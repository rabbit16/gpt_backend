# -*- coding: utf-8 -*-
# @Time    : 2023/10/22 09:24
# @Author  : rabbit
# @File    : blue_rabbit_pay.py
# @Software: PyCharm
import http.client
import json
import time
from urllib.parse import parse_qs

import urllib.parse
import hashlib
from collections import OrderedDict

from settings.dependencies import REDIS_SIGN_TOOL
from settings.env import get
from settings.macro import PRODUCT_NAME, RETURN_URL_BACK

# 蓝兔支付（ltzf）商户配置，全部从环境变量读取。
LTZF_MCH_ID = get("LTZF_MCH_ID", "")
LTZF_PARTNER_KEY = get("LTZF_PARTNER_KEY", "")
LTZF_API_HOST = get("LTZF_API_HOST", "api.ltzf.cn")
LTZF_QUIT_URL = get("LTZF_QUIT_URL", "")
LTZF_RETURN_URL = get("LTZF_RETURN_URL", "")


def package_sign(params, url_encoder):
    # Sort the parameters according to their parameter name in dictionary order
    sorted_params = OrderedDict(sorted(params.items()))
    sb = []
    sort_format = OrderedDict()
    for key, value in sorted_params.items():
        if not value or key not in ["mch_id", "out_trade_no", "total_fee", "body", "timestamp", "notify_url"]:
            continue
        sb.append(f"{key}={url_encode(value)}" if url_encoder else f"{key}={value}")
        sort_format[key] = value
    print('&'.join(sb))
    return '&'.join(sb), sort_format


def url_encode(src):
    return urllib.parse.quote_plus(src).replace("+", "%20")


def create_sign(params, partner_key):
    # Remove sign before generating signature
    params.pop("sign", None)
    string_a, sort_format = package_sign(params, False)
    string_sign_temp = string_a + "&key=" + partner_key
    sign = md5(string_sign_temp).upper()
    # parsed_data = parse_qs(params)
    REDIS_SIGN_TOOL.set(params["out_trade_no"], sign)
    return sign, string_sign_temp


def md5(src):
    m = hashlib.md5()
    m.update(src.encode('utf-8'))
    return m.hexdigest()

def create_pay(code_num, pay_url, money_num):
    if not LTZF_MCH_ID or not LTZF_PARTNER_KEY:
        raise RuntimeError("未配置 LTZF_MCH_ID / LTZF_PARTNER_KEY，请在 .env 中设置")
    t = time.time()
    query_format = {
        "mch_id": LTZF_MCH_ID,  # 必填
        "out_trade_no": code_num,  # 必填
        "total_fee": money_num,  # 必填
        "body": PRODUCT_NAME,  # 必填：收银台展示的商品名称，全站统一
        "timestamp": str(int(t)),  # 必填
        "notify_url": RETURN_URL_BACK,  # 必填
        "quit_url": LTZF_QUIT_URL,
        "return_url": LTZF_RETURN_URL,
        "time_expire": "1m",
        "sign": ""
    }
    sign, string_param = create_sign(query_format, LTZF_PARTNER_KEY)
    string_param += f"&sign={sign}&return_url={LTZF_RETURN_URL}"
    string_param = string_param.replace(f"key={LTZF_PARTNER_KEY}", "")
    conn = http.client.HTTPSConnection(LTZF_API_HOST)
    headers = {'content-type': "application/x-www-form-urlencoded"}
    conn.request("POST", pay_url, string_param, headers)
    res = conn.getresponse()
    data = res.read()
    return json.loads(data.decode("utf-8"))

if __name__ == '__main__':
    # print(create_pay(None))
    pass