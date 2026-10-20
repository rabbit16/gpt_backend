# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:57 下午
# @Author  : rabbit
# @File    : dependencies.py
# @Software: PyCharm

from fastapi import Request, Depends
from sqlalchemy.orm import Session

from settings.database import SessionLocal
from settings.env import get, get_int


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


import redis

REDIS_HOST = get("REDIS_HOST", "localhost")
REDIS_PORT = get_int("REDIS_PORT", 6379)
REDIS_PASSWORD = get("REDIS_PASSWORD")
REDIS_MAX_CONNECTIONS = get_int("REDIS_MAX_CONNECTIONS", 20)


def _redis_client(db_index):
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=db_index,
        password=REDIS_PASSWORD,
        max_connections=REDIS_MAX_CONNECTIONS,
        decode_responses=False,
    )


# 创建Redis连接
REDIS_TOOL = _redis_client(get_int("REDIS_DB_TOOL", 3))
REDIS_TOKEN_TOOL = _redis_client(get_int("REDIS_DB_TOKEN", 0))  # token登录的redis库
REDIS_BILL_TOOL = _redis_client(get_int("REDIS_DB_BILL", 1))  # 订单redis库
REDIS_SIGN_TOOL = _redis_client(get_int("REDIS_DB_SIGN", 2))  # gpt的key库
REDIS_SMI_CODE = _redis_client(get_int("REDIS_DB_SMI_CODE", 3))  # 验证码的redis库
REDIS_USER_MESSAGE = _redis_client(get_int("REDIS_DB_USER_MESSAGE", 4))  # 用户权限的redis库
REDIS_USER_ASK = _redis_client(get_int("REDIS_DB_USER_ASK", 5))  # 用户权限的redis库
REDIS_USER_ASK_TOKEN = _redis_client(get_int("REDIS_DB_USER_ASK_TOKEN", 6))  # 用户问题的临时存储库，保证生成的token是正确的


# 该类包含了请求元数据和数据库对象
class   CommonQueryParams:
    def __init__(self, request: Request, db: Session = Depends(get_db)):
        self.request = request
        self.db = db
        # self.redis = redis_tool
