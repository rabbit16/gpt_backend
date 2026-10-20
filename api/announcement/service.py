import datetime

from api.admin.auth import require_admin
from api.announcement.schemas import (
    AnnouncementCreate,
    AnnouncementListQuery,
    AnnouncementUpdate,
)
from api.users.models import Announcement
from app.http import json_response
from settings.database import engine
from utils.res_code import Code, ERROR_MAP

MIN_TITLE = 1
MAX_TITLE = 200
MIN_CONTENT = 1
MAX_CONTENT = 20000


def ensure_announcement_table():
    Announcement.__table__.create(bind=engine, checkfirst=True)


def _fmt_time(value):
    if value and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or ""


def _public_item(row: Announcement):
    return {
        "id": row.id,
        "title": row.title or "",
        "content": row.content or "",
        "sort": int(row.sort or 0),
        "status": int(row.status or 0),
        "insert_time": _fmt_time(row.insert_time),
        "update_time": _fmt_time(row.update_time),
    }


def _admin_item(row: Announcement):
    item = _public_item(row)
    item["is_delete"] = bool(row.is_delete)
    return item


class AnnouncementService:
    def list_public(self, request_body: AnnouncementListQuery, common):
        ensure_announcement_table()
        page = request_body.page or 1
        page_num = request_body.page_num or 10
        query = common.db.query(Announcement).filter(
            Announcement.is_delete == False,
            Announcement.status == 1,
        )
        total = query.count()
        rows = (
            query.order_by(Announcement.sort.desc(), Announcement.id.desc())
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [_public_item(row) for row in rows],
            "page": page,
            "page_num": page_num,
            "total": total,
        })

    def latest(self, common):
        """登录弹窗用：取当前上线中排序最前的一条。"""
        ensure_announcement_table()
        row = (
            common.db.query(Announcement)
            .filter(Announcement.is_delete == False, Announcement.status == 1)
            .order_by(Announcement.sort.desc(), Announcement.id.desc())
            .first()
        )
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "item": _public_item(row) if row else None,
        })

    def list_admin(self, request_body: AnnouncementListQuery, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_announcement_table()
        page = request_body.page or 1
        page_num = request_body.page_num or 10
        query = common.db.query(Announcement).filter(Announcement.is_delete == False)
        total = query.count()
        rows = (
            query.order_by(Announcement.sort.desc(), Announcement.id.desc())
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [_admin_item(row) for row in rows],
            "page": page,
            "page_num": page_num,
            "total": total,
        })

    def create(self, request_body: AnnouncementCreate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_announcement_table()
        title = (request_body.title or "").strip()
        content = (request_body.content or "").strip()
        if not (MIN_TITLE <= len(title) <= MAX_TITLE):
            return json_response({
                "code": str(Code.FEEDBACK_INVALID),
                "codeMsg": f"标题请控制在 {MIN_TITLE}-{MAX_TITLE} 字",
            })
        if not (MIN_CONTENT <= len(content) <= MAX_CONTENT):
            return json_response({
                "code": str(Code.FEEDBACK_INVALID),
                "codeMsg": f"内容请控制在 {MIN_CONTENT}-{MAX_CONTENT} 字",
            })
        status = 1 if int(request_body.status or 0) == 1 else 0
        sort = int(request_body.sort or 0)
        now = datetime.datetime.now()
        item = Announcement(
            title=title,
            content=content,
            status=status,
            sort=sort,
            insert_time=now,
            update_time=now,
        )
        common.db.add(item)
        common.db.commit()
        common.db.refresh(item)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "公告已创建",
            "item": _admin_item(item),
        })

    def update(self, request_body: AnnouncementUpdate, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_announcement_table()
        row = common.db.query(Announcement).filter(Announcement.id == request_body.id).first()
        if not row or row.is_delete:
            return json_response({
                "code": str(Code.FEEDBACK_INVALID),
                "codeMsg": "公告不存在",
            })
        payload = {"update_time": datetime.datetime.now()}
        if request_body.title is not None:
            title = request_body.title.strip()
            if not (MIN_TITLE <= len(title) <= MAX_TITLE):
                return json_response({
                    "code": str(Code.FEEDBACK_INVALID),
                    "codeMsg": f"标题请控制在 {MIN_TITLE}-{MAX_TITLE} 字",
                })
            payload["title"] = title
        if request_body.content is not None:
            content = request_body.content.strip()
            if not (MIN_CONTENT <= len(content) <= MAX_CONTENT):
                return json_response({
                    "code": str(Code.FEEDBACK_INVALID),
                    "codeMsg": f"内容请控制在 {MIN_CONTENT}-{MAX_CONTENT} 字",
                })
            payload["content"] = content
        if request_body.status is not None:
            payload["status"] = 1 if int(request_body.status) == 1 else 0
        if request_body.sort is not None:
            payload["sort"] = int(request_body.sort)
        if request_body.is_delete is not None:
            payload["is_delete"] = bool(request_body.is_delete)
        common.db.query(Announcement).filter(Announcement.id == request_body.id).update(payload)
        common.db.commit()
        row = common.db.query(Announcement).filter(Announcement.id == request_body.id).first()
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "更新成功",
            "item": _admin_item(row) if row else None,
        })


announcement_service = AnnouncementService()
