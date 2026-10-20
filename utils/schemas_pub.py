# -*- coding: utf-8 -*-
# @Time    : 2023/7/22 11:00
# @Author  : rabbit
# @File    : schemas_pub.py
# @Software: PyCharm
from typing import Union

from pydantic import BaseModel
from api.users.response_schemas import RegisterResponse


# 公共响应类
class ResponsePub(BaseModel):
    code: Union[str, int]
    codeMsg: str
    bodyMessage: Union[dict, None, RegisterResponse] = None
    data: str = ""
