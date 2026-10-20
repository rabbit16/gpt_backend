# -*- coding: utf-8 -*-
"""微信支付 v3 客户端封装。

只负责和微信交互：下单、查单、关闭订单、回调验签解密。
业务入账逻辑不放在这里，见 ``wxpay_order.py``。

设计要点：
  * 懒加载单例，进程内只初始化一次，避免每个请求都重建带证书的 client。
  * 缺配置时抛 :class:`WxPayConfigError`，路由层转成明确错误，不会静默用假凭据。
  * 回调验签失败返回 ``None``，调用方必须据此拒绝，绝不能把未验签数据交给入账逻辑。
"""
import json
import threading

from settings.macro import USR_LOG
from utils.pay_util import pay_param

try:
    from wechatpayv3 import WeChatPay, WeChatPayType
except ImportError:  # pragma: no cover - 依赖缺失时给出明确指引
    WeChatPay = None
    WeChatPayType = None


class WxPayConfigError(RuntimeError):
    """微信支付配置缺失或不完整。"""


class WxPayError(RuntimeError):
    """调用微信支付接口失败。"""

    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"wechatpay error {code}: {message}")


_client = None
_client_lock = threading.Lock()


def is_configured():
    return not pay_param.missing_config()


def _build_client():
    if WeChatPay is None:
        raise WxPayConfigError("未安装 wechatpayv3，请执行 pip install -r requirements.txt")

    missing = pay_param.missing_config()
    if missing:
        raise WxPayConfigError("微信支付配置缺失: " + ", ".join(missing))

    kwargs = {
        "wechatpay_type": WeChatPayType.NATIVE,
        "mchid": pay_param.MCHID,
        "private_key": pay_param.PRIVATE_KEY,
        "cert_serial_no": pay_param.CERT_SERIAL_NO,
        "apiv3_key": pay_param.APIV3_KEY,
        "appid": pay_param.APPID,
        "notify_url": pay_param.NOTIFY_URL,
        "cert_dir": pay_param.CERT_DIR,
        "logger": pay_param.LOGGER,
        "partner_mode": pay_param.PARTNER_MODE,
        "proxy": pay_param.PROXY,
        "timeout": pay_param.TIMEOUT,
    }
    # 公钥模式：只配了公钥才传，否则 SDK 走平台证书自动下载。
    if pay_param.verify_mode() == "public_key":
        kwargs["public_key"] = pay_param.PUBLIC_KEY
        kwargs["public_key_id"] = pay_param.PUBLIC_KEY_ID

    USR_LOG.info(f"初始化微信支付客户端，验签模式: {pay_param.verify_mode()}")
    return WeChatPay(**kwargs)


def get_client():
    """返回进程级单例；初始化失败时抛出 :class:`WxPayConfigError`。"""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = _build_client()
    return _client


def _unwrap(result):
    """把 SDK 的 (code, message) 拆成 (code, dict)，非 2xx 抛 WxPayError。"""
    code, message = result
    if isinstance(message, bytes):
        message = message.decode("utf-8")
    if code not in range(200, 300):
        raise WxPayError(code, message)
    return code, (json.loads(message) if message else {})


def create_native_order(out_trade_no, description, total_fen, time_expire=None, attach=None):
    """Native 扫码下单，返回 ``code_url``。"""
    client = get_client()
    _, data = _unwrap(client.pay(
        description=description,
        out_trade_no=out_trade_no,
        amount={"total": total_fen, "currency": "CNY"},
        pay_type=WeChatPayType.NATIVE,
        time_expire=time_expire,
        attach=attach,
    ))
    return data.get("code_url", "")


def create_h5_order(out_trade_no, description, total_fen, client_ip,
                    time_expire=None, attach=None):
    """H5 下单，返回跳转链接 ``h5_url``。"""
    if not client_ip:
        raise WxPayError(400, "H5 支付必须提供 payer_client_ip")
    client = get_client()
    _, data = _unwrap(client.pay(
        description=description,
        out_trade_no=out_trade_no,
        amount={"total": total_fen, "currency": "CNY"},
        pay_type=WeChatPayType.H5,
        scene_info={
            "payer_client_ip": client_ip,
            "h5_info": {"type": "Wap"},
        },
        time_expire=time_expire,
        attach=attach,
    ))
    return data.get("h5_url", "")


def query_order(out_trade_no):
    """按商户订单号查单，返回微信订单 JSON。"""
    _, data = _unwrap(get_client().query(out_trade_no=out_trade_no))
    return data


def close_order(out_trade_no):
    """关闭未支付订单，失败不抛出，由调用方决定是否需要处理。"""
    try:
        get_client().close(out_trade_no=out_trade_no)
    except Exception as exc:  # noqa: BLE001 - 关闭失败不影响主流程
        USR_LOG.warning(f"关闭微信订单 {out_trade_no} 失败: {exc}")


def parse_callback(headers, body):
    """校验回调签名并解密 resource。

    验签或解密失败返回 ``None``，调用方必须拒绝该回调。
    """
    return get_client().callback(headers, body)
