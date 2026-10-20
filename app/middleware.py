import time

from fastapi import FastAPI, Request

from app.http import json_response
from settings.dependencies import REDIS_TOOL
from settings.env import get_list
from settings.macro import SYSTEM_LOG
from utils.res_code import Code, ERROR_MAP

PUBLIC_PATHS = {
    "/apiAI/user/logout",
    "/apiAI/user/function_list",
    "/apiAI/user/verify",
    "/apiAI/user/register",
    "/apiAI/user/anonymous/username",
    "/apiAI/user/password/send_code",
    "/apiAI/user/password/reset",
    "/docs",
    "/openapi.json",
    "/favicon.ico",
    "/apiAI/user/mode_list",
    "/apiAI/user/verify_rabbit",
    "/apiAI/user/feedback",
    "/apiAI/user/feedback/list",
    "/apiAI/user/announcement/list",
    "/apiAI/user/announcement/latest",
    "/apiAI/user/software/category/list",
    "/apiAI/user/software/list",
}

SKIP_AUTH_PATHS = {
    "file",
    "/apiAI/user/gpt/ask",
    "/apiAI/user/userExist",
}

DOCS_REFERERS = set(get_list("DOCS_REFERERS", ["http://127.0.0.1:8888/docs"]))

punishment_dict = {}
punishment_list = []


def register_auth_middleware(app: FastAPI):
    @app.middleware("http")
    async def check_login(request: Request, call_next):
        request_url = request.url
        request_host = request.client.host
        if int(time.time()) - punishment_dict.get(request_host, 100) <= 1 and "register" in request_url.path or "python" in request.headers.get("user-agent", ""):
            punishment_list.append(request_host)
        punishment_dict[request_host] = int(time.time())
        SYSTEM_LOG.info(f"访问IP为{request_host}, 请求url {request_url.path}, 请求头: {request.headers}")
        referer = request.headers.get("referer", "")
        header_dict = dict(request.headers.items())
        start_time = time.time()
        if referer in DOCS_REFERERS or "file" in request.url.path or request_url.path in SKIP_AUTH_PATHS:
            response = await call_next(request)
            SYSTEM_LOG.info(f"接口{request_url.path}, 方法: {request.method}耗时: {time.time() - start_time}")
            return response

        if request_url.path not in PUBLIC_PATHS and request.method.lower() not in ["options", "fetch"]:
            token = request.headers.get("token")
            if token or request_url.path == "/apiAI/user/verify_pay":
                user_exists = REDIS_TOOL.exists(f"users:{token}")
                if user_exists or request_url.path == "/apiAI/user/verify_pay":
                    response = await call_next(request)
                    SYSTEM_LOG.info(f"接口{request_url.path}, 方法: {request.method}耗时: {time.time() - start_time}")
                    return response
                SYSTEM_LOG.info(f"接口{request_url.path}, 方法: {request.method}耗时: {time.time() - start_time}")
                request_body = await request.json()
                SYSTEM_LOG.info(f"过期用户发送请求: {request_body}")
                return json_response({
                    "code": str(Code.USER_EXPIRE),
                    "codeMsg": ERROR_MAP[Code.USER_EXPIRE],
                })
            if "referer" not in header_dict and request_url.path not in ["/apiAI/user/verify_rabbit", "/apiAI/user/file"]:
                return json_response({"code": "0", "codeMsg": "成功"})
            SYSTEM_LOG.info(f"接口{request_url.path}, 方法: {request.method}耗时: {time.time() - start_time}")
            return json_response({
                "code": str(Code.USER_EXPIRE),
                "codeMsg": ERROR_MAP[Code.USER_EXPIRE],
            })

        response = await call_next(request)
        SYSTEM_LOG.info(f"接口{request_url.path}, 方法: {request.method}耗时: {time.time() - start_time}")
        return response

    return check_login
