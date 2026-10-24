from typing import Optional

from pydantic import BaseModel, Field


class InvoiceCreate(BaseModel):
    """提交开票申请。金额一律以订单为准，前端传来的 amount / order_no 只做兼容忽略。"""

    bill_id: Optional[str] = Field(None, description="要开票的充值订单号，必填")
    amount: Optional[float] = Field(None, description="旧字段，忽略，以后端订单金额为准")
    order_no: Optional[str] = Field(None, description="旧字段，等价于 bill_id")
    title_type: str = Field("company", description="company 单位 / personal 个人")
    title: str = Field("", description="发票抬头")
    tax_no: Optional[str] = Field("", description="税号，单位必填")
    email: str = Field("", description="收票邮箱")
    remark: Optional[str] = Field("", description="备注")


class InvoiceListQuery(BaseModel):
    page: int = Field(1, ge=1, description="页码，从 1 开始")
    # 后台导出 CSV 会一次取 200 条，上限放宽到 200
    page_num: int = Field(10, ge=1, le=200, description="每页条数")
    status: Optional[str] = Field(None, description="pending / issuing / issued / rejected，空表示全部")


class AdminInvoiceListQuery(InvoiceListQuery):
    userId: Optional[int] = Field(None, description="按用户过滤，空表示全部")


class InvoiceCancel(BaseModel):
    id: int = Field(..., description="发票 id")


class InvoiceReview(BaseModel):
    id: int = Field(..., description="发票 id")
    status: str = Field(..., description="issued 通过 / rejected 驳回")
    invoice_no: Optional[str] = Field("", description="发票号，issued 时必填")
    reject_reason: Optional[str] = Field("", description="驳回原因，rejected 时必填")
