# -*- coding: utf-8 -*-
# @Time    : 2023/10/16 09:36
# @Author  : rabbit
# @File    : send_email_util.py
# @Software: PyCharm
import smtplib
from email.mime.text import MIMEText

from settings.env import get, get_int
from settings.macro import EMAIL_LOG

SMTP_HOST = get("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = get_int("SMTP_PORT", 465)
SMTP_USER = get("SMTP_USER", "")
SMTP_PASSWORD = get("SMTP_PASSWORD", "")


def send_email(title, content, user_recv):
    """通过 SMTP 发送验证码/通知邮件，账号与授权码从环境变量读取。"""
    if not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("未配置 SMTP_USER / SMTP_PASSWORD，请在 .env 中设置")
    username_send = SMTP_USER
    password = SMTP_PASSWORD
    username_recv = [user_recv]  # 收件人，多个收件人用逗号隔开
    content += "   \n如果您不认识这个邮件，可以忽略，肯定是有人随便输入了一个邮箱。"
    mail = MIMEText(content)  # 这里输入邮箱内容
    mail['Subject'] = title  # 这里是标题
    mail['From'] = username_send  # 发件人
    mail['To'] = ",".join(username_recv)  # 收件人
    smtp = smtplib.SMTP_SSL(SMTP_HOST, port=SMTP_PORT)
    smtp.login(username_send, password)  # 登录邮箱
    result = smtp.sendmail(username_send, username_recv, mail.as_string())
    print(result)
    EMAIL_LOG.info(f"""发送邮件, 标题：{title}, 内容: {content}, 收件人：{''.join(username_recv)}""")
    smtp.quit()  # 发送完毕后退出smtp
