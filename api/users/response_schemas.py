# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:59 下午
# @Author  : rabbit
# @File    : ner_relation_schemas.py
# @Software: PyCharm

from typing import Union, List
from pydantic import BaseModel, Field

# 注册返回格式
from utils.public_schemas import ResponseOwn


class RegisterResponse(BaseModel):
    registerDetail: str
    registerFinishTime: str
    userId: int
    userName: str
    telephone: str
    email: str
    code: str
    register_time: str = ""
    allow_phone_key: bool = True
    username: str = ""
    is_anonymous: bool = False


class LoginResponse(BaseModel):
    loginDetail: str
    loginTime: str
    userId: int
    userName: str
    userCode: str
    telephone: str
    email: str
    is_staff: bool = False
    register_time: str = ""
    allow_phone_key: bool = True


class GptAskResponse(ResponseOwn):
    gptResult: Union[list, None] = None


class NewChatResponse(ResponseOwn):
    newChatId: int


class ChatListResponse(ResponseOwn):
    context_dict: list
    allContextNum: int


class PayApiResponse(ResponseOwn):
    payUrl: Union[dict, str] = Field(..., description="这个是支付相关接口")
    userId: int = Field(..., description="用户的id")


class FunctionListResponse(ResponseOwn):
    function_list: List[dict] = Field(..., description="返回功能列表")


class UserBillListResponse(ResponseOwn):
    user_bill_list: List[dict] = Field(..., description="返回订单列表")
    totalNum: int = Field(..., description="总数")


class BillCreateResponse(ResponseOwn):
    pass


class UserInfoResponse(ResponseOwn):
    userMessage: dict = Field(..., description="用户信息")
