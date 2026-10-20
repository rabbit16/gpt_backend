import copy
import datetime
import json
import os.path
import time
import uuid
import hashlib

import pypandoc
from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from api.users.schemas import UserRequestFormat, GptAskFormat
from settings.billing import (
    billed_input_text,
    chat_cost_cny,
    count_tokens,
    format_billing_stream_chunk,
)
from settings.dependencies import get_db, REDIS_USER_MESSAGE, REDIS_SMI_CODE
from settings.macro import PLUS_USER_PLUS_NUM, FILE_STORE_ADDR, FILE_STORE_LINUX_PWD
from utils.markdown_math import (
    PANDOC_FROM_MARKDOWN,
    ensure_pandoc_env,
    normalize_math_markdown,
)
from utils.gpt_draw.gpt_draw import draw_pic_func
from utils.res_code import Code
from api.users.models import User, FunctionCode, UserContext
from utils.user_use_change_util.user_usage_change import change_user_usage_count
from settings.macro import USR_LOG


def create_single_user(request_body: UserRequestFormat, db: Session):
    column_names = {column.name for column in User.__table__.columns}
    payload = {
        key: value for key, value in request_body.dict().items() if key in column_names
    }
    # 匿名注册不送 1 元试用余额
    start_token = 0 if bool(getattr(request_body, "is_anonymous", False) or getattr(request_body, "anonymous", False)) else 1
    single_user = User(
        **payload,
        is_activate=1,
        token=start_token,
        plus_user_count=4,
        regular_user=0,
        is_year=0,
        is_quarter=0,
        plus_user_expire_time=(datetime.datetime.fromtimestamp(
            datetime.datetime.now().timestamp()) + datetime.timedelta(days=3)).strftime(
            "%Y-%m-%d %H:%M:%S")
    )
    db.add(single_user)
    db.commit()
    db.refresh(single_user)
    chat_id = str(int(time.time() * 1000))
    new_context = UserContext(
        context_id=chat_id,
        used_by=single_user.user_id
    )
    db.add(new_context)
    db.commit()
    return Code.OK, single_user


def _parse_context_payload(raw):
    """SQLAlchemy JSON 列可能已是 list/dict，也可能仍是 JSON 字符串。"""
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, dict)):
        return raw if isinstance(raw, list) else []
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode()
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def create_message_context(context_list, result_list):
    for context in context_list:
        d = {}
        d["id"] = context.context_id
        context_obj = _parse_context_payload(context.context)
        tmp = []
        for index, i in enumerate(context_obj):
            d_t = {}
            for j in range(2):
                d_t["id"] = uuid.uuid4()
                if (j + 1) % 2 == 0:
                    d_t["role"] = "assistant"
                    d_t["dateTime"] = i["answer_time"]
                    d_t["text"] = i["gpt"]
                else:
                    d_t["dateTime"] = i["start_time"]
                    d_t["role"] = "user"
                    d_t["text"] = i["user"]
                d_t["status"] = "pass"
                d_t["requestOptions"] = {
                    "options": {
                        "frequency_penalty": 0,
                        "max tokens": 1888,
                        "model": "gpt-3.5-turbo-16k",
                        "presence penalty": 0,
                        "temperature": 0.8
                    },
                    "parentMessageId": context.context_id,
                    "persona_id": "",
                    "prompt": d_t["text"]
                }
                tmp.append(copy.deepcopy(d_t))
        d["path"] = uuid.uuid4()
        d["data"] = tmp
        d["name"] = tmp[0]["text"] if tmp else "标题"
        d["persona_id"] = ""
        result_list.append(d)


def get_function_list_curd(common):
    function_obj_list = common.db.query(FunctionCode).all()
    function_list = []
    for obj in function_obj_list:
        function_list.append({
            "function_id": obj.function_id,
            "function_code": obj.function_code,
            "function_name": obj.function_name
        })
    return function_list


def update_context_list_message(context_list, common, chat, request_body, user_item, input_tokens=None, output_tokens=None):
    if request_body.mode is not None and "gpt" in request_body.mode and "绘图" not in request_body.mode:
        user_obj = user_item.first()
        if input_tokens is None or output_tokens is None:
            billed_prompt = billed_input_text(chat.get("user", ""), context_list, request_body.withoutContext)
            input_tokens = count_tokens(billed_prompt, request_body.mode)
            output_tokens = count_tokens(chat.get("gpt", ""), request_body.mode) + int(chat.get("output_token") or 0)
        input_tokens = int(input_tokens or 0)
        output_tokens = int(output_tokens or 0)
        base_cost = chat_cost_cny(
            request_body.mode,
            input_tokens,
            output_tokens,
            discount=1,
            money_rate=user_obj.money_rate,
        )
        pay_all = round(base_cost * float(user_obj.discount or 1), 6)
        user_message = common.db.query(User).filter(User.user_id == request_body.userId).first()
        USR_LOG.info(
            f"用户{request_body} 消耗 input_token: {input_tokens} output{output_tokens}"
            f" 花销{pay_all},"
            f" 余额: {user_message.token - pay_all}"
        )
        common.db.query(User).filter(User.user_id == request_body.userId).update(
            {
                "token_daily": user_message.token_daily + base_cost,
                "input_token": user_message.input_token + input_tokens,
                "output_token": user_message.output_token + output_tokens,
                "token": user_message.token - pay_all,
                "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        )
        common.db.commit()

    if context_list:
        context_detail = _parse_context_payload(context_list.context)
        context_detail.append(chat)
        common.db.query(UserContext).filter(
            or_(
                and_(
                    UserContext.context_id == request_body.contextId,
                    UserContext.used_by == request_body.userId
                ),
                and_(
                    UserContext.context_uuid == request_body.contextId,
                    UserContext.used_by == request_body.userId
                )
            )
        ).update({"context": json.dumps(context_detail),
                  "update_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    else:
        context_detail = [chat]
        if len(request_body.contextId) > 13:
            user_context = UserContext(
                used_by=request_body.userId,
                context_uuid=request_body.contextId,
                context=json.dumps(context_detail)
            )
        else:
            user_context = UserContext(
                context_id=request_body.contextId,
                used_by=request_body.userId,
                context=json.dumps(context_detail)
            )
        common.db.add(user_context)
    common.db.commit()
    change_user_usage_count(user_item, request_body, common, user_item.first().regular_user_expire_time)
    return context_detail


def append_context_message(common, user_id, context_id, chat):
    """仅追加会话上下文，不走 LLM、不扣费（v1 代理已计费）。"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    context_row = common.db.query(UserContext).filter(
        or_(
            and_(UserContext.context_id == context_id, UserContext.used_by == user_id),
            and_(UserContext.context_uuid == context_id, UserContext.used_by == user_id),
        ),
        UserContext.is_delete == False,
    ).first()
    if context_row is None:
        raise ValueError("context not found")

    context_detail = _parse_context_payload(context_row.context)
    context_detail.append(chat)
    common.db.query(UserContext).filter(
        UserContext.context_id == context_row.context_id,
        UserContext.used_by == user_id,
    ).update({
        "context": json.dumps(context_detail, ensure_ascii=False),
        "update_time": now,
    })
    common.db.commit()
    return context_detail


def question_limit(msg):
    for index, i in enumerate(msg):
        if index == len(msg) - 1:
            s = {
                "id": "chatcmpl-85tww7qSui0E1k4lIEp5Y3pRPlW02",
                "object": "chatpletion.chunk",
                "created": 1696417402,
                "model": "",
                "choices": [{"index": 0, "delta": {"content": i}, "finish_reason": "stop"}]}
        else:
            s = {
                "id": "chatcmpl-85tww7qSui0E1k4lIEp5Y3pRPlW02",
                "object": "chatpletion.chunk",
                "created": 1696417402,
                "model": "",
                "choices": [{"index": 0, "delta": {"content": i}, "finish_reason": None}]}
        yield json.dumps(s, ensure_ascii=False) + "$_$"


def ask_draw_pic(request_body: GptAskFormat, user_item, common, regular_user_time):
    mession = "请稍后，图片正在生成中， 预计10-20s。该页面没有记忆功能，请及时保存满意的图片以免丢失，提示词可先用gpt生成后再用本模型生成，以免浪费次数。"
    for index, i in enumerate(mession):
        if index == len(mession) - 1:
            s = {
                "id": "chatcmpl-85tww7qSui0E1k4lIEp5Y3pRPlW02",
                "object": "chatpletion.chunk",
                "created": 1696417402,
                "model": "",
                "choices": [{"index": 0, "delta": {"content": "："}, "finish_reason": None}]}
        else:
            s = {
                "id": "chatcmpl-85tww7qSui0E1k4lIEp5Y3pRPlW02",
                "object": "chatpletion.chunk",
                "created": 1696417402,
                "model": "",
                "choices": [{"index": 0, "delta": {"content": i}, "finish_reason": None}]}
        yield json.dumps(s, ensure_ascii=False) + "$_$"
    user_obj = user_item.first()
    image_url = f"![绘图结果]({draw_pic_func(request_body.prompt, request_body.mode, api_key=getattr(user_obj, 'telephone', None))})"
    USR_LOG.info(f"用户{request_body}绘图成功, {image_url}")
    for i in question_limit(image_url):
        yield i
    # 主计费已在 TeamRouter 中转完成；此处不再二次扣费
    cost = 0
    input_tokens = count_tokens(request_body.prompt, "")
    user_after = common.db.query(User).filter(User.user_id == request_body.userId).first()
    yield json.dumps(
        format_billing_stream_chunk(
            input_tokens,
            0,
            cost,
            user_after.token if user_after else 0,
        ),
        ensure_ascii=False,
    ) + "$_$"


def update_user_count():
    USR_LOG.info(f"""更新服务正在运行中，尝试更新用户状态""")
    db: Session = next(get_db())
    now_time = datetime.datetime.fromtimestamp(time.time())
    db.query(User).update({
        "token_daily": 0
    })
    plus_user_list = db.query(User).filter(and_(
        User.plus_user_expire_time >= now_time,
        User.plus_user_count < PLUS_USER_PLUS_NUM,
        User.is_quarter == 4
    ))
    plus_user_list.update({
        "plus_user_count": PLUS_USER_PLUS_NUM
    })
    db.commit()

    plus_user_list = db.query(User).filter(and_(
        User.plus_user_expire_time >= now_time,
        User.plus_user_count < PLUS_USER_PLUS_NUM * 2,
        User.is_quarter == 3
    ))
    plus_user_list.update({
        "plus_user_count": PLUS_USER_PLUS_NUM * 2
    })
    db.commit()

    plus_user_list = db.query(User).filter(and_(
        User.plus_user_expire_time >= now_time,
        User.plus_user_count < (PLUS_USER_PLUS_NUM * 4 - 10),
        User.is_quarter == 1
    ))
    plus_user_list.update({
        "plus_user_count": PLUS_USER_PLUS_NUM * 2
    })
    db.commit()


def monitor_every_second():
    db: Session = next(get_db())
    one_day_user_list = db.query(User).filter(and_(
        User.is_quarter == 2
    ))
    for one_day_user in one_day_user_list.all():
        if not REDIS_USER_MESSAGE.exists(one_day_user.email):
            db.query(User).filter(and_(
                User.user_id == one_day_user.user_id
            )).update(
                {"is_quarter": 0}
            )
            db.commit()

    now_time = datetime.datetime.fromtimestamp(time.time())
    gpt4_user = db.query(User).filter(and_(
        User.plus_user_expire_time < now_time,
        User.is_quarter != 2
    ))
    gpt4_user.update({
        "is_quarter": 0,
        "is_year": 0
    })

    gpt4_user = db.query(User).filter(and_(
        User.plus_user_expire_time < now_time,
        User.plus_user_count > 0
    ))
    gpt4_user.update({
        "plus_user_count": 0
    })

    gpt4_user = db.query(User).filter(and_(
        User.token < 0,
        User.is_delete == False
    ))
    gpt4_user.update({
        "token": 0
    })
    db.commit()


def _file_source_text(file_content):
    if isinstance(file_content, dict):
        return file_content.get("gpt") or ""
    return file_content or ""


def generate_file(file_content, user_id, filename, file_type, source_format="markdown"):
    file_path = f"{FILE_STORE_LINUX_PWD}/{user_id}"
    if not os.path.exists(file_path):
        os.makedirs(file_path, exist_ok=True)
        USR_LOG.info(f"""为用户{user_id}创建一个目录存放文件""")
    source_text = _file_source_text(file_content)
    pandoc_bin = ensure_pandoc_env()
    output_path = f"{file_path}/{filename}"
    if source_format in ("html", "htm"):
        pypandoc.convert_text(
            source_text,
            file_type,
            format="html+tex_math_dollars",
            outputfile=output_path,
        )
        return "", FILE_STORE_ADDR + f"?user_id={user_id}&filename={filename}"
    markdown_text = normalize_math_markdown(source_text)
    if file_type == "pptx":
        md_path = f"{file_path}/{filename}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)
        pandoc = pandoc_bin or "pandoc"
        os.system(
            f"{pandoc} {md_path} -f {PANDOC_FROM_MARKDOWN} -o {output_path}"
        )
    else:
        pypandoc.convert_text(
            markdown_text,
            file_type,
            format=PANDOC_FROM_MARKDOWN,
            outputfile=output_path,
        )
    return "", FILE_STORE_ADDR + f"?user_id={user_id}&filename={filename}"


def md5_encrypt(input_string):
    md5_hash = hashlib.md5()
    md5_hash.update(input_string.encode('utf-8'))
    return md5_hash.hexdigest()
