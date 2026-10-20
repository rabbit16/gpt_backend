# -*- coding: utf-8 -*-
# @Time    : 2023/12/3 19:13
# @Author  : rabbit
# @File    : gpt_draw.py
# @Software: PyCharm
"""通过站内 TeamRouter 中转（claude_proxy）调用图像生成。

默认请求 {LLM_PROXY_BASE}/images/generations，地址由 LLM_PROXY_BASE 配置，
用用户手机号作为 Bearer（与对话一致），由中转层扣费。
"""
import base64
import time
from pathlib import Path
from uuid import uuid4

import requests

from settings.billing import DEFAULT_IMAGE_MODEL, parse_image_mode
from settings.env import get
from settings.macro import FILE_STORE_LINUX_PWD, USR_LOG

# 站内图像中转地址，可用 LLM_PROXY_BASE 覆盖。
LLM_PROXY_BASE = (get("LLM_PROXY_BASE", "http://127.0.0.1:8888/v1") or "").rstrip("/")


def draw_pic_func(prompt, mode, api_key=None, size="1024x1024"):
    model, quality = parse_image_mode(mode)
    model = model or DEFAULT_IMAGE_MODEL
    quality = quality or "auto"
    if not api_key:
        raise ValueError("缺少用户手机号/API Key，无法调用 TeamRouter 图像接口")

    request_body = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": size or "1024x1024",
        "quality": quality if quality in {"low", "medium", "high", "auto"} else "auto",
        "response_format": "b64_json",
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = f"{LLM_PROXY_BASE}/images/generations"
    last_error = None
    for attempt in range(1, 5):
        try:
            response = requests.post(url, json=request_body, headers=headers, timeout=180)
            payload = response.json() if response.content else {}
            if response.status_code >= 400:
                detail = payload.get("error") or payload.get("codeMsg") or response.text
                raise RuntimeError(f"图像上游错误 ({response.status_code}): {detail}")
            data = payload.get("data") or []
            if not data:
                raise RuntimeError("图像上游未返回 data")
            item = data[0] or {}
            b64_json = item.get("b64_json")
            if b64_json:
                user_dir = Path(FILE_STORE_LINUX_PWD) / "draw"
                user_dir.mkdir(parents=True, exist_ok=True)
                filename = f"{uuid4().hex}.png"
                file_path = user_dir / filename
                file_path.write_bytes(base64.b64decode(b64_json))
                USR_LOG.info(f"TeamRouter 绘图已保存: {file_path} model={model}")
                return f"/apiAI/user/file/image?filename={filename}"
            remote_url = item.get("url")
            if remote_url:
                return remote_url
            raise RuntimeError("图像上游未返回 b64_json/url")
        except Exception as exc:
            last_error = exc
            USR_LOG.warning(f"TeamRouter 绘图失败 attempt={attempt} err={exc}")
            time.sleep(min(2 * attempt, 6))
    USR_LOG.error(f"TeamRouter 绘图最终失败: {last_error}")
    return "请稍后再试，当前图像服务繁忙或余额不足"
