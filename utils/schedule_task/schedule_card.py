# -*- coding: utf-8 -*-
# @Time    : 2023/8/31 23:34
# @Author  : rabbit
# @File    : schedule_card.py
# @Software: PyCharm
import time

import requests
import schedule

from settings.env import get

CHECKIN_URL = get("SOCKBOOM_CHECKIN_URL", "")
CHECKIN_TOKEN = get("SOCKBOOM_TOKEN", "")


def daily_task():
    if not CHECKIN_URL or not CHECKIN_TOKEN:
        return
    r = requests.get(url=CHECKIN_URL, json={"token": CHECKIN_TOKEN}, timeout=10)
    print(r.text)


schedule.every().day.at("00:00").do(daily_task)

while True:
    schedule.run_pending()
    time.sleep(1)