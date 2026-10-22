# -*- coding: utf-8 -*-
"""支付通道开关的请求/响应模型。"""
from pydantic import BaseModel, Field


class PayChannelUpdate(BaseModel):
    channel: str = Field(..., description="支付通道：xunhupay 或 lantu")
