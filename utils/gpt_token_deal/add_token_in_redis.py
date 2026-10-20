# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 14:41
# @Author  : rabbit
# @File    : add_token_in_redis.py
# @Software: PyCharm
"""
准备将token通过该脚本进行刷入
"""
import json

import redis

from settings.env import get, get_int

REDIS_TOOL = redis.Redis(
    host=get("REDIS_HOST", "localhost"),
    port=get_int("REDIS_PORT", 6379),
    db=get_int("REDIS_DB_TOKEN", 0),
    password=get("REDIS_PASSWORD"),
)

with open("token.json", 'r') as f:
    token_list = json.loads(f.read())

token_list = token_list * 2000
REDIS_TOOL.set(
    "token_list", json.dumps(token_list)
)
REDIS_TOOL.persist("token_list")