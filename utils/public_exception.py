# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:53 下午
# @Author  : rabbit
# @File    : public_exception.py
# @Software: PyCharm

# ner接口的错误处理类
class UnicornException(Exception):
    def __init__(self, status_code, detail):
        self.code = status_code
        self.codeMsg = detail
        self.data = ""
