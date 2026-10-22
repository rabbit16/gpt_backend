import json
import re
import time

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import and_

from api.users.curd import get_function_list_curd
from api.users.models import Bill
from api.users.response_schemas import (
    BillCreateResponse,
    FunctionListResponse,
    PayApiResponse,
    UserBillListResponse,
)
from api.users.schemas import BillFormat, BillQueryFormat, UserPayApi, VerifyPayAgainFormat
from api.payment import channel as pay_channel
from api.payment.schemas_channel import PayChannelUpdate
from api.admin.auth import require_admin
from app.http import json_response
from settings.dependencies import CommonQueryParams, REDIS_BILL_TOOL
from settings.macro import ALI_PAY_GATEWAY, PAY_URL_MAP_DICT, USR_LOG
from utils.add_answer_num import add_num_by_money
from utils.pay_util.blue_rabbit.blue_rabbit_pay import create_pay
from utils.res_code import Code, ERROR_MAP

router = APIRouter()


@router.get("/verify_pay")
def pay_notify(charset, out_trade_no, method, total_amount, sign, auth_app_id, version, app_id, sign_type,
               seller_id, timestamp,
               function_id=Query(..., description="功能点id"),
               user_id=Query(..., description="用户id"),
               pay_id=Query(..., description="订单id，13位长度对字符串"),
               common: CommonQueryParams = Depends()):
    """
    该接口没有实际用途，测试用，可忽略
    :param pay_id:
    :param charset:
    :param out_trade_no:
    :param method:
    :param total_amount:
    :param sign:
    :param auth_app_id:
    :param version:
    :param app_id:
    :param sign_type:
    :param seller_id:
    :param timestamp:
    :param function_id:
    :param user_id:
    :param common:
    :return:
    """
    bill_data = BillFormat(
        bill_id=pay_id,
        money=total_amount,
        function_id=function_id,
        user_id=user_id
    ).dict()
    bill = Bill(
        **bill_data
    )
    common.db.add(bill)
    common.db.commit()
    return BillCreateResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK]
    )


@router.post("/verify_rabbit")
async def pay_rabbit_notify(request: Request, common: CommonQueryParams = Depends()):
    """
        该接口给后端用，用来接收支付宝发来的请求，验证支付是否完成。
        :return:
        """
    data = await request.form()
    data = data._dict
    subject = data['out_trade_no']
    try:
        funciton_code, user_id, bill_id = subject.split("-")
        if funciton_code == "chatGPT":
            funciton_code = "chatGpt"
        USR_LOG.info(f"用户{user_id}完成支付，{funciton_code}, 订单号: {bill_id}")
        function_list = get_function_list_curd(common)
        d = {}
        for i in function_list:
            d[i["function_code"]] = i["function_id"]
        USR_LOG.info(f"订单{bill_id}验证通过，正在创建订单")
        bill_data = BillFormat(
            bill_id=bill_id,
            money=data["total_fee"],
            function_id=int(d[funciton_code]),
            generate_by=int(user_id)
        ).dict()
        bill = Bill(
            **bill_data
        )
        return_code = add_num_by_money(common, data["total_fee"], funciton_code, user_id, USR_LOG)
        if return_code != 0:
            common.db.add(bill)
            common.db.commit()
            REDIS_BILL_TOOL.set(subject, json.dumps(data), ex=5 * 60)
            USR_LOG.info(f"创建{bill_id}成功")
        return Response(content='SUCCESS', status_code=200)
    except Exception as e:
        print(e)
        return Response(status_code=443, content="FALL")


@router.post("/verify_pay_again")
def verify_again(request: Request, request_body: VerifyPayAgainFormat,
                 common: CommonQueryParams = Depends()):
    if REDIS_BILL_TOOL.exists(request_body.codeNum):
        bill_info = json.loads(REDIS_BILL_TOOL.get(request_body.codeNum))
        bill_info["code"] = str(Code.OK)
        bill_info["codeMsg"] = ERROR_MAP[Code.OK]
        return JSONResponse(content=bill_info)
    return JSONResponse(
        content={
            "code": str(Code.BILL_NOT_FOUND),
            "codeMsg": ERROR_MAP[Code.BILL_NOT_FOUND]
        }
    )


@router.post("/function_list", response_model=FunctionListResponse)
def get_function_list(common: CommonQueryParams = Depends()):
    function_list = get_function_list_curd(common)
    return FunctionListResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        function_list=function_list
    )


@router.post("/user_bill_list", response_model=UserBillListResponse)
def get_user_bill_list(request: Request, request_body: BillQueryFormat,
                       common: CommonQueryParams = Depends()):
    function_list = get_function_list_curd(common)
    d = {}
    for i in function_list:
        d[i["function_id"]] = i["function_name"]
    user_bill_obj_list = common.db.query(Bill).filter(
        and_(
            Bill.generate_by == request_body.userId,
            Bill.is_delete == False
        )
    ).offset(request_body.page_num * (request_body.page - 1)). \
        limit(request_body.page_num).all()
    user_bill_list = []
    for obj in user_bill_obj_list:
        user_bill_list.append({
            "bill_id": obj.bill_id,
            "generate_time": obj.generate_time,
            "pay": obj.money,
            "function_name": d[obj.function_id]
        })
    return UserBillListResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        user_bill_list=user_bill_list,
        totalNum=common.db.query(Bill).filter(
            and_(
                Bill.generate_by == request_body.userId,
                Bill.is_delete == False
            )
        ).count()
    )


@router.get("/pay/channel")
def get_pay_channel():
    """读取全站当前生效的支付通道，前端启动时调用。"""
    return json_response({
        "code": str(Code.OK),
        "codeMsg": ERROR_MAP[Code.OK],
        **pay_channel.public_config(),
    })


@router.post("/admin/payment/channel")
def set_pay_channel(request_body: PayChannelUpdate, common: CommonQueryParams = Depends()):
    """管理员切换全站支付通道。"""
    _, error = require_admin(common)
    if error:
        return error
    try:
        current = pay_channel.set_channel(request_body.channel)
    except ValueError as exc:
        return json_response({
            "code": str(Code.ACCESS_DENY),
            "codeMsg": str(exc),
        })
    USR_LOG.info(f"管理员切换支付通道为 {current}")
    return json_response({
        "code": str(Code.OK),
        "codeMsg": ERROR_MAP[Code.OK],
        **pay_channel.public_config(),
    })


@router.post("/pay_rabbit", response_model=PayApiResponse)
def pay_api(request: Request, request_body: UserPayApi, common: CommonQueryParams = Depends()):
    user_agent = request.headers.get("user-agent", "").lower()
    mobile_usr = 0
    if re.search(r"mobile|android|iphone|ipad", user_agent):
        mobile_usr = 1

    USR_LOG.info(f"用户{request_body.userId}请求对{request_body.function_code}功能付款{request_body.money}元")
    pay_id = str(int(time.time() * 1000))
    code_num = f"{request_body.function_code}-{request_body.userId}-{pay_id}"
    if mobile_usr:
        pay_info = create_pay(code_num, PAY_URL_MAP_DICT["weiChatJumpH5"], request_body.money)
    else:
        pay_info = create_pay(code_num, PAY_URL_MAP_DICT["weiChatPic"], request_body.money)
    USR_LOG.info(f"用户{request_body.userId}付款链接为{ALI_PAY_GATEWAY.format(pay_info)}")
    pay_info["code_num"] = code_num
    return PayApiResponse(
        code=Code.OK,
        codeMsg=ERROR_MAP[Code.OK],
        payUrl=pay_info,
        userId=request_body.userId
    )
