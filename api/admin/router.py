from fastapi import APIRouter, Depends

from api.admin.schemas import (
    AdminFeedbackQuery,
    AdminFeedbackUpdate,
    AdminOrderQuery,
    AdminPageQuery,
    AdminUserCreate,
    AdminUserUpdate,
)
from api.admin.service import admin_service
from settings.dependencies import CommonQueryParams

router = APIRouter()


@router.post("/admin/overview")
def admin_overview(common: CommonQueryParams = Depends()):
    return admin_service.overview(common)


@router.post("/admin/users")
def admin_users(request_body: AdminPageQuery, common: CommonQueryParams = Depends()):
    return admin_service.list_users(request_body, common)


@router.post("/admin/user/create")
def admin_user_create(request_body: AdminUserCreate, common: CommonQueryParams = Depends()):
    return admin_service.create_user(request_body, common)


@router.post("/admin/user/update")
def admin_user_update(request_body: AdminUserUpdate, common: CommonQueryParams = Depends()):
    return admin_service.update_user(request_body, common)


@router.post("/admin/feedback")
def admin_feedback(request_body: AdminFeedbackQuery, common: CommonQueryParams = Depends()):
    return admin_service.list_feedback(request_body, common)


@router.post("/admin/feedback/update")
def admin_feedback_update(request_body: AdminFeedbackUpdate, common: CommonQueryParams = Depends()):
    return admin_service.update_feedback(request_body, common)


@router.post("/admin/orders")
def admin_orders(request_body: AdminOrderQuery, common: CommonQueryParams = Depends()):
    return admin_service.list_orders(request_body, common)
