from typing import List, Optional

from pydantic import BaseModel, Field


class SoftwareLink(BaseModel):
    label: str = Field(..., description="链接名称，如百度网盘")
    url: str = Field(..., description="第三方下载地址")
    code: Optional[str] = Field("", description="提取码，可空")


class SoftwarePlatformInput(BaseModel):
    platform: str = Field(..., description="windows / macos / linux")
    file_url: str = Field("", description="安装包直链或网盘地址")
    file_size: Optional[float] = Field(None, description="字节数，未知可省略")
    version: Optional[str] = Field(None, description="该平台单独版本号，不传回退顶层 version")


class SoftwareListQuery(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    page_num: int = Field(12, ge=1, le=50, description="每页条数")
    category_id: Optional[int] = Field(None, description="分类筛选，空表示全部")
    keyword: Optional[str] = Field(None, description="按名称和简介搜索")
    source: Optional[str] = Field(None, description="official / user，空表示全部")


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
    platforms: List[SoftwarePlatformInput] = []
    # 兼容期单数写法：等价于 platforms 只有一个元素
    platform: Optional[str] = None
    file_url: Optional[str] = None
    file_size: Optional[float] = None
    changelog: str = ""
    repo_url: str = ""
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
    platforms: Optional[List[SoftwarePlatformInput]] = None
    platform: Optional[str] = None
    file_url: Optional[str] = None
    file_size: Optional[float] = None
    changelog: Optional[str] = None
    repo_url: Optional[str] = None
    status: Optional[int] = None
    sort: Optional[int] = None
    is_delete: Optional[bool] = None


class UserSoftwareSubmit(BaseModel):
    """用户投稿，服务端强制 source=user、review_status=pending、status=0。"""

    name: str = Field(..., description="软件名称")
    summary: str = Field("", description="简介")
    category_id: Optional[int] = Field(None, description="分类 id")
    version: str = Field("", description="版本号")
    platforms: List[SoftwarePlatformInput] = Field(default_factory=list, description="1-3 个平台的安装包")
    changelog: Optional[str] = Field("", description="更新说明")
    repo_url: Optional[str] = Field("", description="代码仓库地址")


class ReviewListQuery(BaseModel):
    status: Optional[str] = Field(None, description="pending / approved / rejected / all")
    page: int = Field(1, ge=1)
    page_num: int = Field(10, ge=1, le=50)


class ReviewAction(BaseModel):
    id: int
    action: str = Field(..., description="approve 通过 / reject 驳回")
    note: Optional[str] = Field("", description="驳回原因，reject 时必填")
