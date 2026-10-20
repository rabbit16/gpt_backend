from typing import Optional

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    content: str = Field(..., description="留言正文，5-2000字")
    contact: Optional[str] = Field("", description="选填联系方式，如微信/邮箱/手机")
    nickname: Optional[str] = Field("", description="选填昵称，匿名可空")
    anonymous: bool = Field(True, description="是否匿名，默认匿名")
    userId: Optional[int] = Field(None, description="登录用户可选传入，匿名时忽略")


class FeedbackListQuery(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_num: int = Field(10, ge=1, le=20, description="每页条数，默认 10，最多 20")
