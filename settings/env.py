# -*- coding: utf-8 -*-
"""统一的环境变量读取入口。

所有敏感配置（数据库、Redis、第三方密钥、支付证书等）只从环境变量或项目根目录的
``.env`` 读取。仓库中只提供 ``.env.example`` 模板，真实 ``.env`` 不进入版本控制。
"""
import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# .env 缺失时不会抛错，方便在容器中完全用环境变量注入。
load_dotenv(BASE_DIR / ".env")


def get(name, default=None):
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def get_int(name, default=0):
    value = get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_float(name, default=0.0):
    value = get(name)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_bool(name, default=False):
    value = get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_list(name, default=None):
    value = get(name)
    if value is None:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def get_int_list(name, default=None):
    result = []
    for item in get_list(name, default=None):
        try:
            result.append(int(item))
        except ValueError:
            continue
    if result:
        return result
    return list(default or [])


def get_json(name, default=None):
    value = get(name)
    if value is None:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def get_path(name, default=None):
    value = get(name)
    if value is None:
        return Path(default) if default is not None else None
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


def read_text_file(name, default=""):
    """读取 .env 指定路径的文本内容，文件不存在时返回 default。"""
    path = get_path(name)
    if path is None or not path.exists():
        return default
    return path.read_text(encoding="utf-8")
