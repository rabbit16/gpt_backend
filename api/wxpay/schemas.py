# -*- coding: utf-8 -*-
"""微信支付 v3 请求/响应模型。"""
from typing import Optional, Union

from pydantic import BaseModel, Field

from utils.public_schemas import ResponseOwn


class WxPayCreate(BaseModel):
    userId: int = Field(..., description="用户 id")
    money: float = Field(..., gt=0, description="支付金额，单位元")
    function_code: str = Field(..., description="功能编码，如 chatGpt")
    # native=扫码(Native)，h5=手机浏览器(H5)
    pay_type: str = Field("native", description="支付方式：native 或 h5")
    description: Optional[str] = Field(None, max_length=127, description="商品描述，留空用默认文案")


class WxPayCreateResponse(ResponseOwn):
    outTradeNo: str = Field(..., description="商户订单号")
    payType: str = Field(..., description="实际使用的支付方式")
    payUrl: Union[dict, str] = Field(..., description="native 返回 code_url，h5 返回 h5_url")
    userId: int = Field(..., description="用户 id")


class WxPayQueryResponse(ResponseOwn):
    tradeState: str = Field("", description="微信订单状态")
    paid: bool = Field(False, description="是否已支付并入账")


class WxPayStatusResponse(ResponseOwn):
    configured: bool = Field(..., description="配置是否完整")
    verifyMode: str = Field(..., description="验签模式：public_key / platform_cert")
    partnerMode: bool = Field(..., description="是否为服务商模式")
    missing: list = Field(default_factory=list, description="缺失的配置项")
