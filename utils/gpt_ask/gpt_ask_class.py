# -*- coding: utf-8 -*-
import requests
import openai
from openai import OpenAI

from settings.env import get
from settings.macro import USR_LOG, GPT_URL_OPENAI_OLD, GPT_URL_OPENAI_NEW

OPENAI_API_KEY = get("OPENAI_API_KEY", "")
OPENAI_ORG_ID = get("OPENAI_ORG_ID", "")
# 可选 HTTP 代理，例如 http://127.0.0.1:7890；留空表示直连。
OPENAI_PROXY = get("OPENAI_PROXY", "")

openai.organization = OPENAI_ORG_ID
openai.api_key = OPENAI_API_KEY

_client = None


def _openai_client():
    """延迟创建 OpenAI 客户端：缺少密钥时在调用处报错，而不是 import 阶段就崩。"""
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("未配置 OPENAI_API_KEY，请在 .env 中设置")
        _client = OpenAI(api_key=OPENAI_API_KEY, organization=OPENAI_ORG_ID or None)
    return _client


class GptAsk:
    def __init__(self, url=None):
        self.url = url

    def ask_gpt_single(self, prompt, model="gpt-3.5-turbo-16k"):
        response = _openai_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "需要你换一个语气和风格对我给你的话进行改写，保证内容的意思不变，改写的字数接近。仅输出改写后的内容即可，并附带基本的文本段落格式。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.95,
            stream=False
        )
        return response.choices[0].message, response.usage.completion_tokens, response.usage.prompt_tokens

    def ask_gpt_by_stream(self, prompt, model="gpt-3.5-turbo-16k", context=None):
        context = context or []
        ask_context = list(context)
        ask_context.append({"role": "user", "content": prompt})
        if not OPENAI_API_KEY:
            raise RuntimeError("未配置 OPENAI_API_KEY，请在 .env 中设置")
        USR_LOG.info("正在调用 OpenAI 接口, model={}".format(model))
        request_headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        url = GPT_URL_OPENAI_NEW if "instruct" in model else GPT_URL_OPENAI_OLD
        proxies = {"http": OPENAI_PROXY, "https": OPENAI_PROXY} if OPENAI_PROXY else None
        request_body = {
            "model": model,
            "messages": ask_context,
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": 1,
        }
        try:
            response = requests.post(
                headers=request_headers,
                json=request_body,
                stream=True,
                url=url,
                timeout=60,
                proxies=proxies,
            )
            if response.status_code >= 400 and "stream_options" in request_body:
                response.close()
                request_body.pop("stream_options", None)
                response = requests.post(
                    headers=request_headers,
                    json=request_body,
                    stream=True,
                    url=url,
                    timeout=60,
                    proxies=proxies,
                )
            return response
        except Exception as e:
            if "gpt-4" not in model:
                raise
            USR_LOG.warning(f"""发生错误{e}， 开使用0613的gpt4""")
            request_body["model"] = "gpt-4-0613"
            return requests.post(
                headers=request_headers,
                json=request_body,
                stream=True,
                url=GPT_URL_OPENAI_OLD,
                timeout=60,
                proxies=proxies,
            )
