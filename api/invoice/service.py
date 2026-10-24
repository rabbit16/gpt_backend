"""发票：按充值订单开，一单一票。

契约见 chatgpt-web/docs/api/invoice.md。三条硬规则由后端兜底：
1. 必须绑定订单：金额取 tb_bill 里的记录，不信任前端传的 amount；
2. 一单一票：同一 user_id + bill_id 只允许一张 pending / issuing / issued 的发票；
3. 只能开自己的已支付订单：tb_bill 里的记录都是验签入账后写入的，天然是已支付充值订单。
"""

import re

from api.admin.auth import require_admin, resolve_login_user
from api.invoice.schemas import (
    AdminInvoiceListQuery,
    InvoiceCancel,
    InvoiceCreate,
    InvoiceListQuery,
    InvoiceReview,
)
from api.users.models import Bill, Invoice, User
from app.http import json_response
from settings.database import engine
from utils.res_code import Code, ERROR_MAP

# 占用了订单、不允许重复申请的状态；rejected 不占位，可以重新申请
OCCUPIED_STATUS = ("pending", "issuing", "issued")
VALID_STATUS = ("pending", "issuing", "issued", "rejected")
REVIEW_STATUS = ("issued", "rejected")

MIN_TITLE = 2
MAX_TITLE = 200
MAX_TAX_NO = 50
MAX_EMAIL = 200
MAX_REMARK = 500

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# 统一社会信用代码 18 位，允许纳税人识别号 15~20 位字母数字
TAX_NO_RE = re.compile(r"^[0-9A-Za-z]{15,20}$")

CODE_BILL_NOT_FOUND = "4005"
CODE_BILL_ALREADY_INVOICED = "4006"
CODE_BILL_NOT_PAID = "4007"
CODE_INVOICE_INVALID = "4008"


def ensure_invoice_table():
    Invoice.__table__.create(bind=engine, checkfirst=True)


def _fmt_time(value):
    if value and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value or ""


def _ok(**payload):
    return json_response({
        "code": str(Code.OK),
        "codeMsg": ERROR_MAP[Code.OK],
        **payload,
    })


def _fail(code, message):
    return json_response({"code": str(code), "codeMsg": message})


def _item(row: Invoice):
    return {
        "id": row.id,
        "user_id": row.user_id,
        "bill_id": row.bill_id or "",
        "amount": float(row.amount or 0),
        "title_type": row.title_type or "company",
        "title": row.title or "",
        "tax_no": row.tax_no or "",
        "email": row.email or "",
        "remark": row.remark or "",
        "status": row.status or "pending",
        "invoice_no": row.invoice_no or "",
        "reject_reason": row.reject_reason or "",
        "created_at": _fmt_time(row.created_at),
        "updated_at": _fmt_time(row.updated_at),
    }


def _taken_status(db, user_id, bill_id, exclude_id=None):
    """返回占用该订单的发票状态，没有则 None。"""
    query = db.query(Invoice).filter(
        Invoice.user_id == user_id,
        Invoice.bill_id == bill_id,
        Invoice.status.in_(OCCUPIED_STATUS),
    )
    if exclude_id is not None:
        query = query.filter(Invoice.id != exclude_id)
    row = query.first()
    return row.status if row else None


class InvoiceService:
    # ---------------- 用户端 ----------------

    def create(self, request_body: InvoiceCreate, common):
        ensure_invoice_table()
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])

        bill_id = (request_body.bill_id or request_body.order_no or "").strip()
        if not bill_id:
            return _fail(CODE_INVOICE_INVALID, "请从支付记录里选择订单开票")

        bill = common.db.query(Bill).filter(
            Bill.bill_id == bill_id,
            Bill.is_delete == False,
        ).first()
        if not bill or bill.generate_by != user.user_id:
            return _fail(CODE_BILL_NOT_FOUND, "找不到这笔订单，请刷新支付记录")

        # tb_bill 只在支付回调验签通过后写入，金额未达入账条件时还会回滚，
        # 因此能查到记录即代表已支付充值订单；金额为 0 或负数视为异常。
        if not bill.money or float(bill.money) <= 0:
            return _fail(CODE_BILL_NOT_PAID, "只有已支付的充值订单可以开票")

        taken = _taken_status(common.db, user.user_id, bill_id)
        if taken:
            if taken == "issued":
                return _fail(CODE_BILL_ALREADY_INVOICED, "该订单已开过发票，不能重复申请")
            return _fail(CODE_BILL_ALREADY_INVOICED, "该订单的发票正在处理中，请勿重复提交")

        title_type = (request_body.title_type or "company").strip().lower()
        if title_type not in ("company", "personal"):
            return _fail(CODE_INVOICE_INVALID, "请选择开票类型")
        title = (request_body.title or "").strip()
        tax_no = (request_body.tax_no or "").strip()
        email = (request_body.email or "").strip()
        remark = (request_body.remark or "").strip()

        if not (MIN_TITLE <= len(title) <= MAX_TITLE):
            return _fail(CODE_INVOICE_INVALID, "发票抬头请控制在 %s-%s 字" % (MIN_TITLE, MAX_TITLE))
        if title_type == "company" and not tax_no:
            return _fail(CODE_INVOICE_INVALID, "单位开票请填写税号")
        if tax_no and not TAX_NO_RE.match(tax_no):
            return _fail(CODE_INVOICE_INVALID, "税号格式不正确，请填写 15-20 位字母数字")
        if len(tax_no) > MAX_TAX_NO:
            return _fail(CODE_INVOICE_INVALID, "税号过长")
        if not email or len(email) > MAX_EMAIL or not EMAIL_RE.match(email):
            return _fail(CODE_INVOICE_INVALID, "请填写正确的收票邮箱")
        if len(remark) > MAX_REMARK:
            return _fail(CODE_INVOICE_INVALID, "备注请控制在 %s 字以内" % MAX_REMARK)

        row = Invoice(
            user_id=user.user_id,
            bill_id=bill_id,
            amount=float(bill.money),  # 金额以订单为准
            title_type=title_type,
            title=title,
            tax_no=tax_no,
            email=email,
            remark=remark,
            status="pending",
        )
        common.db.add(row)
        common.db.commit()
        common.db.refresh(row)
        return _ok(data={"id": row.id}, invoice=_item(row))

    def list(self, request_body: InvoiceListQuery, common):
        ensure_invoice_table()
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])
        return self._list_for(common, user.user_id, request_body)

    def summary(self, common):
        ensure_invoice_table()
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])

        bills = common.db.query(Bill.bill_id, Bill.money).filter(
            Bill.generate_by == user.user_id,
            Bill.is_delete == False,
            Bill.money > 0,
        ).all()
        recharge_total = sum(float(money or 0) for _, money in bills)
        bill_amount = {bill_id: float(money or 0) for bill_id, money in bills}

        # 按订单口径统计：可开金额 = 还没有有效发票的订单金额之和。
        # 一单一票，所以不能简单用「充值总额 - 已开票 - 审核中」，那样会出现
        # 「可开金额为 0，但某个订单其实还没开」的矛盾。
        issued_amount = 0.0
        pending_amount = 0.0
        occupied = set()
        for (bill_id, status) in common.db.query(Invoice.bill_id, Invoice.status).filter(
            Invoice.user_id == user.user_id,
            Invoice.status.in_(OCCUPIED_STATUS),
        ).all():
            value = bill_amount.get(bill_id, 0.0)
            occupied.add(bill_id)
            if status == "issued":
                issued_amount += value
            else:
                pending_amount += value

        invoiceable = sum(
            amount for bill_id, amount in bill_amount.items() if bill_id not in occupied
        )
        return _ok(data={
            "recharge_total": round(recharge_total, 2),
            "issued_amount": round(issued_amount, 2),
            "pending_amount": round(pending_amount, 2),
            "invoiceable_amount": round(invoiceable, 2),
        })

    def cancel(self, request_body: InvoiceCancel, common):
        ensure_invoice_table()
        user = resolve_login_user(common)
        if not user:
            return _fail(Code.USER_EXPIRE, ERROR_MAP[Code.USER_EXPIRE])

        row = common.db.query(Invoice).filter(
            Invoice.id == request_body.id,
            Invoice.user_id == user.user_id,
        ).first()
        if not row:
            return _fail(Code.BILL_NOT_FOUND, "发票不存在")
        if row.status not in ("pending", "issuing"):
            return _fail(CODE_INVOICE_INVALID, "该发票已开出或已驳回，不能撤销")

        common.db.delete(row)
        common.db.commit()
        return _ok(message="已撤销开票申请")

    # ---------------- 站长端 ----------------

    def admin_list(self, request_body: AdminInvoiceListQuery, common):
        _, error = require_admin(common)
        if error:
            return error
        return self._list_for(common, request_body.userId, request_body, admin=True)

    def review(self, request_body: InvoiceReview, common):
        admin, error = require_admin(common)
        if error:
            return error
        ensure_invoice_table()

        status = (request_body.status or "").strip()
        if status not in REVIEW_STATUS:
            return _fail(CODE_INVOICE_INVALID, "审核结果只能是 issued 或 rejected")

        row = common.db.query(Invoice).filter(Invoice.id == request_body.id).first()
        if not row:
            return _fail(Code.BILL_NOT_FOUND, "发票不存在")
        if row.status not in ("pending", "issuing"):
            return _fail(CODE_INVOICE_INVALID, "该发票已处理，不能重复审核")

        if status == "issued":
            invoice_no = (request_body.invoice_no or "").strip()
            if not invoice_no:
                return _fail(CODE_INVOICE_INVALID, "通过审核必须填写发票号")
            # 并发兜底：同一订单不能出现第二张已开票
            other = common.db.query(Invoice).filter(
                Invoice.user_id == row.user_id,
                Invoice.bill_id == row.bill_id,
                Invoice.id != row.id,
                Invoice.status == "issued",
            ).first()
            if other:
                return _fail(CODE_BILL_ALREADY_INVOICED, "该订单已有其他已开出的发票")
            row.status = "issued"
            row.invoice_no = invoice_no[:100]
            row.reject_reason = ""
        else:
            reason = (request_body.reject_reason or "").strip()
            if not reason:
                return _fail(CODE_INVOICE_INVALID, "驳回必须填写原因")
            row.status = "rejected"
            row.reject_reason = reason[:MAX_REMARK]

        common.db.commit()
        common.db.refresh(row)
        return _ok(data={"id": row.id}, invoice=_item(row))

    # ---------------- 内部 ----------------

    def _list_for(self, common, user_id, request_body, admin=False):
        page = request_body.page or 1
        page_num = request_body.page_num or 10
        status = (request_body.status or "").strip()

        query = common.db.query(Invoice)
        if user_id:
            query = query.filter(Invoice.user_id == user_id)
        if status and status != "all":
            if status not in VALID_STATUS:
                return _fail(CODE_INVOICE_INVALID, "状态参数不正确")
            query = query.filter(Invoice.status == status)

        total = query.count()
        rows = (
            query.order_by(Invoice.created_at.desc(), Invoice.id.desc())
            .offset((page - 1) * page_num)
            .limit(page_num)
            .all()
        )

        items = []
        need_user = admin or not user_id
        names = {}
        if need_user:
            ids = {row.user_id for row in rows if row.user_id}
            if ids:
                for user in common.db.query(User.user_id, User.name, User.telephone).filter(
                    User.user_id.in_(ids)
                ).all():
                    names[user.user_id] = (user.name or "").strip() or str(user.telephone or "")

        for row in rows:
            item = _item(row)
            if need_user:
                item["user_name"] = names.get(row.user_id, "")
            items.append(item)

        # 前端读的是 data.list / data.total（src/pages/invoice/index.tsx），
        # 顶层 list / total / page 保留，兼容现有调用方。
        return _ok(data={
            "list": items,
            "total": total,
            "page": page,
            "page_num": page_num,
        }, list=items, total=total, page=page, page_num=page_num)


invoice_service = InvoiceService()
