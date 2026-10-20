# -*- coding: utf-8 -*-
# @Time    : 2023/11/28 13:52
# @Author  : rabbit
# @File    : send_sms_tele_code.py
# @Software: PyCharm
import hashlib
import random
import time

import requests

from settings.env import get

SMS_API_URL = get("SMS_API_URL", "https://api.netease.im/sms/sendcode.action")
SMS_APP_KEY = get("SMS_APP_KEY", "")
SMS_APP_SECRET = get("SMS_APP_SECRET", "")


def send_code(mobile):
    """网易云信短信验证码。AppKey/AppSecret 从环境变量读取。"""
    if not SMS_APP_KEY or not SMS_APP_SECRET:
        raise RuntimeError("未配置 SMS_APP_KEY / SMS_APP_SECRET，请在 .env 中设置")
    # 生成128个长度以内的随机字符串
    nonce = hashlib.new('sha512', str(time.time()).encode("utf-8")).hexdigest()
    # 获取当前时间戳
    curtime = str(int(time.time()))
    # 根据要求进行SHA1哈希计算
    check_sum = hashlib.sha1((SMS_APP_SECRET + nonce + curtime).encode("utf-8")).hexdigest()
    code_sms = ''.join(str(random.randint(0, 9)) for _ in range(4))
    header = {
        "AppKey": SMS_APP_KEY,
        "Nonce": nonce,
        "CurTime": curtime,
        "CheckSum": check_sum,
    }
    data = {
        'mobile': mobile,
        "authCode": code_sms,
    }
    resp = requests.post(SMS_API_URL, data=data, headers=header, timeout=10)
    print("Response:", resp.content.decode())
