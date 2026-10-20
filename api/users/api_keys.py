import datetime
import secrets

from pydantic import BaseModel, Field
from sqlalchemy import text

from api.admin.auth import resolve_login_user
from api.users.models import UserApiKey
from app.http import json_response
from settings.database import engine
from utils.res_code import Code, ERROR_MAP

# 2026-10-01 00:00:00（不含）之前注册的用户仍可用手机号当密钥。
PHONE_KEY_CUTOFF = datetime.datetime(2026, 10, 1)
MAX_KEYS = 20


class ApiKeyCreate(BaseModel):
    name: str = Field("", description="密钥备注，可空")


class ApiKeyId(BaseModel):
    id: int


def phone_key_allowed(register_time) -> bool:
    if register_time is None:
        return True
    if getattr(register_time, "tzinfo", None) is not None:
        register_time = register_time.replace(tzinfo=None)
    return register_time < PHONE_KEY_CUTOFF


def user_allows_phone_key(user, db=None) -> bool:
    """手机号还能不能用来请求模型。生成过 sk- 后永久关闭，删掉密钥也不恢复。

    只限制模型调用。价目、用量、模型列表和其他功能仍用手机号。
    """
    if user is None:
        return False
    if bool(getattr(user, "phone_key_revoked", False)):
        return False
    user_id = getattr(user, "user_id", None)
    if db is not None and user_id:
        issued = db.query(UserApiKey.id).filter(UserApiKey.user_id == user_id).limit(1).first()
        if issued:
            return False
    return phone_key_allowed(getattr(user, "register_time", None))


def ensure_api_key_table():
    UserApiKey.__table__.create(bind=engine, checkfirst=True)
    statements = (
        "ALTER TABLE tb_user ADD COLUMN phone_key_revoked TINYINT(1) NOT NULL DEFAULT 0",
        "UPDATE tb_user u SET phone_key_revoked = 1 "
        "WHERE phone_key_revoked = 0 AND EXISTS ("
        "SELECT 1 FROM tb_user_api_key k WHERE k.user_id = u.user_id)",
    )
    with engine.begin() as conn:
        for ddl in statements:
            try:
                conn.execute(text(ddl))
            except Exception as exc:
                msg = str(exc).lower()
                if "duplicate column" in msg or "1060" in msg:
                    continue
                if "doesn't exist" in msg or "1146" in msg:
                    continue
                raise


def _fmt_time(value):
    if value and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return ""


def mask_api_key(api_key: str) -> str:
    key = api_key or ""
    if len(key) <= 12:
        return key
    return f"{key[:7]}****{key[-4:]}"


def _require_user(common):
    user = resolve_login_user(common)
    if not user or user.is_delete:
        return None, json_response({
            "code": str(Code.USER_EXPIRE),
            "codeMsg": ERROR_MAP[Code.USER_EXPIRE],
        })
    return user, None


def _key_item(row: UserApiKey, reveal: str = ""):
    # 只返回给密钥所属用户。列表也带完整密钥，方便下次打开页面再复制。
    return {
        "id": row.id,
        "name": row.name or "",
        "key_mask": mask_api_key(row.api_key),
        "api_key": reveal or (row.api_key or ""),
        "is_active": bool(row.is_active),
        "created_at": _fmt_time(row.created_at),
    }


class ApiKeyService:
    def list_keys(self, common):
        ensure_api_key_table()
        user, error = _require_user(common)
        if error:
            return error
        rows = common.db.query(UserApiKey).filter(
            UserApiKey.user_id == user.user_id
        ).order_by(UserApiKey.id.desc()).all()
        return json_response({
            "code": Code.OK,
            "codeMsg": ERROR_MAP[Code.OK],
            "allow_phone_key": user_allows_phone_key(user, common.db),
            "register_time": _fmt_time(user.register_time),
            "keys": [_key_item(row) for row in rows],
        })

    def create_key(self, request_body: ApiKeyCreate, common):
        ensure_api_key_table()
        user, error = _require_user(common)
        if error:
            return error
        count = common.db.query(UserApiKey).filter(UserApiKey.user_id == user.user_id).count()
        if count >= MAX_KEYS:
            return json_response({
                "code": Code.ACCESS_DENY,
                "codeMsg": f"最多创建 {MAX_KEYS} 把密钥，请先删除不再使用的密钥",
            })
        name = (request_body.name or "").strip()[:40] or "未命名"
        api_key = ""
        for _ in range(5):
            candidate = "sk-" + secrets.token_hex(24)
            exists = common.db.query(UserApiKey).filter(UserApiKey.api_key == candidate).first()
            if not exists:
                api_key = candidate
                break
        if not api_key:
            return json_response({
                "code": Code.ACCESS_DENY,
                "codeMsg": "密钥生成失败，请重试",
            })
        user.phone_key_revoked = True
        row = UserApiKey(user_id=user.user_id, api_key=api_key, name=name, is_active=True)
        common.db.add(row)
        common.db.commit()
        common.db.refresh(row)
        return json_response({
            "code": Code.OK,
            "codeMsg": ERROR_MAP[Code.OK],
            "key": _key_item(row, reveal=api_key),
        })

    def set_active(self, request_body: ApiKeyId, common, active: bool):
        ensure_api_key_table()
        user, error = _require_user(common)
        if error:
            return error
        row = common.db.query(UserApiKey).filter(
            UserApiKey.id == request_body.id,
            UserApiKey.user_id == user.user_id,
        ).first()
        if not row:
            return json_response({
                "code": Code.CONTEXT_ID_WRONG,
                "codeMsg": "密钥不存在",
            })
        row.is_active = active
        row.updated_at = datetime.datetime.now()
        common.db.commit()
        return json_response({
            "code": Code.OK,
            "codeMsg": ERROR_MAP[Code.OK],
            "key": _key_item(row),
            "allow_phone_key": user_allows_phone_key(user, common.db),
        })

    def delete_key(self, request_body: ApiKeyId, common):
        ensure_api_key_table()
        user, error = _require_user(common)
        if error:
            return error
        row = common.db.query(UserApiKey).filter(
            UserApiKey.id == request_body.id,
            UserApiKey.user_id == user.user_id,
        ).first()
        if not row:
            return json_response({
                "code": Code.CONTEXT_ID_WRONG,
                "codeMsg": "密钥不存在",
            })
        common.db.delete(row)
        if not bool(getattr(user, "phone_key_revoked", False)):
            user.phone_key_revoked = True
        common.db.commit()
        return json_response({
            "code": Code.OK,
            "codeMsg": ERROR_MAP[Code.OK],
            "allow_phone_key": False,
        })


api_key_service = ApiKeyService()
