# -*- coding: utf-8 -*-
"""微信支付 v3 原生接口。

与旧的 ``api/payment`` 路由并存，互不影响：
旧的 ``/pay_rabbit``、``/verify_rabbit`` 继续走蓝兔聚合通道，
新的 ``/wxpay/*`` 走微信官方 APIv3 直连。
"""
import json

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from api.wxpay.schemas import (
    WxPayCreate,
    WxPayCreateResponse,
    WxPayQueryResponse,
    WxPayStatusResponse,
)
from settings.dependencies import CommonQueryParams
from settings.macro import PRODUCT_NAME, USR_LOG
from utils.add_answer_num import add_num_by_money
from utils.pay_util import pay_param, wxpay_order, wxpay_v3
from utils.res_code import ERROR_MAP, Code

router = APIRouter(prefix="/wxpay", tags=["wxpay"])

_PAY_TYPE_MAP = {
    "native": "native",
    "h5": "h5",
}


def _client_ip(request: Request):
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


@router.get("/status", response_model=WxPayStatusResponse)
def pay_status():
    """配置自检接口，便于部署后第一时间确认密钥是否齐全。"""
    missing = pay_param.missing_config()
    return WxPayStatusResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        configured=not missing,
        verifyMode=pay_param.verify_mode(),
        partnerMode=pay_param.PARTNER_MODE,
        missing=missing,
    )


@router.post("/pay", response_model=WxPayCreateResponse)
def create_pay(request: Request, body: WxPayCreate, common: CommonQueryParams = Depends()):
    """统一下单，返回二维码链接或 H5 跳转链接。"""
    pay_type = _PAY_TYPE_MAP.get((body.pay_type or "").lower())
    if pay_type is None:
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": "不支持的支付方式"},
            status_code=400,
        )

    if not wxpay_v3.is_configured():
        missing = pay_param.missing_config()
        USR_LOG.error(f"微信支付配置不完整: {missing}")
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": "微信支付未配置: " + ", ".join(missing)},
            status_code=503,
        )

    out_trade_no = wxpay_order.build_order_no(body.function_code, body.userId)
    # 商品描述全站统一，不接受前端传入，避免暴露内部标识或联系方式。
    description = PRODUCT_NAME
    total_fen = int(round(body.money * 100))
    if total_fen <= 0:
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": "支付金额非法"},
            status_code=400,
        )

    USR_LOG.info(f"用户{body.userId}请求微信支付({pay_type}) {body.money} 元，订单 {out_trade_no}")

    try:
        if pay_type == "native":
            pay_url = wxpay_v3.create_native_order(out_trade_no, description, total_fen)
        else:
            pay_url = wxpay_v3.create_h5_order(
                out_trade_no, description, total_fen, _client_ip(request)
            )
    except wxpay_v3.WxPayConfigError as exc:
        USR_LOG.error(f"微信支付初始化失败: {exc}")
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": str(exc)},
            status_code=503,
        )
    except wxpay_v3.WxPayError as exc:
        USR_LOG.error(f"微信下单失败 {out_trade_no}: {exc.code} {exc.message}")
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": f"微信下单失败: {exc.message}"},
            status_code=502,
        )

    return WxPayCreateResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        outTradeNo=out_trade_no,
        payType=pay_type,
        payUrl=pay_url,
        userId=body.userId,
    )


@router.post("/notify")
async def pay_notify(request: Request, common: CommonQueryParams = Depends()):
    """微信支付回调。

    必须验签通过才入账；无论业务是否成功，验签失败一律返回失败响应。
    成功时必须返回 204/200 且 body 为成功结构，否则微信会持续重试。
    """
    body = await request.body()
    headers = request.headers

    try:
        transaction = wxpay_v3.parse_callback(headers, body)
    except wxpay_v3.WxPayConfigError as exc:
        USR_LOG.error(f"微信回调验签失败，配置异常: {exc}")
        return JSONResponse(content={"code": "FAIL", "message": "配置异常"}, status_code=500)
    except Exception as exc:  # noqa: BLE001 - 验签异常必须拒绝
        USR_LOG.error(f"微信回调验签异常: {exc}")
        return JSONResponse(content={"code": "FAIL", "message": "验签异常"}, status_code=400)

    if transaction is None:
        USR_LOG.error("微信回调验签未通过，已拒绝")
        return JSONResponse(content={"code": "FAIL", "message": "验签失败"}, status_code=401)

    resource = transaction.get("resource") or {}
    out_trade_no = resource.get("out_trade_no", "")
    USR_LOG.info(f"收到微信回调，订单 {out_trade_no}，事件 {transaction.get('event_type')}")

    try:
        ok, reason = wxpay_order.settle(common, resource, add_num_by_money)
    except wxpay_order.OrderFormatError as exc:
        USR_LOG.error(f"微信回调订单号非法: {exc}")
        return JSONResponse(content={"code": "FAIL", "message": "订单号非法"}, status_code=400)

    if not ok:
        # 业务失败返回非 2xx，让微信按策略重试。
        return JSONResponse(content={"code": "FAIL", "message": reason}, status_code=500)

    return Response(status_code=204)


@router.get("/query/{out_trade_no}", response_model=WxPayQueryResponse)
def query_pay(out_trade_no: str):
    """查询订单状态。已入账时直接返回缓存结果，不再打微信。"""
    cached = wxpay_order.get_result(out_trade_no)
    if cached:
        return WxPayQueryResponse(
            code=Code.OK,
            codeMsg=ERROR_MAP[Code.OK],
            tradeState="SUCCESS",
            paid=True,
        )

    try:
        transaction = wxpay_v3.query_order(out_trade_no)
    except wxpay_v3.WxPayConfigError as exc:
        return JSONResponse(
            content={"code": str(Code.ACCESS_DENY), "codeMsg": str(exc)}, status_code=503
        )
    except wxpay_v3.WxPayError as exc:
        return JSONResponse(
            content={"code": str(Code.BILL_NOT_FOUND), "codeMsg": f"查询失败: {exc.message}"},
            status_code=502,
        )

    state = transaction.get("trade_state", "")
    return WxPayQueryResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        tradeState=state,
        # 已支付但回调还没到，这里如实返回，由前端继续轮询。
        paid=state == "SUCCESS" and wxpay_order.is_done(out_trade_no),
    )
