# -*- coding: utf-8 -*-
# @Time    : 2023/8/11 23:43
# @Author  : rabbit
# @File    : get_log.py
# @Software: PyCharm
# import logging
from loguru import logger
import os.path
import re
from logging.handlers import TimedRotatingFileHandler

current_dir = os.path.dirname(__file__)


# def log_create(log_level, log_name, filename):
#     # 这里注册每个抽象模块下的日志记录器
#     logger = logging.Logger(log_name)
#     fh = TimedRotatingFileHandler(filename=f'{os.path.abspath(os.path.join(current_dir, ".."))}/log/{filename}.log', when='D', interval=1, backupCount=7)
#     fh.suffix = "%Y-%m-%d_%H-%M.log"
#     fh.extMatch = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}.log$")
#     # l = logging.FileHandler('log/{}.log'.format(filename))
#     # l.setLevel(log_level)
#     # l.setFormatter(ner_relation_format)
#     fh.setLevel(log_level)
#     ner_relation_format = logging.Formatter("%(asctime)s - %(levelname)s - %(pathname)s: %(message)s")
#     fh.setFormatter(ner_relation_format)
#     logger.addHandler(fh)
#     return logger

def user_filter(record):
    return "user" in record["extra"]["name"]


def system_filter(record):
    return "system" in record["extra"]["name"]


def email_filter(record):
    return "email" in record["extra"]["name"]


def pay_filter(record):
    return "pay" in record["extra"]["name"]


map_dict = {
    "user": user_filter,
    "system": system_filter,
    "email": email_filter,
    "pay": pay_filter
}


def log_create(log_level, bind_info, filename):
    global map_dict
    logger.add(
        f'{os.path.abspath(os.path.join(current_dir, ".."))}/log/{filename}.log',
        format="{time}----{level}----{message}",
        level=log_level,
        rotation="100 MB",
        filter=map_dict[bind_info]
    )
    return logger.bind(name=bind_info)
