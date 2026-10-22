# -*- coding: utf-8 -*-
"""微信支付订单号与入账幂等控制。

通用逻辑已抽到 :mod:`utils.pay_util.pay_settle`，这里保留微信通道的
Redis 前缀与对外接口，避免已有调用方与线上缓存键发生变化。
"""
from settings.macro import USR_LOG
from utils.pay_util import pay_settle
from utils.pay_util.pay_settle import OrderFormatError  # noqa: F401 - 兼容旧引用

CHANNEL = "wxpay"

build_order_no = pay_settle.build_order_no
parse_order_no = pay_settle.parse_order_no


def reserve(out_trade_no):
    """抢占订单，返回 True 表示本次调用可以入账。"""
    return pay_settle.reserve(CHANNEL, out_trade_no)


def release(out_trade_no):
    """入账失败时释放抢占，允许微信重试后再次处理。"""
    pay_settle.release(CHANNEL, out_trade_no)


def mark_done(out_trade_no, payload):
    """标记已处理，并缓存结果供前端轮询。"""
    pay_settle.mark_done(CHANNEL, out_trade_no, payload)


def get_result(out_trade_no):
    """读取已缓存的处理结果，没有则返回 None。"""
    return pay_settle.get_result(CHANNEL, out_trade_no)


def is_done(out_trade_no):
    return pay_settle.is_done(CHANNEL, out_trade_no)


def settle(common, transaction, add_num_by_money):
    """把已验签的微信订单落库并入账。

    :param common: ``CommonQueryParams``，提供 db 会话。
    :param transaction: 微信订单 JSON（已解密、已验签）。
    :param add_num_by_money: 入账函数，避免循环导入由调用方传入。
    :return: (是否成功, 说明)
    """
    out_trade_no = transaction.get("out_trade_no")

    if transaction.get("trade_state") != "SUCCESS":
        USR_LOG.info(f"微信订单 {out_trade_no} 状态为 {transaction.get('trade_state')}，暂不入账")
        return False, "订单未支付成功"

    # 金额单位是分，必须校验，避免被篡改成 1 分钱买年度会员。
    amount = transaction.get("amount") or {}
    total_fen = amount.get("total")
    if not isinstance(total_fen, int):
        return False, "订单金额缺失"
    money = total_fen / 100

    return pay_settle.settle(
        common,
        CHANNEL,
        out_trade_no,
        money,
        transaction.get("transaction_id"),
        add_num_by_money,
        USR_LOG,
    )
