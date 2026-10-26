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
    # 微信支付 v3 回调与下单自检，微信服务器不携带登录 token
    "/apiAI/user/wxpay/notify",
    "/apiAI/user/wxpay/status",
    # 虎皮椒回调与自检，虎皮椒服务器不携带登录 token
    "/apiAI/user/xunhupay/notify",
    "/apiAI/user/xunhupay/status",
    # 全站支付通道开关，登录前也要读取，不含任何敏感信息
    "/apiAI/user/pay/channel",
    "/apiAI/user/feedback",
    "/apiAI/user/feedback/list",
    "/apiAI/user/announcement/list",
    "/apiAI/user/announcement/latest",
    "/apiAI/user/software/category/list",
    "/apiAI/user/software/list",
    "/apiAI/user/software/detail",
    # 软件商城公开列表/详情，游客也要能浏览（详情对未审记录会二次校验作者身份）
    "/apiAI/user/open-source/projects",
}

# 前缀放行的路径：安装包下载链接是给浏览器直接点的，带不上登录头
PUBLIC_PATH_PREFIXES = (
    "/apiAI/user/software/download/",
)

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

        is_public = request_url.path in PUBLIC_PATHS or request_url.path.startswith(PUBLIC_PATH_PREFIXES)
        if not is_public and request.method.lower() not in ["options", "fetch"]:
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
            # 原来是「没 token 且没 referer 就回 {"code":0} 成功」的兜底，
            # 那是给早年某个无 token 轮询接口留的。现在前端任何写操作都带 token，
            # 这种空壳响应会让前端把「未登录」误判成提交成功（用户以为申请成功，
            # 站长后台却一条都收不到）。统一按未登录处理，前端会弹登录框。
            SYSTEM_LOG.info(f"接口{request_url.path}, 方法: {request.method}耗时: {time.time() - start_time}")
            return json_response({
                "code": str(Code.USER_EXPIRE),
                "codeMsg": ERROR_MAP[Code.USER_EXPIRE],
            })

        response = await call_next(request)
        SYSTEM_LOG.info(f"接口{request_url.path}, 方法: {request.method}耗时: {time.time() - start_time}")
        return response

    return check_login
