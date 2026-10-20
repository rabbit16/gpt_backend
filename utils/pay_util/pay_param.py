# -*- coding: utf-8 -*-
# @Time    : 2023/8/29 10:39
# @Author  : rabbit
# @File    : pay_example.py
# @Software: PyCharm
import logging
import os

from settings.env import get
from utils.get_log import log_create

# 微信支付商户号，服务商模式下为服务商户号，即官方文档中的sp_mchid。
MCHID = get("WXPAY_MCHID", "")

# 商户证书私钥，此文件不要放置在下面设置的CERT_DIR目录里。
_PAY_KEY_FILE = get("WXPAY_PRIVATE_KEY_FILE", "/etc/security/apiclient_key.pem")
PRIVATE_KEY = ""
if os.path.exists(_PAY_KEY_FILE):
    with open(_PAY_KEY_FILE) as f:
        PRIVATE_KEY = f.read()

# 商户证书序列号
CERT_SERIAL_NO = get("WXPAY_CERT_SERIAL_NO", "")

# API v3密钥， https://pay.weixin.qq.com/wiki/doc/apiv3/wechatpay/wechatpay3_2.shtml
APIV3_KEY = get("WXPAY_APIV3_KEY", "")

# APPID，应用ID，服务商模式下为服务商应用ID，即官方文档中的sp_appid，也可以在调用接口的时候覆盖。
APPID = get("WXPAY_APPID", "")

# 回调地址，也可以在调用接口的时候覆盖。
NOTIFY_URL = get("WXPAY_NOTIFY_URL", "")

# 微信支付平台证书缓存目录，初始调试的时候可以设为None，首次使用确保此目录为空目录。
CERT_DIR = get("WXPAY_CERT_DIR")

# 日志记录器，记录web请求和回调细节，便于调试排错。
LOGGER = log_create(logging.INFO, "pay", "pay")

# 接入模式：False=直连商户模式，True=服务商模式。
PARTNER_MODE = get("WXPAY_PARTNER_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}

# 代理设置，None或者{"https": "http://10.10.1.10:1080"}
PROXY = None
