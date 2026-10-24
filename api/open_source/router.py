from typing import Optional

from fastapi import APIRouter, Depends, Query

from api.open_source.schemas import ProjectReview, ProjectSubmit
from api.open_source.service import open_source_service
from settings.dependencies import CommonQueryParams

router = APIRouter()


@router.get("/open-source/projects")
def list_open_source_projects(common: CommonQueryParams = Depends()):
    return open_source_service.list_public(common)


@router.get("/open-source/my-projects")
def list_my_projects(common: CommonQueryParams = Depends()):
    return open_source_service.list_mine(common)


@router.post("/open-source/projects")
def submit_open_source_project(request_body: ProjectSubmit, common: CommonQueryParams = Depends()):
    return open_source_service.submit(request_body, common)


@router.get("/admin/open-source/projects")
def admin_list_open_source_projects(
    status: Optional[str] = Query("pending", description="pending / approved / rejected / all"),
    page: int = Query(1, ge=1),
    page_num: int = Query(20, ge=1, le=50),
    common: CommonQueryParams = Depends(),
):
    query = type("Query", (), {"status": status, "page": page, "page_num": page_num})()
    return open_source_service.admin_list(query, common)


@router.post("/admin/open-source/review")
def review_open_source_project(request_body: ProjectReview, common: CommonQueryParams = Depends()):
    return open_source_service.review(request_body, common)
