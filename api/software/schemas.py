from typing import List, Optional

from pydantic import BaseModel, Field


class SoftwareLink(BaseModel):
    label: str = Field(..., description="链接名称，如百度网盘")
    url: str = Field(..., description="第三方下载地址")
    code: Optional[str] = Field("", description="提取码，可空")


class SoftwareListQuery(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_num: int = Field(12, ge=1, le=50, description="每页条数")
    category_id: Optional[int] = Field(None, description="分类筛选，空表示全部")
    keyword: Optional[str] = Field(None, description="按名称和简介搜索")


class CategoryListQuery(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_num: int = Field(10, ge=1, le=200, description="每页条数")


class CategoryCreate(BaseModel):
    name: str = Field(..., description="分类名称")
    status: int = Field(1, description="1 上线 / 0 下线")
    sort: int = Field(0, description="排序，数字越大越靠前")


class CategoryUpdate(BaseModel):
    id: int
    name: Optional[str] = None
    status: Optional[int] = None
    sort: Optional[int] = None
    is_delete: Optional[bool] = None


class SoftwareCreate(BaseModel):
    category_id: int
    name: str
    summary: str = ""
    cover_url: str = ""
    version: str = ""
    links: List[SoftwareLink] = []
    status: int = Field(1, description="1 上线 / 0 下线")
    sort: int = Field(0, description="排序，数字越大越靠前")


class SoftwareUpdate(BaseModel):
    id: int
    category_id: Optional[int] = None
    name: Optional[str] = None
    summary: Optional[str] = None
    cover_url: Optional[str] = None
    version: Optional[str] = None
    links: Optional[List[SoftwareLink]] = None
    status: Optional[int] = None
    sort: Optional[int] = None
    is_delete: Optional[bool] = None
