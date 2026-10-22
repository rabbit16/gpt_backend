# -*- coding: utf-8 -*-
"""各支付通道共用的订单号与入账逻辑。

订单号格式统一为 ``{function_code}-{user_id}-{13位毫秒时间戳}``，
无论回调来自微信 v3、虎皮椒还是旧的蓝兔通道，都能解析出同样的三元组。

入账幂等通过 Redis 的 ``SET NX`` 实现：回调可能重复投递，支付平台
要求重复通知时也返回成功，所以必须先用订单号抢占一次，只有抢占成功的
那一次才真正加余额。

各通道使用独立的 Redis 前缀，互不干扰。
"""
import json
import time

from settings.dependencies import REDIS_BILL_TOOL

# 幂等标记保留 7 天，覆盖各支付平台的回调重试窗口。
_IDEMPOTENT_TTL = 7 * 24 * 60 * 60
# 成功结果缓存 5 分钟，供前端轮询。
_RESULT_TTL = 5 * 60


class OrderFormatError(ValueError):
    """订单号格式不符合约定。"""


def build_order_no(function_code, user_id, now_ms=None):
    """生成订单号。"""
    if not function_code or user_id is None:
        raise OrderFormatError("function_code 与 user_id 不能为空")
    if "-" in str(function_code):
        raise OrderFormatError("function_code 不能包含 '-'")
    timestamp = int(now_ms if now_ms is not None else time.time() * 1000)
    return f"{function_code}-{int(user_id)}-{timestamp}"


def parse_order_no(out_trade_no):
    """解析订单号为 (function_code, user_id, order_id)。"""
    if not out_trade_no:
        raise OrderFormatError("订单号为空")
    parts = out_trade_no.split("-")
    if len(parts) != 3:
        raise OrderFormatError(f"订单号格式错误: {out_trade_no}")
    function_code, user_id, order_id = parts
    try:
        user_id_int = int(user_id)
    except ValueError as exc:
        raise OrderFormatError(f"订单号中的用户 id 非法: {user_id}") from exc
    if not function_code or not order_id:
        raise OrderFormatError(f"订单号格式错误: {out_trade_no}")
    return function_code, user_id_int, order_id


def _pending_key(channel, out_trade_no):
    return f"{channel}:pending:{out_trade_no}"


def _done_key(channel, out_trade_no):
    return f"{channel}:done:{out_trade_no}"


def reserve(channel, out_trade_no):
    """抢占订单，返回 True 表示本次调用可以入账。"""
    return bool(
        REDIS_BILL_TOOL.set(_pending_key(channel, out_trade_no), "1", nx=True, ex=_IDEMPOTENT_TTL)
    )


def release(channel, out_trade_no):
    """入账失败时释放抢占，允许平台重试后再次处理。"""
    REDIS_BILL_TOOL.delete(_pending_key(channel, out_trade_no))


def mark_done(channel, out_trade_no, payload):
    """标记已处理，并缓存结果供前端轮询。"""
    body = json.dumps(payload, ensure_ascii=False, default=str)
    REDIS_BILL_TOOL.set(_done_key(channel, out_trade_no), body, ex=_RESULT_TTL)


def get_result(channel, out_trade_no):
    """读取已缓存的处理结果，没有则返回 None。"""
    raw = REDIS_BILL_TOOL.get(_done_key(channel, out_trade_no))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def is_done(channel, out_trade_no):
    return bool(REDIS_BILL_TOOL.exists(_done_key(channel, out_trade_no)))


def settle(common, channel, out_trade_no, money, transaction_id, add_num_by_money, log):
    """把已验签的支付订单落库并入账。

    :param common: ``CommonQueryParams``，提供 db 会话。
    :param channel: 通道标识，如 ``wxpay`` / ``xunhupay``，用于隔离 Redis 前缀。
    :param out_trade_no: 商户订单号。
    :param money: 实际支付金额（元），必须由调用方从已验签数据中取得。
    :param transaction_id: 平台交易号，仅用于日志与缓存结果。
    :param add_num_by_money: 入账函数，避免循环导入由调用方传入。
    :param log: 日志记录器。
    :return: (是否成功, 说明)
    """
    function_code, user_id, order_id = parse_order_no(out_trade_no)

    if not reserve(channel, out_trade_no):
        log.info(f"{channel} 订单 {out_trade_no} 已处理过，忽略重复回调")
        return True, "重复回调，已忽略"

    try:
        from api.users.models import Bill
        from api.users.schemas import BillFormat
        from api.users.curd import get_function_list_curd

        function_list = get_function_list_curd(common)
        code_to_id = {item["function_code"]: item["function_id"] for item in function_list}
        # 旧数据里 chatGPT / chatGpt 两种写法都存在，统一按数据库实际值取。
        function_id = code_to_id.get(function_code)
        if function_id is None:
            lower_map = {k.lower(): v for k, v in code_to_id.items()}
            function_id = lower_map.get(function_code.lower())
        if function_id is None:
            raise ValueError(f"功能点 {function_code} 不存在")

        # 入账函数内按 "chatGpt" 精确匹配，这里统一成数据库里的真实写法。
        add_code = next(
            (code for code in code_to_id if code.lower() == function_code.lower()),
            function_code,
        )

        bill_data = BillFormat(
            bill_id=order_id,
            money=money,
            function_id=int(function_id),
            generate_by=user_id,
        ).dict()
        common.db.add(Bill(**bill_data))

        # add_num_by_money 只处理 chatGpt 且金额命中固定档位；其它编码或金额会静默返回 None，
        # 这里必须拦住，否则用户付了钱却没到账。
        return_code = add_num_by_money(common, money, add_code, user_id, log)
        if return_code != 1:
            raise ValueError(
                f"入账未生效：功能 {add_code} 金额 {money} 元，"
                f"add_num_by_money 返回 {return_code}"
            )

        common.db.commit()
        payload = {
            "code": "0",
            "codeMsg": "成功",
            "out_trade_no": out_trade_no,
            "transaction_id": transaction_id,
            "money": money,
        }
        mark_done(channel, out_trade_no, payload)
        log.info(f"{channel} 订单 {out_trade_no} 入账成功，金额 {money} 元，用户 {user_id}")
        return True, "成功"
    except Exception as exc:
        common.db.rollback()
        release(channel, out_trade_no)
        log.error(f"{channel} 订单 {out_trade_no} 入账失败: {exc}")
        return False, str(exc)
