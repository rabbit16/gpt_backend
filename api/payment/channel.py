# -*- coding: utf-8 -*-
"""支付通道全局开关。

配置保存在 Redis，全站共享：前端启动时读取，后台切换后所有用户立即生效。
当前支持两个通道：

* ``xunhupay`` 虎皮椒（/xunhupay/*）
* ``lantu``    旧的蓝兔聚合通道（/pay_rabbit + /verify_pay_again）

Redis 不可用时回退到默认通道，保证下单接口不会因为读配置失败而整体不可用。
"""
from settings.dependencies import REDIS_TOOL
from settings.macro import USR_LOG

KEY = "payment:channel:active"
DEFAULT_CHANNEL = "xunhupay"

# 允许的通道值，新增通道时在这里登记。
CHANNELS = ("xunhupay", "lantu")

CHANNEL_NAMES = {
    "xunhupay": "虎皮椒",
    "lantu": "蓝兔（旧通道）",
}


def get_channel():
    """读取当前生效的支付通道，非法值或读取失败时返回默认值。"""
    try:
        raw = REDIS_TOOL.get(KEY)
    except Exception as exc:
        USR_LOG.error(f"读取支付通道配置失败，使用默认值 {DEFAULT_CHANNEL}: {exc}")
        return DEFAULT_CHANNEL
    if raw is None:
        return DEFAULT_CHANNEL
    value = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    value = value.strip().lower()
    return value if value in CHANNELS else DEFAULT_CHANNEL


def set_channel(channel):
    """设置全局支付通道，返回设置后的值。非法值抛 ValueError。"""
    value = (channel or "").strip().lower()
    if value not in CHANNELS:
        raise ValueError(f"不支持的支付通道: {channel}")
    REDIS_TOOL.set(KEY, value)
    return value


def public_config():
    current = get_channel()
    return {
        "channel": current,
        "channelName": CHANNEL_NAMES.get(current, current),
        "channels": [
            {"value": key, "name": CHANNEL_NAMES[key]} for key in CHANNELS
        ],
    }
