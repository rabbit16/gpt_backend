from typing import List, Optional

from pydantic import BaseModel, Field


class ProjectReleaseInput(BaseModel):
    platform: str = Field(..., description="windows / macos / linux")
    file_url: str = Field("", description="安装包直链或网盘地址")


class ProjectSubmit(BaseModel):
    """用户提交新项目或新版本，契约见前端 src/request/projects.ts。"""

    name: str = Field("", description="项目名")
    summary: str = Field("", description="一句话介绍")
    description: Optional[str] = Field("", description="详细介绍")
    repo_url: Optional[str] = Field("", description="开源仓库地址")
    version: str = Field("", description="版本号")
    changelog: Optional[str] = Field("", description="更新说明")
    cover_url: Optional[str] = Field("", description="封面图")
    releases: List[ProjectReleaseInput] = Field(default_factory=list, description="各平台安装包")


class ProjectReview(BaseModel):
    id: int = Field(..., description="项目 id")
    action: str = Field(..., description="approve 通过 / reject 驳回")
    note: Optional[str] = Field("", description="审核备注或驳回原因")
