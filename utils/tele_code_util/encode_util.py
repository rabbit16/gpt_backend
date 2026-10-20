# -*- coding: utf-8 -*-
# @Time    : 2023/11/28 13:51
# @Author  : rabbit
# @File    : encode_util.py
# @Software: PyCharm
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成签名信息
Args:
    secretKey 产品私钥
    params 接口请求参数，不包括signature参数
"""
import hashlib


def gen_signature(secretKey, params=None):
        params_str = ""
        for k in sorted(params.keys()):
            params_str += str(k)+ str(params[k])

        params_str += secretKey
        # python2 语法：  return hashlib.md5(params_str).hexdigest()
        return hashlib.md5(params_str.encode("utf-8")).hexdigest()

