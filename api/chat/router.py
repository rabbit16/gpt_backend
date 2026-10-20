from fastapi import APIRouter, Depends, Request, BackgroundTasks

from api.chat.service import chat_service, GPT_MODE_LIST
from settings.billing import billing_public_config
from api.users.response_schemas import GptAskResponse, NewChatResponse, ChatListResponse
from api.users.schemas import GptAskFormat, CreateNewChatContext, QueryUserContextList, SaveChatContextFormat, SearchChatContext
from app.http import json_response
from settings.dependencies import CommonQueryParams
from utils.res_code import Code, ERROR_MAP

router = APIRouter()


@router.post("/gpt/ask", response_model=GptAskResponse)
def gpt_api(request: Request, request_body: GptAskFormat, common: CommonQueryParams = Depends()):
    return chat_service.ask_once(request_body, common)


@router.post("/gpt/askStream", response_model=GptAskResponse)
def gpt_stream_api(request: Request, request_body: GptAskFormat, background_task: BackgroundTasks,
                   common: CommonQueryParams = Depends()):
    return chat_service.ask_stream(request, request_body, common)


@router.post("/createChat", response_model=NewChatResponse)
def create_chat(request_body: CreateNewChatContext, common: CommonQueryParams = Depends()):
    return chat_service.create_chat(request_body, common)


@router.post("/saveChatMessage")
def save_chat_message(request_body: SaveChatContextFormat, common: CommonQueryParams = Depends()):
    return chat_service.save_chat_context(request_body, common)


@router.post("/deleteChat")
def delete_chat_context(request_body: QueryUserContextList, background_task: BackgroundTasks,
                        common: CommonQueryParams = Depends()):
    return chat_service.delete_chat(request_body, common)


@router.post("/deleteAllChat")
def delete_all_chat_context(request_body: QueryUserContextList, common: CommonQueryParams = Depends()):
    return chat_service.delete_all_chat(request_body, common)


@router.post("/getContextList", response_model=ChatListResponse)
def query_context_list(request: Request, request_body: QueryUserContextList, common: CommonQueryParams = Depends()):
    return chat_service.get_context_list(request_body, common)


@router.post("/searchChat")
def search_chat(request: Request, request_body: SearchChatContext, common: CommonQueryParams = Depends()):
    return chat_service.search_chat(request, request_body, common)


@router.post("/mode_list")
def get_mode_list():
    return json_response({
        "code": str(Code.OK),
        "codeMsg": ERROR_MAP[Code.OK],
        "modeList": GPT_MODE_LIST,
        "billing": billing_public_config(),
        "data": ""
    })
