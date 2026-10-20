from typing import Optional

from pydantic import BaseModel, Field


class AdminPageQuery(BaseModel):
    page: int = Field(1, ge=1)
    page_num: int = Field(10, ge=1, le=50)
    keyword: Optional[str] = Field("", description="搜索手机号/邮箱/昵称/ID")


class AdminUserCreate(BaseModel):
    username: str = Field(..., description="登录用户名，全局唯一")
    password: str = Field(..., description="明文密码，后端保存 md5")
    name: Optional[str] = Field(None, description="昵称，默认同用户名")
    email: Optional[str] = None
    telephone: Optional[str] = None
    token: Optional[float] = 0
    discount: Optional[float] = 1
    money_rate: Optional[float] = 1
    is_staff: bool = False
    username_login: bool = False


class AdminUserUpdate(BaseModel):
    userId: int
    token: Optional[float] = None
    discount: Optional[float] = None
    money_rate: Optional[float] = None
    is_delete: Optional[bool] = None
    is_staff: Optional[bool] = None
    username: Optional[str] = None
    password: Optional[str] = None
    username_login: Optional[bool] = None


class AdminFeedbackQuery(BaseModel):
    page: int = Field(1, ge=1)
    page_num: int = Field(10, ge=1, le=50)
    only_unread: bool = False


class AdminFeedbackUpdate(BaseModel):
    id: int
    is_read: Optional[bool] = None
    is_delete: Optional[bool] = None
    reply: Optional[str] = Field(None, description="管理员公开回复，空字符串表示清空")


class AdminOrderQuery(BaseModel):
    page: int = Field(1, ge=1)
    page_num: int = Field(10, ge=1, le=50)
    userId: Optional[int] = None
