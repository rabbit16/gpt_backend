# -*- coding: utf-8 -*-
import datetime
import time

from settings.billing import charge_image_cny, parse_image_mode


def change_user_usage_count(user_item, request_body, common, regular_user_time):
    now_time = datetime.datetime.fromtimestamp(time.time())
    if "gpt-4" not in request_body.mode:
        if "绘图" in request_body.mode:
            model, quality = parse_image_mode(request_body.mode)
            user_obj = user_item.first()
            user_item.update(
                {
                    "token": user_obj.token - charge_image_cny(
                        model,
                        quality,
                        discount=user_obj.discount,
                        money_rate=user_obj.money_rate,
                    ),
                    "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
            )
            common.db.commit()
        else:
            user_item.update(
                    {
                        "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
            )
    else:
        user_item.update(
            {
                "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
    common.db.commit()
