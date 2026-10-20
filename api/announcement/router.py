from fastapi import APIRouter, Depends

from api.announcement.schemas import (
    AnnouncementCreate,
    AnnouncementListQuery,
    AnnouncementUpdate,
)
from api.announcement.service import announcement_service
from settings.dependencies import CommonQueryParams

router = APIRouter()


@router.post("/announcement/list")
def list_announcement(request_body: AnnouncementListQuery, common: CommonQueryParams = Depends()):
    return announcement_service.list_public(request_body, common)


@router.post("/announcement/latest")
def latest_announcement(common: CommonQueryParams = Depends()):
    return announcement_service.latest(common)


@router.post("/admin/announcement")
def admin_list_announcement(request_body: AnnouncementListQuery, common: CommonQueryParams = Depends()):
    return announcement_service.list_admin(request_body, common)


@router.post("/admin/announcement/create")
def admin_create_announcement(request_body: AnnouncementCreate, common: CommonQueryParams = Depends()):
    return announcement_service.create(request_body, common)


@router.post("/admin/announcement/update")
def admin_update_announcement(request_body: AnnouncementUpdate, common: CommonQueryParams = Depends()):
    return announcement_service.update(request_body, common)
