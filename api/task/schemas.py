from typing import Optional

from pydantic import BaseModel, Field


class TaskListQuery(BaseModel):
    scope: str = Field("open", description="open/all/pending/running/failed/done")
    page: int = Field(1, ge=1)
    page_num: int = Field(20, ge=1, le=50)


class TaskCreate(BaseModel):
    title: str = Field(..., description="任务标题")
    detail: Optional[str] = Field("", description="补充说明")
    log_text: Optional[str] = Field("", description="用于判断状态的日志")


class TaskLogUpdate(BaseModel):
    id: int
    log_text: str = Field("", description="整段替换为最新日志")


class TaskStatusUpdate(BaseModel):
    id: int
    status: str = Field(..., description="pending/running/failed/done")


class TaskId(BaseModel):
    id: int
