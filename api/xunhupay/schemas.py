# -*- coding: utf-8 -*-
"""虎皮椒支付请求/响应模型。"""
from typing import Optional

from pydantic import BaseModel, Field

from utils.public_schemas import ResponseOwn


class XuHuPayCreate(BaseModel):
    userId: int = Field(..., description="用户 id")
    money: float = Field(..., description="支付金额，单位元，必须是大于 0 的整数（如 1、50、100）")
    function_code: str = Field(..., description="功能编码，如 chatGpt")
    # auto=按 UA 自动分流，h5=强制手机通道，qrcode=强制 PC 扫码
    pay_type: str = Field("auto", description="支付方式：auto 或 h5 或 qrcode")
    description: Optional[str] = Field(None, max_length=42, description="订单标题，留空用默认文案")


class XuHuPayCreateResponse(ResponseOwn):
    outTradeNo: str = Field(..., description="商户订单号")
    payType: str = Field(..., description="实际使用的支付方式：h5 / qrcode")
    payUrl: str = Field(..., description="h5 返回跳转链接，qrcode 返回二维码图片地址")
    userId: int = Field(..., description="用户 id")


class XuHuPayQueryResponse(ResponseOwn):
    tradeState: str = Field("", description="订单状态：OD 已支付 / WP 未付款 / CD 已取消")
    paid: bool = Field(False, description="是否已支付并入账")


class XuHuPayStatusResponse(ResponseOwn):
    configured: bool = Field(..., description="配置是否完整")
    gateway: str = Field(..., description="当前下单网关")
    missing: list = Field(default_factory=list, description="缺失的配置项")
