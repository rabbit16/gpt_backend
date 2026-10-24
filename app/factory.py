import pytz
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from api.router import api_router
from api.announcement.service import ensure_announcement_table
from api.software.service import ensure_software_tables
from api.invoice.service import ensure_invoice_table
from api.open_source.service import ensure_open_source_tables
from api.feedback.service import ensure_feedback_table
from api.task.service import ensure_task_table
from api.users.api_keys import ensure_api_key_table
from api.users.username_login import ensure_username_columns
from api.users.curd import update_user_count
from app.exceptions import register_exception_handlers
from app.middleware import register_auth_middleware


def create_app() -> FastAPI:
    app = FastAPI(debug=True)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    register_auth_middleware(app)
    app.include_router(api_router)

    scheduler = AsyncIOScheduler()

    @app.on_event("startup")
    async def startup_event():
        ensure_feedback_table()
        ensure_task_table()
        ensure_announcement_table()
        ensure_software_tables()
        ensure_invoice_table()
        ensure_open_source_tables()
        ensure_api_key_table()
        ensure_username_columns()
        scheduler.add_job(
            update_user_count,
            trigger=CronTrigger(hour=0, minute=0, second=0, timezone=pytz.timezone("Asia/Shanghai")),
        )
        scheduler.start()

    @app.on_event("shutdown")
    def shutdown_event():
        scheduler.shutdown()

    return app
