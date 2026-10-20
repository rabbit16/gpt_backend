import datetime
import random
import secrets
import time

from sqlalchemy import func, or_, and_
from sqlalchemy.exc import IntegrityError

from api.admin.auth import is_admin_user, resolve_login_user
from api.users.api_keys import user_allows_phone_key
from api.users import curd
from api.users.curd import md5_encrypt
from api.users.models import User
from api.users.response_schemas import RegisterResponse, LoginResponse, UserInfoResponse
from api.users.schemas import (
    PasswordCodeFormat,
    PasswordResetFormat,
    ProfileUpdateFormat,
    UserRequestFormat,
    UserLoginFormat,
    UserInfoQuery,
    UserExist,
)
from api.users.username_login import (
    EMAIL_RE,
    PHONE_RE,
    account_conflict,
    blank_to_none,
    ensure_username_columns,
    find_user_by_username,
    generate_memorable_username,
    is_memorable_username,
    password_matches,
    store_password,
)
from app.http import json_response
from settings.dependencies import REDIS_TOOL, REDIS_SMI_CODE
from settings.billing import chat_cost_cny
from settings.macro import DEFAULT_EXPIRE_TIME, SAFE_LEN, LOGIN_FAILURE_TIME, SYSTEM_LOG, EMAIL_LOG, USR_LOG
from utils.public_exception import UnicornException
from utils.res_code import Code, ERROR_MAP
from utils.schemas_pub import ResponsePub
from utils.send_email_util import send_email


def _register_time_text(user):
    value = getattr(user, "register_time", None) if user else None
    if value and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return ""


def _phone_key_flag(user, db=None):
    return user_allows_phone_key(user, db)


def _profile_body(user):
    return {
        "userId": user.user_id,
        "userName": user.name or "",
        "telephone": user.telephone or "",
        "email": user.email or "",
        "username": getattr(user, "username", None) or "",
        "is_anonymous": bool(getattr(user, "is_anonymous", False)),
        "is_staff": is_admin_user(user),
        "register_time": _register_time_text(user),
    }


def _sync_profile_cache(user):
    targets = {str(user.user_id)}
    if user.telephone:
        targets.add(str(user.telephone))
    if user.email:
        targets.add(str(user.email))
    try:
        for key in REDIS_TOOL.scan_iter("users:*", count=200):
            raw = REDIS_TOOL.hget(key, "userId")
            if raw is None:
                continue
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            if text not in targets:
                continue
            REDIS_TOOL.hset(key, "userName", user.name or "")
            REDIS_TOOL.hset(key, "telephone", user.telephone or "")
            REDIS_TOOL.hset(key, "email", user.email or "")
            REDIS_TOOL.hset(key, "code", user.code or "")
    except Exception:
        return


class UserService:
    def login(self, request, request_body: UserLoginFormat, common):
        token = request.headers.get("token", "")
        if REDIS_TOOL.exists(f"users:{token}"):
            headers = {
                "x-set-cookie": f"token={token}"
            }
            raw_user_id = REDIS_TOOL.hmget(f"users:{token}", "userId")[0].decode("utf-8")
            logged_in = resolve_login_user(common)
            is_staff = is_admin_user(logged_in)
            response = ResponsePub(
                code=Code.OK,
                codeMsg=ERROR_MAP[Code.OK],
                bodyMessage={
                    "loginDetail": "用户已登入",
                    "loginTime": str(int(time.time())),
                    "userId": raw_user_id,
                    "userName": REDIS_TOOL.hmget(f"users:{token}", "userName")[0].decode("utf-8"),
                    "telephone": REDIS_TOOL.hmget(f"users:{token}", "telephone")[0].decode("utf-8"),
                    "email": REDIS_TOOL.hmget(f"users:{token}", "email")[0].decode("utf-8"),
                    "code": REDIS_TOOL.hmget(f"users:{token}", "code")[0].decode("utf-8"),
                    "is_staff": is_staff,
                    "register_time": _register_time_text(logged_in),
                    "allow_phone_key": _phone_key_flag(logged_in, common.db),
                }
            ).dict()
            return json_response(response, extra_headers=headers)
        ensure_username_columns()
        account = (request_body.userId or "").strip()
        password = request_body.password or ""
        user = common.db.query(User).filter(or_(
            and_(User.telephone == account, User.password == password),
            and_(User.email == account, User.password == password),
        )).first()
        code_key = f"{account}:{password}:password"
        if not user and REDIS_SMI_CODE.exists(code_key):
            user = common.db.query(User).filter(User.telephone == account).first()
        if not user:
            account_owner = common.db.query(User).filter(or_(
                User.telephone == account,
                User.email == account,
            )).first()
            if account_owner:
                verification_code = ''.join(str(random.randint(0, 9)) for _ in range(8))
                redis_code_store = f"{account_owner.telephone}:{md5_encrypt(verification_code)}:password"
                REDIS_SMI_CODE.set(redis_code_store, redis_code_store, ex=300)
                send_email("验证码登陆", f"您好，系统监测到您可能忘记密码，所以发了验证码邮件给您。请您用手机号登陆，并在密码输入框输入以下验证码进行验证码登陆：{verification_code}！！",
                           account_owner.email)
                raise UnicornException(
                    Code.USER_NOT_EXIST,
                    ERROR_MAP[Code.USER_NOT_EXIST]
                )
            named = find_user_by_username(common.db, account)
            if not named:
                raise UnicornException(
                    Code.PASSWORD_WRONG,
                    ERROR_MAP[Code.PASSWORD_WRONG]
                )
            if named.password != password:
                raise UnicornException(Code.PASSWORD_WRONG, "密码错误")
            if named.is_delete:
                raise UnicornException(Code.ACCESS_DENY, "该账号已被封禁")
            if not bool(named.username_login):
                raise UnicornException(Code.ACCESS_DENY, "用户名登录未开启，请联系管理员打开开关")
            user = named

        user_id = user.user_id
        token = secrets.token_urlsafe(SAFE_LEN)
        headers = {
            "x-set-cookie": f"token={token}"
        }
        REDIS_TOOL.hmset(f"users:{token}", {
            "userId": user_id,
            "userName": user.name or "",
            "telephone": user.telephone or "",
            "email": user.email or "",
            "code": user.code or "",
            "is_staff": "1" if is_admin_user(user) else "0",
        })
        REDIS_TOOL.expire(f"users:{token}", LOGIN_FAILURE_TIME)
        login_message = LoginResponse(
            loginDetail="login successfully",
            loginTime=str(int(time.time())),
            userId=user_id,
            userCode=user.code or "",
            userName=user.name or "",
            telephone=user.telephone or "",
            email=user.email or "",
            is_staff=is_admin_user(user),
            register_time=_register_time_text(user),
            allow_phone_key=_phone_key_flag(user, common.db),
        ).dict()
        response = ResponsePub(
            code=str(Code.OK),
            codeMsg=ERROR_MAP[Code.OK],
            bodyMessage=login_message
        ).dict()
        print(token)
        common.db.query(User).filter(and_(
            User.user_id == user_id
        )).update(
            {
                "last_login_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
        common.db.commit()
        return json_response(response, extra_headers=headers)

    def current_session(self, common):
        ensure_username_columns()
        user = resolve_login_user(common)
        if not user or user.is_delete:
            return json_response({
                "code": str(Code.USER_EXPIRE),
                "codeMsg": ERROR_MAP[Code.USER_EXPIRE],
            })
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "bodyMessage": _profile_body(user),
        })

    def logout(self, request):
        token = request.headers.get("token", "")
        REDIS_TOOL.delete(f"users:{token}")
        response = ResponsePub(
            code=Code.OK,
            codeMsg=ERROR_MAP[Code.OK],
            bodyMessage={}
        ).dict()
        return json_response(response, extra_headers={"x-set-cookie": "token=logout"})

    def suggest_anonymous_username(self, common):
        ensure_username_columns()
        username = generate_memorable_username(common.db)
        if not username:
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "暂时无法生成用户名，请稍后再试"})
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "username": username,
        })

    def register(self, request, request_body: UserRequestFormat, common):
        SYSTEM_LOG.info(f"请求的IP：{request.client.host}")
        ensure_username_columns()
        anonymous = bool(request_body.anonymous)
        name = (request_body.name or "").strip()
        if anonymous:
            supplied = (request_body.username or "").strip().lower()
            if (
                is_memorable_username(supplied)
                and not find_user_by_username(common.db, supplied)
                and not account_conflict(common.db, supplied)
            ):
                username = supplied
            else:
                username = generate_memorable_username(common.db)
            if not username:
                raise UnicornException(Code.USER_EXIST, "暂时无法生成用户名，请稍后再试")
            if not name:
                name = username
            if len(name) > 100:
                raise UnicornException(Code.USER_EXIST, "名称请控制在 100 字以内")
            request_body.name = name
            request_body.telephone = None
            request_body.email = None
            request_body.code = name
            request_body.username = username
            request_body.username_login = True
            request_body.is_anonymous = True
        else:
            if not name or len(name) > 100:
                raise UnicornException(Code.USER_EXIST, "请填写名称")
            telephone = (request_body.telephone or "").strip()
            email = (request_body.email or "").strip().lower()
            if not PHONE_RE.match(telephone):
                raise UnicornException(Code.USER_EXIST, "请填写正确的电话号码")
            if not EMAIL_RE.match(email):
                raise UnicornException(Code.USER_EXIST, "请填写正确的邮箱")
            if common.db.query(User).filter(User.telephone == telephone).first():
                raise UnicornException(Code.USER_EXIST, "手机号已存在")
            if common.db.query(User).filter(func.lower(User.email) == email).first():
                raise UnicornException(Code.USER_EXIST, "邮箱已存在")
            request_body.name = name
            request_body.telephone = telephone
            request_body.email = email
            request_body.code = name
            request_body.username = None
            request_body.username_login = False
            request_body.is_anonymous = False
        request_body.is_staff = False
        try:
            code, single_user = curd.create_single_user(request_body, common.db)
        except IntegrityError:
            common.db.rollback()
            if not anonymous:
                raise UnicornException(Code.USER_EXIST, "手机号或邮箱已存在")
            request_body.username = generate_memorable_username(common.db)
            if not request_body.username:
                raise UnicornException(Code.USER_EXIST, "暂时无法生成用户名，请稍后再试")
            code, single_user = curd.create_single_user(request_body, common.db)
        token = secrets.token_urlsafe(SAFE_LEN)
        REDIS_TOOL.hmset(f"users:{token}",
                         {
                             "userId": single_user.user_id if anonymous else single_user.telephone,
                             "userName": single_user.name or "",
                             "telephone": single_user.telephone or "",
                             "email": single_user.email or "",
                             "code": single_user.code or "",
                         }
                         )
        if single_user.email:
            try:
                send_email("注册成功通知",
                           "恭喜，您的账户以注册成功，请尽快开始对话，来激活账户，谢谢您的理解与配合",
                           single_user.email)
                EMAIL_LOG.info(f"""成功向用户发送邮件{single_user.to_dict()}""")
            except Exception as e:
                EMAIL_LOG.warning(f"""发送失败，用户不存在""")
                common.db.delete(single_user)
                common.db.commit()
        REDIS_TOOL.expire(f"users:{token}", DEFAULT_EXPIRE_TIME)
        response = ResponsePub(
            code=str(code),
            codeMsg=ERROR_MAP[code],
            bodyMessage=RegisterResponse(
                registerDetail="register successfully",
                registerFinishTime=str(int(time.time())),
                userId=single_user.user_id,
                userName=single_user.name,
                telephone=single_user.telephone or "",
                email=single_user.email or "",
                code=single_user.code or "",
                register_time=_register_time_text(single_user),
                allow_phone_key=_phone_key_flag(single_user, common.db),
                username=single_user.username or "",
                is_anonymous=bool(single_user.is_anonymous),
            )
        )
        return json_response(response.dict(), extra_headers={"x-set-cookie": f"token={token}"})

    def send_reset_code(self, request_body: PasswordCodeFormat, common):
        email = (request_body.email or "").strip().lower()
        if not EMAIL_RE.match(email):
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "请填写正确的邮箱"})
        user = common.db.query(User).filter(func.lower(User.email) == email, User.is_delete == False).first()
        if not user:
            return json_response({"code": str(Code.USER_NOT_EXIST), "codeMsg": "该邮箱未注册"})
        lock_key = f"reset:lock:{email}"
        if REDIS_SMI_CODE.exists(lock_key):
            return json_response({"code": str(Code.FEEDBACK_TOO_FAST), "codeMsg": "验证码已发送，请稍后再试"})
        code = f"{secrets.randbelow(1000000):06d}"
        try:
            send_email(
                "密码找回验证码",
                f"您好，您正在找回密码。验证码是 {code}，10 分钟内有效。请勿把验证码告诉他人。",
                email,
            )
        except Exception:
            EMAIL_LOG.warning(f"密码找回邮件发送失败：{email}")
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "验证码邮件发送失败，请稍后再试"})
        REDIS_SMI_CODE.set(f"reset:{email}", code, ex=600)
        REDIS_SMI_CODE.set(lock_key, "1", ex=60)
        return json_response({"code": str(Code.OK), "codeMsg": "验证码已发送到邮箱"})

    def reset_password(self, request_body: PasswordResetFormat, common):
        email = (request_body.email or "").strip().lower()
        code = (request_body.code or "").strip()
        if not EMAIL_RE.match(email) or not code:
            return json_response({"code": str(Code.PASSWORD_WRONG), "codeMsg": "请填写邮箱和验证码"})
        stored = REDIS_SMI_CODE.get(f"reset:{email}")
        stored_text = stored.decode("utf-8") if isinstance(stored, bytes) else (stored or "")
        if not stored_text or stored_text != code:
            return json_response({"code": str(Code.PASSWORD_WRONG), "codeMsg": "验证码错误或已过期"})
        if not (request_body.password or "").strip():
            return json_response({"code": str(Code.PASSWORD_WRONG), "codeMsg": "请填写新密码"})
        user = common.db.query(User).filter(func.lower(User.email) == email, User.is_delete == False).first()
        if not user:
            return json_response({"code": str(Code.USER_NOT_EXIST), "codeMsg": "该邮箱未注册"})
        user.password = store_password(request_body.password)
        user.update_time = datetime.datetime.now()
        common.db.add(user)
        common.db.commit()
        REDIS_SMI_CODE.delete(f"reset:{email}")
        return json_response({"code": str(Code.OK), "codeMsg": "密码已重置，请使用新密码登录"})

    def update_profile(self, request_body: ProfileUpdateFormat, common):
        ensure_username_columns()
        user = resolve_login_user(common)
        if not user or user.is_delete:
            return json_response({
                "code": str(Code.USER_EXPIRE),
                "codeMsg": ERROR_MAP[Code.USER_EXPIRE],
            })
        name = (request_body.name or "").strip()
        if not name or len(name) > 100:
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "请填写名称，100 字以内"})
        telephone = blank_to_none(request_body.telephone)
        email = blank_to_none(request_body.email)
        if email:
            email = email.lower()
        if telephone and not PHONE_RE.match(telephone):
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "请填写正确的电话号码"})
        if email and not EMAIL_RE.match(email):
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "请填写正确的邮箱"})
        if not telephone and not email and not (user.username or "").strip():
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "请至少保留手机号或邮箱"})
        if telephone:
            taken = common.db.query(User).filter(
                User.telephone == telephone,
                User.user_id != user.user_id,
            ).first()
            if taken:
                return json_response({"code": str(Code.USER_EXIST), "codeMsg": "手机号已存在"})
        if email:
            taken = common.db.query(User).filter(
                func.lower(User.email) == email,
                User.user_id != user.user_id,
            ).first()
            if taken:
                return json_response({"code": str(Code.USER_EXIST), "codeMsg": "邮箱已存在"})
        new_password = (request_body.new_password or "").strip()
        if new_password:
            if not password_matches(user.password, request_body.old_password):
                return json_response({"code": str(Code.PASSWORD_WRONG), "codeMsg": "原密码不正确"})
            user.password = store_password(new_password)
        user.name = name
        if not (user.code or "").strip():
            user.code = name
        user.telephone = telephone
        user.email = email
        user.update_time = datetime.datetime.now()
        common.db.add(user)
        common.db.commit()
        common.db.refresh(user)
        _sync_profile_cache(user)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "资料已更新",
            "bodyMessage": _profile_body(user),
        })

    def get_user_info(self, request_body: UserInfoQuery, common):
        user_obj = common.db.query(User).filter(
            and_(
                User.user_id == request_body.userId,
                User.is_delete == False
            )
        ).first()
        if not user_obj:
            raise UnicornException(
                Code.USER_NOT_EXIST,
                ERROR_MAP[Code.USER_NOT_EXIST]
            )
        return UserInfoResponse(
            code=Code.OK,
            codeMsg=ERROR_MAP[Code.OK],
            userMessage=user_obj.to_dict()
        )

    def user_exist(self, request_body: UserExist, common):
        if common.db.query(User).filter(and_(
                User.user_id == request_body.userId,
                User.is_delete == 0
        )).first():
            USR_LOG.info(f"用户输入: {request_body}")
            if request_body.prompt is not None:
                user_item = common.db.query(User).filter(
                    User.user_id == request_body.userId,
                    User.is_delete == 0
                ).first()
                if request_body.prompt is not None or request_body.prompt != 0:
                    pay_all = chat_cost_cny(
                        "gpt-4o-mini",
                        request_body.prompt,
                        request_body.completion or 0,
                        discount=user_item.discount,
                        money_rate=user_item.money_rate,
                    )
                    common.db.query(User).filter(
                        User.user_id == request_body.userId,
                        User.is_delete == 0
                    ).update({
                        "token": user_item.token - pay_all
                    })
                    common.db.commit()
                    return {
                        "code": 0,
                        "codeMsg": "更新成功"
                    }
            return {
                "code": 0,
                "codeMsg": "用户存在"
            }
        return {
            "code": -1,
            "codeMsg": "用户不存在"
        }


user_service = UserService()
