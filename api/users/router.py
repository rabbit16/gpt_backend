from fastapi import APIRouter, Depends, Request

from api.users.api_keys import ApiKeyCreate, ApiKeyId, api_key_service
from api.users.response_schemas import UserInfoResponse
from api.users.schemas import (
    PasswordCodeFormat,
    PasswordResetFormat,
    ProfileUpdateFormat,
    UserRequestFormat,
    UserLoginFormat,
    UserInfoQuery,
    UserExist,
)
from api.users.service import user_service
from settings.dependencies import CommonQueryParams
from utils.schemas_pub import ResponsePub

router = APIRouter()


@router.post("/verify")
def login(request: Request, request_body: UserLoginFormat, common: CommonQueryParams = Depends()):
    return user_service.login(request, request_body, common)


@router.post("/logout")
def logout(request: Request):
    return user_service.logout(request)


@router.post("/register", response_model=ResponsePub)
def register(request: Request, request_body: UserRequestFormat, common: CommonQueryParams = Depends()):
    return user_service.register(request, request_body, common)


@router.post("/anonymous/username")
def anonymous_username(common: CommonQueryParams = Depends()):
    return user_service.suggest_anonymous_username(common)


@router.post("/password/send_code")
def send_password_code(request_body: PasswordCodeFormat, common: CommonQueryParams = Depends()):
    return user_service.send_reset_code(request_body, common)


@router.post("/password/reset")
def reset_password(request_body: PasswordResetFormat, common: CommonQueryParams = Depends()):
    return user_service.reset_password(request_body, common)


@router.post("/profile/update")
def update_profile(request_body: ProfileUpdateFormat, common: CommonQueryParams = Depends()):
    return user_service.update_profile(request_body, common)


@router.post("/session")
def current_session(common: CommonQueryParams = Depends()):
    return user_service.current_session(common)


@router.post("/get_user_info", response_model=UserInfoResponse)
def get_single_user_info(request: Request, request_body: UserInfoQuery, common: CommonQueryParams = Depends()):
    return user_service.get_user_info(request_body, common)


@router.post("/userExist")
def user_exist(request_body: UserExist, common: CommonQueryParams = Depends()):
    return user_service.user_exist(request_body, common)


@router.post("/api_key/list")
def list_api_keys(common: CommonQueryParams = Depends()):
    return api_key_service.list_keys(common)


@router.post("/api_key/create")
def create_api_key(request_body: ApiKeyCreate, common: CommonQueryParams = Depends()):
    return api_key_service.create_key(request_body, common)


@router.post("/api_key/disable")
def disable_api_key(request_body: ApiKeyId, common: CommonQueryParams = Depends()):
    return api_key_service.set_active(request_body, common, active=False)


@router.post("/api_key/enable")
def enable_api_key(request_body: ApiKeyId, common: CommonQueryParams = Depends()):
    return api_key_service.set_active(request_body, common, active=True)


@router.post("/api_key/delete")
def delete_api_key(request_body: ApiKeyId, common: CommonQueryParams = Depends()):
    return api_key_service.delete_key(request_body, common)
