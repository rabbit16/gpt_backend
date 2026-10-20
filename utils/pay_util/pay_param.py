# -*- coding: utf-8 -*-
# @Time    : 2023/8/29 10:39
# @Author  : rabbit
# @File    : pay_param.py
# @Software: PyCharm
"""微信支付 v3 配置读取。

所有值来自环境变量；证书/密钥只填文件路径，内容不进入仓库。
支持两种验签方式：
  * 微信支付公钥（新商户）：配置 WXPAY_PUBLIC_KEY_FILE + WXPAY_PUBLIC_KEY_ID
  * 平台证书（老商户）：不配公钥，由 SDK 自动下载并缓存到 WXPAY_CERT_DIR
"""
import logging

from settings.env import get, read_text_file
from utils.get_log import log_create

# 微信支付商户号，服务商模式下为服务商商户号（sp_mchid）。
MCHID = get("WXPAY_MCHID", "")

# 商户证书私钥，此文件不要放置在 CERT_DIR 目录里。
PRIVATE_KEY = read_text_file("WXPAY_PRIVATE_KEY_FILE", "")

# 微信支付公钥及公钥 ID（新商户模式）。两者要么都配，要么都不配。
PUBLIC_KEY = read_text_file("WXPAY_PUBLIC_KEY_FILE", "")
PUBLIC_KEY_ID = get("WXPAY_PUBLIC_KEY_ID", "")

# 商户证书序列号
CERT_SERIAL_NO = get("WXPAY_CERT_SERIAL_NO", "")

# API v3 密钥，https://pay.weixin.qq.com/wiki/doc/apiv3/wechatpay/wechatpay3_2.shtml
APIV3_KEY = get("WXPAY_APIV3_KEY", "")

# APPID，应用 ID
APPID = get("WXPAY_APPID", "")

# 回调地址
NOTIFY_URL = get("WXPAY_NOTIFY_URL", "")

# 微信支付平台证书缓存目录；公钥模式下不使用。
CERT_DIR = get("WXPAY_CERT_DIR")

# 日志记录器，记录 web 请求和回调细节，便于排错。
LOGGER = log_create(logging.INFO, "pay", "pay")

# 接入模式：False=直连商户模式，True=服务商模式。
PARTNER_MODE = get("WXPAY_PARTNER_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}

# HTTP 超时：(连接, 读取)。避免微信接口抖动拖住整个 worker。
_TIMEOUT_RAW = get("WXPAY_TIMEOUT", "5,15")
try:
    TIMEOUT = tuple(float(item) for item in _TIMEOUT_RAW.split(",", 1))
    if len(TIMEOUT) != 2:
        raise ValueError
except (TypeError, ValueError):
    TIMEOUT = (5, 15)

# 代理设置，None 或 {"https": "http://10.10.1.10:1080"}
PROXY = get("WXPAY_PROXY") or None


def missing_config():
    """返回缺少的必填配置项名称列表，用于启动自检。"""
    required = {
        "WXPAY_MCHID": MCHID,
        "WXPAY_CERT_SERIAL_NO": CERT_SERIAL_NO,
        "WXPAY_APIV3_KEY": APIV3_KEY,
        "WXPAY_APPID": APPID,
        "WXPAY_NOTIFY_URL": NOTIFY_URL,
        "WXPAY_PRIVATE_KEY_FILE": PRIVATE_KEY,
    }
    missing = [name for name, value in required.items() if not value]
    # 公钥模式下两个配置必须成对出现。
    if bool(PUBLIC_KEY) != bool(PUBLIC_KEY_ID):
        missing.extend(
            name for name, value in (
                ("WXPAY_PUBLIC_KEY_FILE", PUBLIC_KEY),
                ("WXPAY_PUBLIC_KEY_ID", PUBLIC_KEY_ID),
            ) if not value
        )
    return missing


def verify_mode():
    """返回当前验签模式：public_key / platform_cert。"""
    return "public_key" if PUBLIC_KEY and PUBLIC_KEY_ID else "platform_cert"
