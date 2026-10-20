# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:54 下午
# @Author  : rabbit
# @File    : public_schemas.py
# @Software: PyCharm
from typing import Union

from pydantic import BaseModel


# 响应体公共类
class ResponseOwn(BaseModel):
    code: Union[str, int]
    codeMsg: str
    data: str = ""
