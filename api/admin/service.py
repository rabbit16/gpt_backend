import datetime
import time

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from api.admin.auth import is_admin_user, require_admin
from api.feedback.service import ensure_feedback_table
from settings.dependencies import REDIS_TOOL
from api.admin.schemas import (
    AdminFeedbackQuery,
    AdminFeedbackUpdate,
    AdminOrderQuery,
    AdminPageQuery,
    AdminUserCreate,
    AdminUserUpdate,
)
from api.users.models import Bill, FunctionCode, User, UserContext, UserFeedback
from api.users.username_login import (
    EMAIL_RE,
    PHONE_RE,
    account_conflict,
    blank_to_none,
    ensure_username_columns,
    find_user_by_username,
    hash_password,
    normalize_username,
    validate_password,
)
from app.http import json_response
from settings.billing import GPT_MODE_LIST, billing_public_config
from utils.res_code import Code, ERROR_MAP
from utils.send_email_util import send_email


def _fmt_time(value):
    if value and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or ""


def _sync_staff_cache(user_id, is_admin):
    """已登录会话里的管理员标记跟着数据库走，避免改完还要重新登录才生效。"""
    flag = "1" if is_admin else "0"
    target = str(user_id)
    try:
        for key in REDIS_TOOL.scan_iter("users:*", count=200):
            raw = REDIS_TOOL.hget(key, "userId")
            if raw is None:
                continue
            text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            if text == target:
                REDIS_TOOL.hset(key, "is_staff", flag)
    except Exception:
        return


class AdminService:
    def overview(self, common):
        admin, error = require_admin(common)
        if error:
            return error
        user_query = common.db.query(User)
        feedback_query = common.db.query(UserFeedback).filter(UserFeedback.is_delete == False)
        bill_query = common.db.query(Bill).filter(Bill.is_delete == False)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "overview": {
                "user_count": user_query.count(),
                "active_user_count": user_query.filter(User.is_delete == False).count(),
                "banned_user_count": user_query.filter(User.is_delete == True).count(),
                "balance_sum": round(float(user_query.with_entities(func.coalesce(func.sum(User.token), 0)).scalar() or 0), 4),
                "today_consume": round(float(user_query.with_entities(func.coalesce(func.sum(User.token_daily), 0)).scalar() or 0), 4),
                "feedback_count": feedback_query.count(),
                "unread_feedback": feedback_query.filter(UserFeedback.is_read == False).count(),
                "order_count": bill_query.count(),
                "order_sum": round(float(bill_query.with_entities(func.coalesce(func.sum(Bill.money), 0)).scalar() or 0), 2),
            },
            "billing": billing_public_config(),
            "models": GPT_MODE_LIST,
        })

    def list_users(self, request_body: AdminPageQuery, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_username_columns()
        query = common.db.query(User)
        keyword = (request_body.keyword or "").strip()
        if keyword:
            filters = [
                User.name.contains(keyword),
                User.email.contains(keyword),
                User.telephone.contains(keyword),
                User.username.contains(keyword),
            ]
            if keyword.isdigit():
                filters.append(User.user_id == int(keyword))
            query = query.filter(or_(*filters))
        total = query.count()
        rows = (
            query.order_by(User.user_id.desc())
            .offset((request_body.page - 1) * request_body.page_num)
            .limit(request_body.page_num)
            .all()
        )
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [self._user_item(row) for row in rows],
            "page": request_body.page,
            "page_num": request_body.page_num,
            "total": total,
        })

    def create_user(self, request_body: AdminUserCreate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_username_columns()
        username, username_error = normalize_username(request_body.username)
        if username_error:
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": username_error})
        password_error = validate_password(request_body.password)
        if password_error:
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": password_error})
        telephone = blank_to_none(request_body.telephone)
        email = blank_to_none(request_body.email)
        if email:
            email = email.lower()
        contact_error = self._contact_error(common, telephone, email)
        if contact_error:
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": contact_error})
        if find_user_by_username(common.db, username):
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "用户名已存在"})
        if account_conflict(common.db, username):
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "用户名不能与已有手机号或邮箱相同"})
        nickname = blank_to_none(request_body.name) or username
        user = User(
            name=nickname[:100],
            code=username,
            telephone=telephone,
            email=email,
            password=hash_password(request_body.password),
            username=username,
            username_login=bool(request_body.username_login),
            is_staff=bool(request_body.is_staff),
            is_activate=True,
            is_delete=False,
            token=0 if request_body.token is None else request_body.token,
            discount=1 if request_body.discount is None else request_body.discount,
            money_rate=1 if request_body.money_rate is None else request_body.money_rate,
            plus_user_count=4,
            regular_user=0,
            is_year=0,
            is_quarter=0,
            plus_user_expire_time=datetime.datetime.now() + datetime.timedelta(days=3),
        )
        common.db.add(user)
        try:
            common.db.commit()
        except IntegrityError:
            common.db.rollback()
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "用户名、手机号或邮箱已存在"})
        common.db.refresh(user)
        common.db.add(UserContext(
            context_id=str(int(time.time() * 1000)),
            used_by=user.user_id,
        ))
        common.db.commit()
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "用户已添加",
            "user": self._user_item(user),
        })

    def update_user(self, request_body: AdminUserUpdate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_username_columns()
        user = common.db.query(User).filter(User.user_id == request_body.userId).first()
        if not user:
            return json_response({
                "code": str(Code.USER_NOT_EXIST),
                "codeMsg": "用户不存在",
            })
        editing_self = int(user.user_id) == int(admin.user_id)
        changed = False
        staff_blocked = False
        password_plain = ""
        if request_body.token is not None:
            user.token = request_body.token
            changed = True
        if request_body.discount is not None:
            user.discount = request_body.discount
            changed = True
        if request_body.money_rate is not None:
            user.money_rate = request_body.money_rate
            changed = True
        if request_body.is_delete is not None and not editing_self:
            user.is_delete = bool(request_body.is_delete)
            changed = True
        if request_body.is_staff is not None:
            if editing_self and bool(request_body.is_staff) != bool(user.is_staff):
                staff_blocked = True
            elif not editing_self:
                user.is_staff = bool(request_body.is_staff)
                changed = True
        if request_body.username is not None:
            username, username_error = normalize_username(request_body.username) if request_body.username.strip() else ("", "")
            if request_body.username.strip() and username_error:
                return json_response({"code": str(Code.USER_EXIST), "codeMsg": username_error})
            if username and find_user_by_username(common.db, username, exclude_user_id=user.user_id):
                return json_response({"code": str(Code.USER_EXIST), "codeMsg": "用户名已存在"})
            if username and account_conflict(common.db, username, exclude_user_id=user.user_id):
                return json_response({"code": str(Code.USER_EXIST), "codeMsg": "用户名不能与已有手机号或邮箱相同"})
            user.username = username or None
            if not user.username:
                user.username_login = False
            changed = True
        if request_body.password:
            password_error = validate_password(request_body.password)
            if password_error:
                return json_response({"code": str(Code.USER_EXIST), "codeMsg": password_error})
            password_plain = request_body.password
            user.password = hash_password(password_plain)
            changed = True
        if request_body.username_login is not None:
            if request_body.username_login and not user.username:
                return json_response({"code": str(Code.USER_EXIST), "codeMsg": "请先填写唯一用户名，再打开用户名登录"})
            user.username_login = bool(request_body.username_login)
            changed = True
        if staff_blocked and not changed:
            return json_response({
                "code": str(Code.ACCESS_DENY),
                "codeMsg": "不能修改自己的管理员身份",
            })
        if not changed:
            return json_response({
                "code": str(Code.ACCESS_DENY),
                "codeMsg": "没有可更新的字段",
            })
        user.update_time = datetime.datetime.now()
        common.db.add(user)
        try:
            common.db.commit()
        except IntegrityError:
            common.db.rollback()
            return json_response({"code": str(Code.USER_EXIST), "codeMsg": "用户名已存在"})
        common.db.refresh(user)
        _sync_staff_cache(user.user_id, is_admin_user(user))
        code_msg = "其他资料已更新，不能修改自己的管理员身份" if staff_blocked else "更新成功"
        if password_plain:
            email = (user.email or "").strip()
            if bool(getattr(user, "is_anonymous", False)) or not email:
                code_msg += "。该用户是匿名用户或未填写邮箱，未发送邮件"
            else:
                try:
                    send_email(
                        "密码已被管理员重置",
                        f"您好，管理员已将您的登录密码重置为：{password_plain}。请使用新密码登录，并尽快在个人资料中修改。",
                        email,
                    )
                    code_msg += "。已邮件通知用户"
                except Exception:
                    code_msg += "。密码已修改，但邮件发送失败"
        return json_response({
            "code": str(Code.OK),
            "codeMsg": code_msg,
            "user": self._user_item(user),
        })

    def list_feedback(self, request_body: AdminFeedbackQuery, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_feedback_table()
        query = common.db.query(UserFeedback)
        if request_body.only_unread:
            query = query.filter(UserFeedback.is_read == False, UserFeedback.is_delete == False)
        total = query.count()
        rows = (
            query.order_by(UserFeedback.id.desc())
            .offset((request_body.page - 1) * request_body.page_num)
            .limit(request_body.page_num)
            .all()
        )
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [self._feedback_item(row) for row in rows],
            "page": request_body.page,
            "page_num": request_body.page_num,
            "total": total,
        })

    def update_feedback(self, request_body: AdminFeedbackUpdate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_feedback_table()
        row = common.db.query(UserFeedback).filter(UserFeedback.id == request_body.id).first()
        if not row:
            return json_response({
                "code": str(Code.FEEDBACK_INVALID),
                "codeMsg": "留言不存在",
            })
        payload = {}
        code_msg = "更新成功"
        if request_body.is_read is not None:
            payload["is_read"] = request_body.is_read
        if request_body.is_delete is not None:
            payload["is_delete"] = request_body.is_delete
        if request_body.reply is not None:
            reply = request_body.reply.strip()
            if len(reply) > 2000:
                return json_response({
                    "code": str(Code.FEEDBACK_INVALID),
                    "codeMsg": "回复请控制在 2000 字以内",
                })
            payload["reply"] = reply
            payload["reply_time"] = datetime.datetime.now() if reply else None
            if reply:
                payload["is_read"] = True
            code_msg = "回复已发布" if reply else "回复已清空"
        if payload:
            common.db.query(UserFeedback).filter(UserFeedback.id == request_body.id).update(payload)
            common.db.commit()
            row = common.db.query(UserFeedback).filter(UserFeedback.id == request_body.id).first()
        return json_response({
            "code": str(Code.OK),
            "codeMsg": code_msg,
            "item": self._feedback_item(row),
        })

    def list_orders(self, request_body: AdminOrderQuery, common):
        admin, error = require_admin(common)
        if error:
            return error
        query = common.db.query(Bill).filter(Bill.is_delete == False)
        if request_body.userId:
            query = query.filter(Bill.generate_by == request_body.userId)
        functions = {
            item.function_id: item.function_name
            for item in common.db.query(FunctionCode).all()
        }
        total = query.count()
        rows = (
            query.order_by(Bill.generate_time.desc())
            .offset((request_body.page - 1) * request_body.page_num)
            .limit(request_body.page_num)
            .all()
        )
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [{
                "bill_id": row.bill_id,
                "user_id": row.generate_by,
                "money": row.money,
                "function_name": functions.get(row.function_id, str(row.function_id)),
                "generate_time": _fmt_time(row.generate_time),
            } for row in rows],
            "page": request_body.page,
            "page_num": request_body.page_num,
            "total": total,
        })

    @staticmethod
    def _user_item(row: User):
        return {
            "user_id": row.user_id,
            "name": row.name,
            "email": row.email,
            "telephone": row.telephone,
            "username": row.username or "",
            "username_login": bool(row.username_login),
            "is_anonymous": bool(getattr(row, "is_anonymous", False)),
            "token": row.token,
            "discount": row.discount,
            "money_rate": row.money_rate,
            "is_staff": bool(row.is_staff),
            "is_admin": is_admin_user(row),
            "is_delete": bool(row.is_delete),
            "token_daily": row.token_daily,
            "input_token": row.input_token,
            "output_token": row.output_token,
            "answer_num": row.answer_num,
            "register_time": _fmt_time(row.register_time),
            "last_login_time": _fmt_time(row.last_login_time),
        }

    @staticmethod
    def _contact_error(common, telephone, email, exclude_user_id=None):
        if telephone and not PHONE_RE.match(telephone):
            return "请填写正确的手机号"
        if email and not EMAIL_RE.match(email):
            return "请填写正确的邮箱"
        if telephone:
            query = common.db.query(User).filter(User.telephone == telephone)
            if exclude_user_id is not None:
                query = query.filter(User.user_id != int(exclude_user_id))
            if query.first():
                return "手机号已存在"
        if email:
            query = common.db.query(User).filter(func.lower(User.email) == email.lower())
            if exclude_user_id is not None:
                query = query.filter(User.user_id != int(exclude_user_id))
            if query.first():
                return "邮箱已存在"
        return ""

    @staticmethod
    def _feedback_item(row: UserFeedback):
        return {
            "id": row.id,
            "content": row.content,
            "contact": row.contact or "",
            "nickname": row.nickname or ("匿名用户" if row.anonymous else "用户"),
            "anonymous": bool(row.anonymous),
            "user_id": row.user_id,
            "ip": row.ip or "",
            "insert_time": _fmt_time(row.insert_time),
            "is_read": bool(row.is_read),
            "is_delete": bool(row.is_delete),
            "reply": (row.reply or "").strip(),
            "reply_time": _fmt_time(row.reply_time),
        }


admin_service = AdminService()
