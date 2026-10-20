from api.admin.auth import resolve_login_user
from api.task.decide import decide_from_log
from api.users.models import UserTask
from app.http import json_response
from settings.database import engine
from utils.res_code import Code, ERROR_MAP

STATUSES = ("pending", "running", "failed", "done")
SCOPES = ("open", "all", "pending", "running", "failed", "done")
MAX_TITLE = 80
MAX_DETAIL = 500
MAX_LOG = 20000


def ensure_task_table():
    UserTask.__table__.create(bind=engine, checkfirst=True)


def _fmt(value):
    if value and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or ""


def _item(row: UserTask):
    return {
        "id": row.id,
        "title": row.title,
        "detail": row.detail or "",
        "status": row.status,
        "status_source": row.status_source or "log",
        "suggested_status": row.suggested_status or "pending",
        "decision": row.decision or "",
        "log_text": row.log_text or "",
        "insert_time": _fmt(row.insert_time),
        "update_time": _fmt(row.update_time),
    }


class TaskService:
    def list_tasks(self, request_body, common):
        user, error = self._user(common)
        if error:
            return error
        ensure_task_table()
        scope = request_body.scope if request_body.scope in SCOPES else "open"
        page = request_body.page or 1
        page_num = request_body.page_num or 20
        base = common.db.query(UserTask).filter(
            UserTask.user_id == user.user_id,
            UserTask.is_delete == False,
        )
        counts = {
            "all": base.count(),
            "pending": base.filter(UserTask.status == "pending").count(),
            "running": base.filter(UserTask.status == "running").count(),
            "failed": base.filter(UserTask.status == "failed").count(),
            "done": base.filter(UserTask.status == "done").count(),
        }
        counts["open"] = counts["pending"] + counts["running"] + counts["failed"]
        query = base
        if scope == "open":
            query = query.filter(UserTask.status != "done")
        elif scope != "all":
            query = query.filter(UserTask.status == scope)
        total = query.count()
        rows = (
            query.order_by(UserTask.update_time.desc(), UserTask.id.desc())
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )
        return json_response({
            "code": str(Code.OK),
            "codeMsg": ERROR_MAP[Code.OK],
            "list": [_item(row) for row in rows],
            "page": page,
            "page_num": page_num,
            "total": total,
            "scope": scope,
            "counts": counts,
        })

    def create(self, request_body, common):
        user, error = self._user(common)
        if error:
            return error
        ensure_task_table()
        title = (request_body.title or "").strip()
        detail = (request_body.detail or "").strip()
        log_text = request_body.log_text or ""
        invalid = self._validate(title, detail, log_text)
        if invalid:
            return invalid
        suggested, decision = decide_from_log(log_text)
        row = UserTask(
            user_id=user.user_id,
            title=title,
            detail=detail,
            log_text=log_text.strip(),
            status=suggested,
            status_source="log",
            suggested_status=suggested,
            decision=decision[:300],
        )
        common.db.add(row)
        common.db.commit()
        common.db.refresh(row)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "任务已记下",
            "item": _item(row),
        })

    def update_log(self, request_body, common):
        user, error = self._user(common)
        if error:
            return error
        row = self._own(common, user.user_id, request_body.id)
        if not row:
            return self._missing()
        log_text = request_body.log_text or ""
        if len(log_text) > MAX_LOG:
            return self._invalid(f"日志请控制在 {MAX_LOG} 字以内")
        suggested, decision = decide_from_log(log_text)
        row.log_text = log_text.strip()
        row.suggested_status = suggested
        row.decision = decision[:300]
        if row.status_source != "manual":
            row.status = suggested
            row.status_source = "log"
        common.db.commit()
        common.db.refresh(row)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "已按最新日志更新判断",
            "item": _item(row),
        })

    def set_status(self, request_body, common):
        user, error = self._user(common)
        if error:
            return error
        if request_body.status not in STATUSES:
            return self._invalid("状态只能是未开始、进行中、失败或已完成")
        row = self._own(common, user.user_id, request_body.id)
        if not row:
            return self._missing()
        row.status = request_body.status
        row.status_source = "manual"
        common.db.commit()
        common.db.refresh(row)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "已按你的设置更新状态",
            "item": _item(row),
        })

    def reevaluate(self, request_body, common):
        user, error = self._user(common)
        if error:
            return error
        row = self._own(common, user.user_id, request_body.id)
        if not row:
            return self._missing()
        suggested, decision = decide_from_log(row.log_text or "")
        row.suggested_status = suggested
        row.decision = decision[:300]
        row.status = suggested
        row.status_source = "log"
        common.db.commit()
        common.db.refresh(row)
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "已改回日志判断",
            "item": _item(row),
        })

    def complete_all(self, common):
        user, error = self._user(common)
        if error:
            return error
        ensure_task_table()
        rows = common.db.query(UserTask).filter(
            UserTask.user_id == user.user_id,
            UserTask.is_delete == False,
            UserTask.status != "done",
        ).all()
        for row in rows:
            row.status = "done"
            row.status_source = "manual"
        common.db.commit()
        return json_response({
            "code": str(Code.OK),
            "codeMsg": f"已把 {len(rows)} 个未完成任务标成完成",
            "updated": len(rows),
        })

    def delete(self, request_body, common):
        user, error = self._user(common)
        if error:
            return error
        row = self._own(common, user.user_id, request_body.id)
        if not row:
            return self._missing()
        row.is_delete = True
        common.db.commit()
        return json_response({
            "code": str(Code.OK),
            "codeMsg": "任务已删除",
        })

    def delete_done(self, common):
        user, error = self._user(common)
        if error:
            return error
        ensure_task_table()
        rows = common.db.query(UserTask).filter(
            UserTask.user_id == user.user_id,
            UserTask.is_delete == False,
            UserTask.status == "done",
        ).all()
        for row in rows:
            row.is_delete = True
        common.db.commit()
        return json_response({
            "code": str(Code.OK),
            "codeMsg": f"已删除 {len(rows)} 个已完成任务",
            "deleted": len(rows),
        })

    @staticmethod
    def _user(common):
        user = resolve_login_user(common)
        if not user or user.is_delete:
            return None, json_response({
                "code": str(Code.USER_EXPIRE),
                "codeMsg": ERROR_MAP[Code.USER_EXPIRE],
            })
        return user, None

    @staticmethod
    def _own(common, user_id, task_id):
        ensure_task_table()
        return common.db.query(UserTask).filter(
            UserTask.id == task_id,
            UserTask.user_id == user_id,
            UserTask.is_delete == False,
        ).first()

    @staticmethod
    def _missing():
        return json_response({
            "code": str(Code.TASK_INVALID),
            "codeMsg": "任务不存在",
        })

    @staticmethod
    def _invalid(message):
        return json_response({
            "code": str(Code.TASK_INVALID),
            "codeMsg": message,
        })

    def _validate(self, title, detail, log_text):
        if not title or len(title) > MAX_TITLE:
            return self._invalid(f"标题请控制在 1-{MAX_TITLE} 字")
        if len(detail) > MAX_DETAIL:
            return self._invalid(f"说明请控制在 {MAX_DETAIL} 字以内")
        if len(log_text) > MAX_LOG:
            return self._invalid(f"日志请控制在 {MAX_LOG} 字以内")
        return None


task_service = TaskService()
