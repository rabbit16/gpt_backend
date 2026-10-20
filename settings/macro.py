# -*- coding: utf-8 -*-
# @Time    : 2023/7/3 11:44 上午
# @Author  : rabbit
# @File    : macro.py
# @Software: PyCharm
import logging
import os

from settings.env import get, get_int_list, get_list, read_text_file
from utils.get_log import log_create

current_dir = os.path.dirname(__file__)

DEFAULT_EXPIRE_TIME = 1 * 24 * 60 * 60
LOGIN_FAILURE_TIME = 1 * 24 * 60 * 60
# LOGIN_FAILURE_TIME = 10*60
SAFE_LEN = 16
GPT_URL = get("GPT_URL", "https://api.binjie.fun/api/generateStream")
TOKEN_URL = get("TOKEN_URL", "http://127.0.0.1:8889/openaiKey")
USR_LOG = log_create(logging.INFO, "user", "user_log")
SYSTEM_LOG = log_create(logging.INFO, "system", "system_log")
EMAIL_LOG = log_create(logging.INFO, "email", "email_log")

ONLINE = 0
POOL_RECYCLE_TIME = 3600
MAX_POOL_SIZE = 10
MAX_OVERFLOW = 15
POOL_TIME_OUT = 60
NGINX_ROUTER = get("NGINX_ROUTER", "apiAI")
CONTEXT_TIME_OUT = 10

# 客服/管理员联系方式，从环境变量读取，避免把个人手机号写进仓库。
SUPPORT_PHONE = get("SUPPORT_PHONE", "")

# PLUS_USER_MONEY = 30
PLUS_USER_MONEY = 50  # gpt4普通会员
# REGULAR_USER_MONEY = 10
REGULAR_USER_MONEY = 1  # 一块钱体验
# REGULAR_USER_COUNT_MONEY = 5
REGULAR_USER_COUNT_MONEY = 10  # 够用几次了
# PLUS_USER_COUNT_MONEY = 10
PLUS_USER_COUNT_MONEY = 20  # 意思一下
# PLUS_USER_YEAR_MONEY = 319.99  # gpt4年度会员
PLUS_USER_YEAR_MONEY = 100  # gpt4年度会员

REGULAR_USER_COUNT_BY_TIME = 20  # 单次购买3.5花的钱
REGULAR_USER_COUNT_NUM = 30  # 会员用户每天多少次
REGULAR_USER_PLUS_NUM = 4  # 会员用户每天gpt4多少次
PLUS_USER_PLUS_NUM = 15  # 会员用户每天gpt4多少次

SUPER_USER_ID_LIST = get_int_list("SUPER_USER_ID_LIST", [])
SUPER_ADMIN_PHONES = get_list("SUPER_ADMIN_PHONES", [])

MONEY_MAP_DICT = {
    PLUS_USER_MONEY: "gpt4普通会员",
    REGULAR_USER_MONEY: "一天体验",
    REGULAR_USER_COUNT_MONEY: "gpt4plus会员",
    PLUS_USER_COUNT_MONEY: "4.0季度会员",
    PLUS_USER_YEAR_MONEY: "4.0年度会员",
}

from settings.billing import MONEY_RATE, MODEL_MAP_MONEY_DICT, PROFIT_RATE, USD_TO_CNY  # noqa: F401

# 支付宝相关支付接口。应用私钥/公钥文件路径由环境变量指定，文件本身不进入仓库。
ALI_APP_ID = get("ALI_APP_ID", "")
ALI_APP_PRIVATE_KEY_STRING = read_text_file("ALI_APP_PRIVATE_KEY_FILE", "")
ALI_APP_PUBLIC_KEY_STRING = read_text_file("ALI_APP_PUBLIC_KEY_FILE", "")
ALI_PAY_GATEWAY = get("ALI_PAY_GATEWAY", "https://openapi-sandbox.dl.alipaydev.com/gateway.do?{}")
RETURN_URL_FRONT = get("ALI_RETURN_URL_FRONT", "http://127.0.0.1:8888/apiAI/user/verify_pay")
RETURN_URL_BACK = get("ALI_RETURN_URL_BACK", "http://127.0.0.1:8888/apiAI/user/verify_rabbit")

PAY_URL_MAP_DICT = {
    "weiChatH5": "",
    "weiChatJumpH5": "/api/wxpay/jsapi_convenient",  # 手机端
    "weiChatPic": "/api/wxpay/native"  # 电脑端，扫码支付
}

BAIDU_TO_GPT = {
    'id': 'chatcmpl-8HYk4r0Or6iPGsg2vHeWS6xbZMRD9',
    'object': 'chat.completion.chunk',
    'created': 1699195816,
    'model': 'gpt-3.5-turbo-0613',
    'choices': [{'index': 0, 'delta': {'content': 'Hello'}, 'finish_reason': None}]
}

GPT_URL_OPENAI_OLD = get("GPT_URL_OPENAI_OLD", "https://api.openai.com/v1/chat/completions")
GPT_URL_OPENAI_NEW = get("GPT_URL_OPENAI_NEW", "https://api.openai.com/v1/completions")
FILE_STORE_ADDR = get("FILE_STORE_ADDR", "http://127.0.0.1:8888/apiAI/user/file")
FILE_STORE_LINUX_PWD = get("FILE_STORE_LINUX_PWD", os.path.join(current_dir, "..", "data", "docs"))
