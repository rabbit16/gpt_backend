# -*- coding: utf-8 -*-
# @Time    : 2023/9/15 23:30
# @Author  : rabbit
# @File    : add_answer_num.py
# @Software: PyCharm
import datetime

from api.users.models import User
from settings.dependencies import REDIS_USER_MESSAGE
from settings.macro import REGULAR_USER_MONEY, PLUS_USER_MONEY, REGULAR_USER_COUNT_MONEY, MONEY_MAP_DICT, \
    REGULAR_USER_COUNT_NUM, PLUS_USER_PLUS_NUM, REGULAR_USER_COUNT_BY_TIME, PLUS_USER_COUNT_MONEY, PLUS_USER_YEAR_MONEY


def add_num_by_money(common, money, function_code, user_id, user_log):
    user = common.db.query(User).filter(User.user_id == user_id).first()
    money = float(money)
    if function_code == "chatGpt":
        if money == REGULAR_USER_MONEY:
            common.db.query(User).filter(User.user_id == user_id).update(
                {
                    # "regular_user": user.regular_user + REGULAR_USER_COUNT_NUM,
                    # "plus_user_count": user.plus_user_count + 10,
                    "token": user.token + REGULAR_USER_MONEY,
                    "is_quarter": 2,  # 一天体验
                    "plus_user_expire_time": (datetime.datetime.fromtimestamp(
                        datetime.datetime.now().timestamp()) + datetime.timedelta(days=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                    "regular_user_expire_time": (datetime.datetime.fromtimestamp(
                        datetime.datetime.now().timestamp()) + datetime.timedelta(days=1)).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                }  # 一天体验
            )
            common.db.commit()
            REDIS_USER_MESSAGE.set(user.email, user.email, ex=24*60*60)
        elif money == PLUS_USER_MONEY:
            common.db.query(User).filter(User.user_id == user_id).update(
                {
                    "token": user.token + PLUS_USER_MONEY,
                    "plus_user_count": user.plus_user_count + PLUS_USER_MONEY,
                    "plus_user_expire_time": (
                            datetime.datetime.fromtimestamp(datetime.datetime.now().timestamp()) + datetime.timedelta(
                        days=30)).strftime("%Y-%m-%d %H:%M:%S"),
                    "is_quarter": 4,
                    "regular_user_expire_time": (datetime.datetime.fromtimestamp(
                        datetime.datetime.now().timestamp()) + datetime.timedelta(days=30)).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                }  # gpt4普通会员
            )
            common.db.commit()
        elif money == REGULAR_USER_COUNT_MONEY:
            common.db.query(User).filter(User.user_id == user_id).update(
                {
                    "token": user.token + REGULAR_USER_COUNT_MONEY,
                    "plus_user_count": user.plus_user_count + PLUS_USER_PLUS_NUM*2,
                    "plus_user_expire_time": (
                            datetime.datetime.fromtimestamp(datetime.datetime.now().timestamp()) + datetime.timedelta(
                        days=30)).strftime("%Y-%m-%d %H:%M:%S"),

                    "is_quarter": 3,
                    "regular_user_expire_time": (datetime.datetime.fromtimestamp(
                        datetime.datetime.now().timestamp()) + datetime.timedelta(days=30)).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                }
            )
            common.db.commit()
        elif money == PLUS_USER_COUNT_MONEY:
            common.db.query(User).filter(User.user_id == user_id).update(
                {
                    "token": user.token + PLUS_USER_COUNT_MONEY,
                    "plus_user_count": user.plus_user_count + (PLUS_USER_PLUS_NUM * 4-10),
                    "plus_user_expire_time": (
                            datetime.datetime.fromtimestamp(datetime.datetime.now().timestamp()) + datetime.timedelta(
                        days=90)).strftime("%Y-%m-%d %H:%M:%S"),
                    "is_quarter": 1,  # 季度会员
                    "regular_user_expire_time": (datetime.datetime.fromtimestamp(
                        datetime.datetime.now().timestamp()) + datetime.timedelta(days=90)).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                }
            )
            common.db.commit()
        elif money == PLUS_USER_YEAR_MONEY:
            common.db.query(User).filter(User.user_id == user_id).update(
                {
                    "token": user.token + PLUS_USER_YEAR_MONEY,
                    "plus_user_count": user.plus_user_count + (PLUS_USER_YEAR_MONEY * 4 - 10),
                    "plus_user_expire_time": (
                            datetime.datetime.fromtimestamp(datetime.datetime.now().timestamp()) + datetime.timedelta(
                        days=365)).strftime("%Y-%m-%d %H:%M:%S"),
                    "regular_user_expire_time": (datetime.datetime.fromtimestamp(
                        datetime.datetime.now().timestamp()) + datetime.timedelta(days=365)).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                    "is_year": 1
                }
            )
            common.db.commit()
        else:
            common.db.query(User).filter(User.user_id == user_id).update(
                {
                    "token": user.token + money,
                    "plus_user_count": user.plus_user_count + (PLUS_USER_YEAR_MONEY * 4 - 10),
                    "plus_user_expire_time": (
                            datetime.datetime.fromtimestamp(datetime.datetime.now().timestamp()) + datetime.timedelta(
                        days=365)).strftime("%Y-%m-%d %H:%M:%S"),
                    "regular_user_expire_time": (datetime.datetime.fromtimestamp(
                        datetime.datetime.now().timestamp()) + datetime.timedelta(days=365)).strftime(
                        "%Y-%m-%d %H:%M:%S"),
                    "is_year": 1
                }
            )
            common.db.commit()
        user_log.info(f"用户{user_id}的{function_code}功能， 余额: {user.token+money}")
        return 1
