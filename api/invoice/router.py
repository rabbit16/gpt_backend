from fastapi import APIRouter, Depends

from api.invoice.schemas import (
    AdminInvoiceListQuery,
    InvoiceCancel,
    InvoiceCreate,
    InvoiceListQuery,
    InvoiceReview,
)
from api.invoice.service import invoice_service
from settings.dependencies import CommonQueryParams

router = APIRouter()


@router.post("/invoice/create")
def create_invoice(request_body: InvoiceCreate, common: CommonQueryParams = Depends()):
    return invoice_service.create(request_body, common)


@router.post("/invoice/list")
def list_invoice(request_body: InvoiceListQuery, common: CommonQueryParams = Depends()):
    return invoice_service.list(request_body, common)


@router.post("/invoice/summary")
def invoice_summary(common: CommonQueryParams = Depends()):
    return invoice_service.summary(common)


@router.post("/invoice/cancel")
def cancel_invoice(request_body: InvoiceCancel, common: CommonQueryParams = Depends()):
    return invoice_service.cancel(request_body, common)


@router.post("/admin/invoice/list")
def admin_list_invoice(request_body: AdminInvoiceListQuery, common: CommonQueryParams = Depends()):
    return invoice_service.admin_list(request_body, common)


@router.post("/admin/invoice/review")
def admin_review_invoice(request_body: InvoiceReview, common: CommonQueryParams = Depends()):
    return invoice_service.review(request_body, common)
