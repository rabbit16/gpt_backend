from fastapi import APIRouter

from api.admin.router import router as admin_router
from api.announcement.router import router as announcement_router
from api.software.router import router as software_router
from api.chat.router import router as chat_router
from api.feedback.router import router as feedback_router
from api.task.router import router as task_router
from api.files.router import router as files_router
from api.payment.router import router as payment_router
from api.users.router import router as users_router
from api.wxpay.router import router as wxpay_router
from api.xunhupay.router import router as xunhupay_router
from settings.macro import NGINX_ROUTER

api_router = APIRouter(
    prefix="/{}/user".format(NGINX_ROUTER),
    responses={404: {"description": "路由不存在"}}
)
api_router.include_router(users_router)
api_router.include_router(chat_router)
api_router.include_router(payment_router)
# 微信支付 v3 原生路由，与旧的聚合支付路由并存
api_router.include_router(wxpay_router)
# 虎皮椒个人微信/支付宝，与上面两条通道并存
api_router.include_router(xunhupay_router)
api_router.include_router(files_router)
api_router.include_router(feedback_router)
api_router.include_router(task_router)
api_router.include_router(announcement_router)
api_router.include_router(software_router)
api_router.include_router(admin_router)
