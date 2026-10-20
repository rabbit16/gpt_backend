# -*- coding: utf-8 -*-
# @Time    : 2023/9/21 15:07
# @Author  : rabbit
# @File    : token_acquire.py
# @Software: PyCharm
# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:55 下午
# @Author  : rabbit
# @File    : main_app.py
# @Software: PyCharm
import json
import time
from contextlib import asynccontextmanager

from contextvars import ContextVar
import random
from typing import Union

import redis
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from lxml import etree
from pydantic import BaseModel
from pyppeteer import launch

async def start_chrome():
    global browser
    browser = await launch()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser
    # Load the ML model
    await start_chrome()
    yield
    # Clean up the ML models and release the resources
    await browser.close()

app = FastAPI(
    debug=True,
    lifespan=lifespan
)
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
custom_var: ContextVar[str] = ContextVar("custom_var", default="")
from settings.env import get, get_int

# redis
REDIS_TOKEN_TOOL = redis.Redis(
    host=get("REDIS_HOST", "localhost"),
    port=get_int("REDIS_PORT", 6379),
    db=get_int("REDIS_DB_TOKEN", 0),
    password=get("REDIS_PASSWORD"),
)


class RequestPrompt(BaseModel):
    prompt: str
    num: Union[int] = 3

# 这里添加中间件来实现请求拦截
@app.post("/openaiKey")
def get_token():
    token_list = REDIS_TOKEN_TOOL.get("token_list")
    token_list = json.loads(token_list)
    key = None
    value = None
    if len(token_list) > 0:
        token_list_random = random.choice(token_list)
        token_list.remove(token_list_random)
        key, value = list(token_list_random.items())[0]
        REDIS_TOKEN_TOOL.set("token_list", json.dumps(token_list))
        return {
            "code": "0",
            "key": key,
            "value": value,
            "count": len(token_list)
        }
    else:
        return {
            "code": "1",
            "key": key,
            "value": value,
            "count": len(token_list)
        }
@app.post("/searchBing")
async def search_bing(request_body: RequestPrompt):
    page = await browser.newPage()
    await page.goto('https://www.google.com/')
    await page.type(".lst", request_body.prompt)
    click_element = await page.xpath("//input[@name='btnG']")
    await click_element[0].click()
    await page.waitForNavigation()
    content = await page.content()
    selector = etree.HTML(content)
    a_list = selector.xpath("//div[@id='main']/div")[4:]
    search_data = []
    try:
        for i in a_list[0:3]:
            title = "".join(i.xpath("./div/div/a//text()"))
            href = "https://www.google.com" + i.xpath("./div/div/a/@href")[0]
            summery = "".join(i.xpath("./div/div[2]//text()"))
            send_format = f"""
                \n\n以下结果来自互联网  
          - 标题(title)：{title}
          - 链接(link) {href}
          - 摘要(summery) {summery}
                         """
            # row_data = {
            #     "snippet": content_format,
            #     "title": title,
            #     "link": link
            # }
            search_data.append(send_format)
    except Exception as e:
        pass
    finally:
        await page.close()
    return {
        "result": "".join(search_data)
    }


if __name__ == '__main__':
    # freeze_support()
    # uvicorn main_app:app --reload --port 8890
    uvicorn.run(app, host="0.0.0.0", port=8889)
