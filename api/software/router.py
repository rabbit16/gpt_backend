import re
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from api.software.schemas import (
    CategoryCreate,
    CategoryListQuery,
    CategoryUpdate,
    ReviewAction,
    ReviewListQuery,
    SoftwareCreate,
    SoftwareListQuery,
    SoftwareUpdate,
    UserSoftwareSubmit,
)
from api.software.service import (
    bump_download_count,
    download_display_name,
    resolve_download,
    software_service,
)
from app.http import json_response
from settings.dependencies import CommonQueryParams

router = APIRouter()


@router.post("/software/category/list")
def list_software_category(common: CommonQueryParams = Depends()):
    return software_service.list_categories_public(common)


@router.post("/software/list")
def list_software(request_body: SoftwareListQuery, common: CommonQueryParams = Depends()):
    return software_service.list_public(request_body, common)


@router.get("/software/detail")
def software_detail(id: int = Query(..., description="软件 id"), common: CommonQueryParams = Depends()):
    return software_service.detail(id, common)


@router.get("/software/download/{filename}")
def download_software(filename: str, common: CommonQueryParams = Depends()):
    """站内托管的安装包下载。文件名只允许 ``uuid__原始名.ext``，不做任何路径拼接。

    强制 attachment，避免上传的 html/svg 在站内被浏览器解析执行。
    顺带把该平台的下载次数 +1（失败不影响下载）。
    """
    target = resolve_download(filename)
    if not target:
        return json_response({"code": "4404", "codeMsg": "文件不存在或已删除"})
    bump_download_count(common.db, target.name)
    display_name = download_display_name(target.name)
    # 中文文件名必须走 filename*（RFC 5987），否则部分浏览器会存成乱码
    disposition = "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (
        re.sub(r'[^A-Za-z0-9._-]', "_", display_name),
        quote(display_name),
    )
    return FileResponse(
        target,
        filename=display_name,
        media_type="application/octet-stream",
        headers={"Content-Disposition": disposition},
    )


@router.post("/software/submit")
def submit_software(request_body: UserSoftwareSubmit, common: CommonQueryParams = Depends()):
    return software_service.submit(request_body, common)


@router.get("/software/my-submissions")
def my_software_submissions(common: CommonQueryParams = Depends()):
    return software_service.list_mine(common)


@router.post("/software/upload")
def upload_user_package(
    file: UploadFile = File(...),
    kind: str = Form("package", description="package / cover"),
    common: CommonQueryParams = Depends(),
):
    return software_service.upload_user_file(file, kind, common)


@router.post("/admin/software/upload")
def upload_admin_file(
    file: UploadFile = File(...),
    kind: str = Form("package", description="package / cover"),
    common: CommonQueryParams = Depends(),
):
    return software_service.upload_admin_file(file, kind, common)


@router.get("/admin/software/review/list")
def admin_review_list(
    status: Optional[str] = Query(None, description="pending / approved / rejected / all"),
    page: int = Query(1, ge=1),
    page_num: int = Query(10, ge=1, le=50),
    common: CommonQueryParams = Depends(),
):
    query = ReviewListQuery(status=status, page=page, page_num=page_num)
    return software_service.review_list(query, common)


@router.post("/admin/software/review")
def admin_review_software(request_body: ReviewAction, common: CommonQueryParams = Depends()):
    return software_service.review(request_body, common)


@router.post("/admin/software/category")
def admin_list_software_category(request_body: CategoryListQuery, common: CommonQueryParams = Depends()):
    return software_service.list_categories_admin(request_body, common)


@router.post("/admin/software/category/create")
def admin_create_software_category(request_body: CategoryCreate, common: CommonQueryParams = Depends()):
    return software_service.create_category(request_body, common)


@router.post("/admin/software/category/update")
def admin_update_software_category(request_body: CategoryUpdate, common: CommonQueryParams = Depends()):
    return software_service.update_category(request_body, common)


@router.post("/admin/software")
def admin_list_software(request_body: SoftwareListQuery, common: CommonQueryParams = Depends()):
    return software_service.list_admin(request_body, common)


@router.post("/admin/software/create")
def admin_create_software(request_body: SoftwareCreate, common: CommonQueryParams = Depends()):
    return software_service.create(request_body, common)


@router.post("/admin/software/update")
def admin_update_software(request_body: SoftwareUpdate, common: CommonQueryParams = Depends()):
    return software_service.update(request_body, common)
