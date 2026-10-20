# -*- coding: utf-8 -*-
# @Time    : 2023/8/29 10:48
# @Author  : rabbit
# @File    : pay_item.py
# @Software: PyCharm
from random import sample
from string import ascii_letters, digits

from flask import jsonify
# from wechatpayv3 import WeChatPayType, WeChatPay
#
# from utils.pay_util.pay_param import APIV3_KEY, MCHID, PRIVATE_KEY, CERT_SERIAL_NO, APPID, NOTIFY_URL, CERT_DIR, LOGGER, \
#     PARTNER_MODE, PROXY

# wxpay = WeChatPay(
#     wechatpay_type=WeChatPayType.NATIVE,
#     mchid=MCHID,
#     private_key=PRIVATE_KEY,
#     cert_serial_no=CERT_SERIAL_NO,
#     apiv3_key=APIV3_KEY,
#     appid=APPID,
#     notify_url=NOTIFY_URL,
#     cert_dir=CERT_DIR,
#     logger=LOGGER,
#     partner_mode=PARTNER_MODE,
#     proxy=PROXY)
#
# def pay():
#     # 以native下单为例，下单成功后即可获取到'code_url'，将'code_url'转换为二维码，并用微信扫码即可进行支付测试。
#     out_trade_no = ''.join(sample(ascii_letters + digits, 8))
#     description = 'demo-description'
#     amount = 1
#     code, message = wxpay.pay(
#         description=description,
#         out_trade_no=out_trade_no,
#         amount={'total': amount},
#         pay_type=WeChatPayType.NATIVE
#     )
#     return jsonify({'code': code, 'message': message})


if __name__ == '__main__':
    print("该脚本仅用于本地调试，第三方账号请通过环境变量注入。")