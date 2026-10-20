from sqlalchemy import or_

from api.users.models import User
from app.http import json_response
from settings.dependencies import REDIS_TOOL
from settings.macro import SUPER_ADMIN_PHONES, SUPER_USER_ID_LIST
from utils.res_code import Code, ERROR_MAP


def _decode(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def resolve_login_user(common):
    token = common.request.headers.get("token") or ""
    if not token or not REDIS_TOOL.exists(f"users:{token}"):
        return None
    raw_user_id = _decode(REDIS_TOOL.hmget(f"users:{token}", "userId")[0])
    if raw_user_id.isdigit():
        return common.db.query(User).filter(User.user_id == int(raw_user_id)).first()
    return common.db.query(User).filter(or_(
        User.telephone == raw_user_id,
        User.email == raw_user_id,
    )).first()


def is_admin_user(user):
    if not user or user.is_delete:
        return False
    telephone = str(user.telephone or "").strip()
    return bool(
        user.is_staff
        or user.user_id in SUPER_USER_ID_LIST
        or telephone in SUPER_ADMIN_PHONES
    )


def require_admin(common):
    user = resolve_login_user(common)
    if not user:
        return None, json_response({
            "code": str(Code.USER_EXPIRE),
            "codeMsg": ERROR_MAP[Code.USER_EXPIRE],
        })
    if not is_admin_user(user):
        return None, json_response({
            "code": str(Code.ACCESS_DENY),
            "codeMsg": "仅管理员可访问后台",
        })
    return user, None
