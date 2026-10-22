# -*- coding: utf-8 -*-
"""虎皮椒（xunhupay）个人微信/支付宝支付客户端。

协议见 https://www.xunhupay.com/doc/api/pay.html 。

只负责和虎皮椒交互：签名、下单、查单、回调验签。
业务入账逻辑在 ``utils.pay_util.pay_settle``，路由层见 ``api/xunhupay``。

签名规则：去掉 ``hash`` 与空值，参数名按 ASCII 升序拼成 ``k=v&k=v``，
末尾直接追加 APPSECRET（无分隔符），取 32 位小写 MD5。
"""
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit

import requests

from settings.env import get

APPID = get("XUNHUPAY_APPID", "")
APPSECRET = get("XUNHUPAY_APPSECRET", "")
GATEWAY = get("XUNHUPAY_GATEWAY", "https://api.xunhupay.com/payment/do.html")
# 查询接口与下单接口同域不同路径，默认从网关推导，也可单独配置。
QUERY_URL = get("XUNHUPAY_QUERY_URL", "")
NOTIFY_URL = get("XUNHUPAY_NOTIFY_URL", "")
RETURN_URL = get("XUNHUPAY_RETURN_URL", "")
CALLBACK_URL = get("XUNHUPAY_CALLBACK_URL", "")
# 手机 H5 通道必填：网站域名与网站名称。
WAP_URL = get("XUNHUPAY_WAP_URL", "")
WAP_NAME = get("XUNHUPAY_WAP_NAME", "")
# 可选：标识接入程序，会在回调中原样带回。
PLUGINS = get("XUNHUPAY_PLUGINS", "")
# 连接/读取超时（秒）。
TIMEOUT = get("XUNHUPAY_TIMEOUT", "5,15")

API_VERSION = "1.1"


class XuHuPayConfigError(RuntimeError):
    """虎皮椒配置缺失或不完整。"""


class XuHuPayError(RuntimeError):
    """调用虎皮椒接口失败。"""

    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"xunhupay error {code}: {message}")


def _timeout():
    try:
        connect, read = (float(item) for item in TIMEOUT.split(",", 1))
    except (AttributeError, TypeError, ValueError):
        return (5, 15)
    return (connect, read)


def missing_config():
    """返回缺少的必填配置项名称列表，用于启动自检。"""
    required = {
        "XUNHUPAY_APPID": APPID,
        "XUNHUPAY_APPSECRET": APPSECRET,
        "XUNHUPAY_GATEWAY": GATEWAY,
        "XUNHUPAY_NOTIFY_URL": NOTIFY_URL,
    }
    return [name for name, value in required.items() if not value]


def is_configured():
    return not missing_config()


def _query_url():
    if QUERY_URL:
        return QUERY_URL
    parts = urlsplit(GATEWAY)
    return f"{parts.scheme}://{parts.netloc}/payment/query.html"


def nonce_str():
    return secrets.token_hex(16)


def make_sign(fields, secret=None):
    """按虎皮椒规则计算 hash。"""
    key = secret if secret is not None else APPSECRET
    pairs = sorted(
        (str(k), str(v))
        for k, v in fields.items()
        if k != "hash" and v is not None and str(v) != ""
    )
    payload = "&".join(f"{k}={v}" for k, v in pairs)
    return hashlib.md5((payload + key).encode("utf-8")).hexdigest()


def verify_sign(fields, secret=None):
    """校验下单响应或回调通知的 hash。

    ``fields`` 全是标量时才可校验；查询响应里的 ``data`` 是嵌套对象，
    官方 demo 同样跳过该响应的验签。
    """
    received = fields.get("hash")
    if not isinstance(received, str) or not received:
        return False
    if any(isinstance(value, (dict, list)) for value in fields.values()):
        return False
    return hmac.compare_digest(make_sign(fields, secret), received.lower())


def _check_response(data, action, secret=None):
    """校验虎皮椒响应：标量响应必须验签，嵌套响应只校验 errcode。"""
    if not isinstance(data, dict):
        raise XuHuPayError("BAD_RESPONSE", "响应不是 JSON 对象")
    if not any(isinstance(value, (dict, list)) for value in data.values()):
        if not verify_sign(data, secret):
            raise XuHuPayError("BAD_SIGN", f"{action}响应验签失败")
    if str(data.get("errcode")) != "0":
        raise XuHuPayError(data.get("errcode"), data.get("errmsg", f"{action}失败"))
    return data


def _post(url, fields, as_json):
    """调用虎皮椒接口。

    官方 demo 里下单用 JSON body，查询用 form 编码，两种都必须支持。
    """
    if not APPID or not APPSECRET:
        raise XuHuPayConfigError("未配置 XUNHUPAY_APPID / XUNHUPAY_APPSECRET，请在 .env 中设置")
    try:
        if as_json:
            resp = requests.post(url, json=fields, timeout=_timeout())
        else:
            resp = requests.post(url, data=fields, timeout=_timeout())
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise XuHuPayError("NETWORK", str(exc)) from exc
    try:
        return resp.json()
    except ValueError as exc:
        raise XuHuPayError("BAD_RESPONSE", resp.text[:200]) from exc


def create_pay(trade_order_id, total_fee, title, notify_url=None,
               return_url=None, mobile=False, attach=None, plugins=None):
    """发起付款，返回虎皮椒响应 dict。

    :param mobile: True 使用手机 H5 通道（返回 ``url``），
                   False 使用 PC 扫码通道（返回 ``url_qrcode``）。
    """
    fields = {
        "version": API_VERSION,
        "appid": APPID,
        "trade_order_id": trade_order_id,
        "total_fee": f"{float(total_fee):.2f}",
        "title": title,
        "time": int(time.time()),
        "notify_url": notify_url or NOTIFY_URL,
        "nonce_str": nonce_str(),
    }
    # return_url / callback_url 只传配置了的值，空值不参与签名也不发送。
    target_return = return_url or RETURN_URL
    if target_return:
        fields["return_url"] = target_return
    if CALLBACK_URL:
        fields["callback_url"] = CALLBACK_URL
    if attach:
        fields["attach"] = attach
    if plugins or PLUGINS:
        fields["plugins"] = plugins or PLUGINS
    if mobile:
        if not WAP_URL or not WAP_NAME:
            raise XuHuPayConfigError("手机 H5 支付需要配置 XUNHUPAY_WAP_URL / XUNHUPAY_WAP_NAME")
        fields["type"] = "WAP"
        fields["wap_url"] = WAP_URL
        fields["wap_name"] = WAP_NAME

    fields["hash"] = make_sign(fields)
    data = _post(GATEWAY, fields, as_json=True)
    # 响应也必须验签，防止被中间人篡改支付链接。
    return _check_response(data, "下单")


def query_order(trade_order_id):
    """按商户订单号查询，返回 ``data`` 字段。

    状态：OD=已支付，WP=未付款，CD=已取消。
    """
    fields = {
        "appid": APPID,
        "out_trade_order": trade_order_id,
        "time": int(time.time()),
        "nonce_str": nonce_str(),
    }
    fields["hash"] = make_sign(fields)
    result = _post(_query_url(), fields, as_json=False)
    return _check_response(result, "查询").get("data") or {}
