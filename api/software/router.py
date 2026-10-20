from fastapi import APIRouter, Depends

from api.software.schemas import (
    CategoryCreate,
    CategoryListQuery,
    CategoryUpdate,
    SoftwareCreate,
    SoftwareListQuery,
    SoftwareUpdate,
)
from api.software.service import software_service
from settings.dependencies import CommonQueryParams

router = APIRouter()


@router.post("/software/category/list")
def list_software_category(common: CommonQueryParams = Depends()):
    return software_service.list_categories_public(common)


@router.post("/software/list")
def list_software(request_body: SoftwareListQuery, common: CommonQueryParams = Depends()):
    return software_service.list_public(request_body, common)


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
