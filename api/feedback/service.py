import datetime

from sqlalchemy import inspect, text

from api.feedback.schemas import FeedbackCreate, FeedbackListQuery
from api.users.models import UserFeedback
from app.http import json_response
from settings.database import engine
from settings.dependencies import REDIS_TOOL
from utils.res_code import Code, ERROR_MAP

MIN_CONTENT = 5
MAX_CONTENT = 2000
MAX_CONTACT = 100
MAX_NICKNAME = 50
COOLDOWN_SECONDS = 30
DAILY_LIMIT = 20


def ensure_feedback_table():
    UserFeedback.__table__.create(bind=engine, checkfirst=True)
    _ensure_reply_columns()


def _ensure_reply_columns():
    """已有表补上管理员回复字段。"""
    try:
        columns = {col["name"] for col in inspect(engine).get_columns("tb_user_feedback")}
    except Exception:
        return
    alters = []
    if "reply" not in columns:
        alters.append("ADD COLUMN reply TEXT NULL")
    if "reply_time" not in columns:
        alters.append("ADD COLUMN reply_time DATETIME NULL")
    if not alters:
        return
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE tb_user_feedback {', '.join(alters)}"))


def _client_ip(common):
    request = common.request
    forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


class FeedbackService:
    def create(self, request_body: FeedbackCreate, common):
        ensure_feedback_table()
        content = (request_body.content or "").strip()
        contact = (request_body.contact or "").strip()
        nickname = (request_body.nickname or "").strip()
        if len(content) < MIN_CONTENT or len(content) > MAX_CONTENT:
            return json_response({
                "code": str(Code.FEEDBACK_INVALID),
                "codeMsg": f"留言请控制在 {MIN_CONTENT}-{MAX_CONTENT} 字",
            })
        if len(contact) > MAX_CONTACT or len(nickname) > MAX_NICKNAME:
            return json_response({
                "code": str(Code.FEEDBACK_INVALID),
                "codeMsg": ERROR_MAP[Code.FEEDBACK_INVALID],
            })

        ip = _client_ip(common)
        cooldown_key = f"feedback:cd:{ip}"
        if REDIS_TOOL.get(cooldown_key):
            return json_response({
                "code": str(Code.FEEDBACK_TOO_FAST),
                "codeMsg": ERROR_MAP[Code.FEEDBACK_TOO_FAST],
            })
        day_key = f"feedback:day:{ip}:{datetime.datetime.now().strftime('%Y%m%d')}"
        daily_count = int(REDIS_TOOL.get(day_key) or 0)
        if daily_count >= DAILY_LIMIT:
            return json_response({
                "code": str(Code.FEEDBACK_TOO_FAST),
                "codeMsg": "今天留言次数已达上限，请明天再来",
            })

        anonymous = True if request_body.anonymous is None else bool(request_body.anonymous)
        user_id = request_body.userId
        item = UserFeedback(
            content=content,
            contact=contact,
            nickname=nickname,
            anonymous=anonymous,
            user_id=user_id,
            ip=ip,
            user_agent=(common.request.headers.get("user-agent") or "")[:255],
        )
        common.db.add(item)
        common.db.commit()
        common.db.refresh(item)
        REDIS_TOOL.setex(cooldown_key, COOLDOWN_SECONDS, 1)
        REDIS_TOOL.incr(day_key)
        if REDIS_TOOL.ttl(day_key) < 0:
            REDIS_TOOL.expire(day_key, 24 * 60 * 60)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "留言已收到，感谢反馈",
            "id": item.id,
        })

    def list_public(self, request_body: FeedbackListQuery, common):
        ensure_feedback_table()
        page = request_body.page or 1
        page_num = request_body.page_num or 10
        query = common.db.query(UserFeedback).filter(UserFeedback.is_delete == False)
        total = query.count()
        rows = (
            query.order_by(UserFeedback.id.desc())
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [self._public_item(row) for row in rows],
            "page": page,
            "page_num": page_num,
            "total": total,
        })

    @staticmethod
    def _public_item(row: UserFeedback):
        nickname = (row.nickname or "").strip()
        if not nickname:
            nickname = "匿名用户" if row.anonymous else "用户"
        insert_time = row.insert_time
        if insert_time and hasattr(insert_time, "strftime"):
            insert_time = insert_time.strftime("%Y-%m-%d %H:%M:%S")
        reply = (row.reply or "").strip()
        reply_time = row.reply_time
        if reply_time and hasattr(reply_time, "strftime"):
            reply_time = reply_time.strftime("%Y-%m-%d %H:%M:%S")
        return {
            "id": row.id,
            "content": row.content,
            "nickname": nickname,
            "anonymous": bool(row.anonymous),
            "insert_time": insert_time or "",
            "reply": reply,
            "reply_time": reply_time or "",
        }


feedback_service = FeedbackService()
