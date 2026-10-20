from typing import Optional

from pydantic import BaseModel, Field


class AnnouncementListQuery(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_num: int = Field(10, ge=1, le=50, description="每页条数")


class AnnouncementCreate(BaseModel):
    title: str = Field(..., description="公告标题")
    content: str = Field(..., description="公告正文")
    status: int = Field(1, description="1 上线 / 0 下线")
    sort: int = Field(0, description="排序，数字越大越靠前")


class AnnouncementUpdate(BaseModel):
    id: int
    title: Optional[str] = None
    content: Optional[str] = None
    status: Optional[int] = None
    sort: Optional[int] = None
    is_delete: Optional[bool] = None
