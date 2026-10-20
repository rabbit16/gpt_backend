# -*- coding: utf-8 -*-
# @Time    : 2022/10/18 2:55 下午
# @Author  : rabbit
# @File    : res_code.py
# @Software: PyCharm
from settings.macro import SUPPORT_PHONE

# 客服联系方式由 SUPPORT_PHONE 注入，仓库里不写死个人手机号。
_SUPPORT = f": {SUPPORT_PHONE}" if SUPPORT_PHONE else ""

class Code:
    OK = "0"
    USER_EXIST = "3001"
    ACCESS_DENY = "4003"
    CONTEXT_ID_WRONG = "3002"
    USER_NOT_EXIST = "3003"
    USER_EXPIRE = "3004"
    PASSWORD_WRONG = "3005"
    BILL_NOT_FOUND = "3006"
    FEEDBACK_INVALID = "3007"
    FEEDBACK_TOO_FAST = "3008"
    TASK_INVALID = "3009"


ERROR_MAP = {
    Code.OK: "成功",
    Code.USER_EXIST: "用户已存在",
    Code.ACCESS_DENY: "拒绝访问",
    Code.CONTEXT_ID_WRONG: "上下文id错误",
    Code.USER_NOT_EXIST: "请用手机号登陆！！如果您忘记密码，系统发了一封邮件给您，凭邮件验证码登陆系统！！"
                         "如果您没有收到邮件，请重新注册！",
    Code.USER_EXPIRE: "用户状态已过期",
    Code.PASSWORD_WRONG: "密码错误 如果您填了不正确的邮箱，那请输入正确邮箱重新注册，登录用 手机号或者注册邮箱登录，密码找回请联系管理员" + _SUPPORT,
    Code.BILL_NOT_FOUND: "订单不存在",
    Code.FEEDBACK_INVALID: "留言内容不符合要求",
    Code.FEEDBACK_TOO_FAST: "提交太频繁，请稍后再试",
    Code.TASK_INVALID: "任务内容不符合要求",
}
