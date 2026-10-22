# -*- coding: utf-8 -*-
"""虎皮椒订单的入账规则。

当前计费体系里没有会员档位：``User.token`` 就是人民币余额，
用户充多少就加多少。因此这里不做任何权益换算，按实付金额等额入账。
"""


def is_valid_amount(money):
    """金额必须是正整数元。"""
    try:
        value = float(money)
    except (TypeError, ValueError):
        return False
    return value > 0 and value.is_integer()


def add_by_amount(common, money, function_code, user_id, log):
    """按实付金额等额入账，返回 1 表示成功。

    延迟导入避免与 ``api.users`` 形成循环依赖。
    """
    from api.users.models import User

    money = float(money)

    user = common.db.query(User).filter(User.user_id == user_id).first()
    if user is None:
        raise ValueError(f"用户 {user_id} 不存在")

    balance = (user.token or 0) + money
    common.db.query(User).filter(User.user_id == user_id).update({"token": balance})
    common.db.commit()
    log.info(f"用户{user_id}通过虎皮椒充值 {money} 元，余额: {balance}")
    return 1
