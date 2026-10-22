# -*- coding: utf-8 -*-
"""虎皮椒（xunhupay）支付路由。

与 ``api/payment``（蓝兔）和 ``api/wxpay``（微信 v3 直连）并存，互不影响：

* ``/xunhupay/pay``   下单，按 UA 自动分流手机 H5 / PC 扫码
* ``/xunhupay/notify`` 支付回调，验签后入账，必须返回纯文本 ``success``
* ``/xunhupay/query``  查单，供前端轮询
* ``/xunhupay/status`` 配置自检
"""
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from api.xunhupay.schemas import (
    XuHuPayCreate,
    XuHuPayCreateResponse,
    XuHuPayQueryResponse,
    XuHuPayStatusResponse,
)
from settings.dependencies import REDIS_BILL_TOOL, CommonQueryParams
from settings.macro import USR_LOG
from utils.pay_util import pay_settle
from utils.pay_util.xunhupay import settle as xunhupay_settle
from utils.pay_util.xunhupay import xunhupay_pay
from utils.res_code import ERROR_MAP, Code

router = APIRouter(prefix="/xunhupay", tags=["xunhupay"])

CHANNEL = "xunhupay"

# 下单金额用于回调时核对，避免金额被篡改。保留 7 天覆盖订单有效期。
_AMOUNT_KEY = "xunhupay:amount:"
_AMOUNT_TTL = 7 * 24 * 60 * 60

_PAY_TYPE_MAP = {"auto": "auto", "h5": "h5", "qrcode": "qrcode", "native": "qrcode"}

# 微信/支付宝 H5 的标题限制：不能带表情与 %，最多 42 个汉字。
_TITLE_MAX = 42


def _is_mobile(request: Request):
    user_agent = request.headers.get("user-agent", "").lower()
    return bool(re.search(r"mobile|android|iphone|ipad|ipod|harmonyos", user_agent))


def _clean_title(raw, function_code):
    title = (raw or "").strip() or f"AI 服务-{function_code}"
    title = title.replace("%", "").replace("&", "")
    return title[:_TITLE_MAX] or "AI 服务"


@router.get("/status", response_model=XuHuPayStatusResponse)
def pay_status():
    """配置自检接口，便于部署后第一时间确认密钥是否齐全。"""
    missing = xunhupay_pay.missing_config()
    return XuHuPayStatusResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        configured=not missing,
        gateway=xunhupay_pay.GATEWAY,
        missing=missing,
    )


@router.post("/pay", response_model=XuHuPayCreateResponse)
def create_pay(request: Request, body: XuHuPayCreate, common: CommonQueryParams = Depends()):
    """统一下单：手机返回跳转链接，PC 返回二维码图片地址。"""
    pay_type = _PAY_TYPE_MAP.get((body.pay_type or "auto").lower())
    if pay_type is None:
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": "不支持的支付方式"},
            status_code=400,
        )
    if pay_type == "auto":
        pay_type = "h5" if _is_mobile(request) else "qrcode"

    if not xunhupay_pay.is_configured():
        missing = xunhupay_pay.missing_config()
        USR_LOG.error(f"虎皮椒支付配置不完整: {missing}")
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": "虎皮椒支付未配置: " + ", ".join(missing)},
            status_code=503,
        )

    # 虎皮椒通道只接受整数元：前端传多少，就生成多少金额的支付链接。
    money = float(body.money)
    if not xunhupay_settle.is_valid_amount(money):
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": "支付金额必须是大于 0 的整数元"},
            status_code=400,
        )
    money = int(money)

    out_trade_no = pay_settle.build_order_no(body.function_code, body.userId)
    USR_LOG.info(f"用户{body.userId}请求虎皮椒支付({pay_type}) {money} 元，订单 {out_trade_no}")

    try:
        data = xunhupay_pay.create_pay(
            out_trade_no,
            money,
            _clean_title(body.description, body.function_code),
            mobile=pay_type == "h5",
            attach=body.function_code,
        )
    except xunhupay_pay.XuHuPayConfigError as exc:
        USR_LOG.error(f"虎皮椒初始化失败: {exc}")
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": str(exc)},
            status_code=503,
        )
    except xunhupay_pay.XuHuPayError as exc:
        USR_LOG.error(f"虎皮椒下单失败 {out_trade_no}: {exc.code} {exc.message}")
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": f"虎皮椒下单失败: {exc.message}"},
            status_code=502,
        )

    pay_url = data.get("url") if pay_type == "h5" else data.get("url_qrcode")
    if not pay_url:
        USR_LOG.error(f"虎皮椒下单响应缺少支付链接: {data}")
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": "虎皮椒未返回支付链接"},
            status_code=502,
        )

    # 记录下单金额，回调时核对，防止金额被替换。
    REDIS_BILL_TOOL.set(f"{_AMOUNT_KEY}{out_trade_no}", f"{money:.2f}", ex=_AMOUNT_TTL)

    return XuHuPayCreateResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        outTradeNo=out_trade_no,
        payType=pay_type,
        payUrl=pay_url,
        userId=body.userId,
    )


@router.post("/notify")
async def pay_notify(request: Request, common: CommonQueryParams = Depends()):
    """虎皮椒支付回调。

    验签不通过一律不处理；处理成功返回纯文本 ``success``，
    否则虎皮椒会再重试 6 次。
    """
    form = await request.form()
    data = {key: str(value) for key, value in form.items()}

    if not xunhupay_pay.verify_sign(data):
        USR_LOG.error(f"虎皮椒回调验签失败: {data.get('trade_order_id')}")
        return PlainTextResponse("fail", status_code=400)

    out_trade_no = data.get("trade_order_id", "")
    status = data.get("status", "")
    USR_LOG.info(f"收到虎皮椒回调，订单 {out_trade_no}，状态 {status}")

    # 只有已支付 (OD) 需要入账；退款相关状态本期不处理。
    if status != "OD":
        USR_LOG.info(f"虎皮椒订单 {out_trade_no} 状态 {status}，不入账")
        return PlainTextResponse("success")

    try:
        money = float(data.get("total_fee", "0"))
    except (TypeError, ValueError):
        USR_LOG.error(f"虎皮椒订单 {out_trade_no} 金额非法: {data.get('total_fee')}")
        return PlainTextResponse("fail", status_code=400)
    if not xunhupay_settle.is_valid_amount(money):
        USR_LOG.error(f"虎皮椒订单 {out_trade_no} 金额非法: {money}")
        return PlainTextResponse("fail", status_code=400)

    expected = REDIS_BILL_TOOL.get(f"{_AMOUNT_KEY}{out_trade_no}")
    if expected is not None:
        expected_money = float(expected.decode("utf-8"))
        if money != expected_money:
            USR_LOG.error(
                f"虎皮椒订单 {out_trade_no} 金额不一致，回调 {money}，下单 {expected_money}"
            )
            return PlainTextResponse("fail", status_code=400)

    try:
        ok, reason = pay_settle.settle(
            common,
            CHANNEL,
            out_trade_no,
            money,
            data.get("transaction_id"),
            xunhupay_settle.add_by_amount,
            USR_LOG,
        )
    except pay_settle.OrderFormatError as exc:
        USR_LOG.error(f"虎皮椒回调订单号非法: {exc}")
        return PlainTextResponse("fail", status_code=400)

    if not ok:
        # 业务失败返回非 success，让虎皮椒按策略重试。
        return PlainTextResponse("fail", status_code=500)

    return PlainTextResponse("success")


@router.get("/query/{out_trade_no}", response_model=XuHuPayQueryResponse)
def query_pay(out_trade_no: str):
    """查询订单状态。已入账时直接返回缓存结果，不再打虎皮椒。"""
    if pay_settle.is_done(CHANNEL, out_trade_no):
        return XuHuPayQueryResponse(
            code=Code.OK,
            codeMsg=ERROR_MAP[Code.OK],
            tradeState="OD",
            paid=True,
        )

    try:
        data = xunhupay_pay.query_order(out_trade_no)
    except xunhupay_pay.XuHuPayConfigError as exc:
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": str(exc)}, status_code=503
        )
    except xunhupay_pay.XuHuPayError as exc:
        return JSONResponse(
            content={"code": str(Code.BILL_NOT_FOUND), "codeMsg": f"查询失败: {exc.message}"},
            status_code=502,
        )

    state = data.get("status", "")
    return XuHuPayQueryResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        tradeState=state,
        # 已支付但回调还没到，这里如实返回，由前端继续轮询。
        paid=state == "OD" and pay_settle.is_done(CHANNEL, out_trade_no),
    )
