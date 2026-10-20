import datetime
import json
import random
import time

from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_, and_, cast, String, func

from api.chat.stream import GptStreamHandler
from api.users.curd import (
    create_message_context,
    _parse_context_payload,
    question_limit,
    ask_draw_pic,
    append_context_message,
)
from api.users.models import User, UserContext
from api.users.response_schemas import GptAskResponse, NewChatResponse, ChatListResponse
from api.users.schemas import GptAskFormat, CreateNewChatContext, QueryUserContextList, SaveChatContextFormat, SearchChatContext
from app.http import event_stream, json_response
from providers.chat.registry import chat_provider_registry
from settings.billing import (
    GPT_MODE_LIST,
    billed_input_text,
    chat_cost_cny,
    count_tokens,
    parse_pending_mode,
)
from settings.dependencies import REDIS_SMI_CODE, REDIS_USER_ASK_TOKEN
from settings.macro import USR_LOG
from utils.public_exception import UnicornException
from utils.res_code import Code, ERROR_MAP
from utils.send_email_util import send_email


class ChatService:
    def __init__(self):
        self.registry = chat_provider_registry

    def ask_once(self, request_body: GptAskFormat, common):
        USR_LOG.info(f"{request_body.userId}用户询问GPT内容为： {request_body.prompt}")
        user_item = common.db.query(User).filter(User.user_id == request_body.userId)
        if user_item.first() is None:
            USR_LOG.warning("no token, user id: {}".format(request_body.userId))
            return GptAskResponse(
                code=Code.ACCESS_DENY,
                codeMsg=ERROR_MAP[Code.ACCESS_DENY],
                gptResult=[{"user": request_body.prompt, "gpt": "请传入必要的信息"}]
            )
        if user_item.first().token <= 0:
            return GptAskResponse(
                code=Code.OK,
                codeMsg=ERROR_MAP[Code.OK],
                gptResult=[{"user": request_body.prompt, "gpt": "请充值"}]
            )
        start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result, complete_token, prompt_token = self.registry.gpt().ask_once(request_body.prompt, request_body.mode)
        chat = {
            "user": request_body.prompt,
            "start_time": start_time,
            "answer_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "gpt": result,
            "single": False
        }
        user_obj = user_item.first()
        pay_all = chat_cost_cny(
            request_body.mode,
            prompt_token,
            complete_token,
            discount=user_obj.discount,
            money_rate=user_obj.money_rate,
        )
        common.db.query(User).filter(User.user_id == request_body.userId).update({
            "token": user_obj.token - pay_all
        })
        common.db.commit()
        return GptAskResponse(code=Code.OK, codeMsg=ERROR_MAP[Code.OK], gptResult=[chat])

    def _limit_stream(self, message):
        return event_stream(question_limit(message))

    def ask_stream(self, request, request_body: GptAskFormat, common):
        user_item = common.db.query(User).filter(User.user_id == request_body.userId)
        if user_item.first().is_delete:
            USR_LOG.info(f"""封禁用户尝试提问: {request_body.userId}""")
            return self._limit_stream("系统怀疑你恶意使用爬虫，已经永久封禁。解封请联系管理员。")
        if user_item.first().token < 0:
            USR_LOG.info(f"""封禁用户尝试提问: {request_body.userId}""")
            return self._limit_stream(
                "经检测，您的余额为负数，故无法使用模型，如果想要继续使用**免费**或者**付费**模型， 请将余额充值到**0**以上。手机用户可点右上角的头像或者方块，点击**我的钱包**或者**商城充值**。")
        if user_item.first().is_new:
            if REDIS_SMI_CODE.exists(f"{request_body.userId}:{request_body.prompt}"):
                common.db.query(User).filter(
                    User.user_id == request_body.userId,
                    User.is_delete == False
                ).update({"is_new": 0})
                common.db.commit()
                return self._limit_stream("恭喜您验证成功, 请开始对话吧！！")
            response = self._limit_stream(
                "新用户您好，为了防止恶意注册，**我发送了一个验证码到您的邮箱**，"
                "**请在对话框输入验证码并提交**，之后您就可以开始使用了，如果系统发送失败，会自动删除您的用户。"
                "本页面，上下文记忆功能默认是打开的，如果希望对话没有记忆功能，记得关闭左下角的上下文按钮。"
                "左下方还可以更换gpt的模型。"
                "如果你想让gpt回答的更好，在问问题之前，请尝试给gpt一个身份已让他更好的回答你，比如： 你现在是一个xxx的专家或者更好的提示给他。"
                "gpt-4模型是不会说自己是gpt4的，所以请不要怀疑，如果你选择gpt4，那一定是gpt4在回答您，您也可以在网上找相关问题验证他的真实性。"
                "售后群以及gpt讨论群：757565609"
            )
            verification_code = ''.join(str(random.randint(0, 9)) for _ in range(4))
            redis_code_store = f"{user_item.first().user_id}:{verification_code}"
            REDIS_SMI_CODE.set(redis_code_store, redis_code_store, ex=300)
            try:
                send_email("验证码", verification_code, user_item.first().email)
            except Exception as e:
                if "non-existent" in e.__str__():
                    common.db.delete(user_item.first())
                    common.db.commit()
                    return self._limit_stream(
                        "系统怀疑恶意注册，已删除您的账户，请换一个正常使用的信息注册，如有疑问请联系管理员")
            return response
        if user_item.first().token <= 0.5 and "gpt-4" in request_body.mode:
            return self._limit_stream("选中模型需要余额大于0.5才可使用哦，请**充值**后再使用哦～有问题联系管理员")
        if user_item.first().token <= 0 and "免费" not in request_body.mode:
            return self._limit_stream("请**充值**后再使用哦～有问题联系管理员")

        USR_LOG.info(
            f"{request_body.userId} 模型{request_body.mode} 所属IP{request.client.host} 用户询问GPT内容为： {request_body.prompt}， 请求体{request_body}")
        user_item = common.db.query(User).filter(User.user_id == request_body.userId)
        user_item.update({"ask_num": user_item.first().ask_num + 1})
        common.db.commit()

        start_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context_list = common.db.query(UserContext).filter(
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
        ).first()

        if "绘图" in request_body.mode:
            return event_stream(ask_draw_pic(request_body, user_item, common, user_item.first().regular_user_expire_time))

        context = []
        if not request_body.withoutContext:
            if "免费" in request_body.mode and len(request_body.prompt) > 5000:
                USR_LOG.warning(f"""用户{request_body.userId} 被拒绝回答""")
                return self._limit_stream("请创建新的对话， 手机用户请点击左上角唤醒侧边栏创建新对话。当前免费模型仅支持5000字上下文。")
            REDIS_USER_ASK_TOKEN.set(
                f"{request_body.userId}_input_{request_body.mode}",
                billed_input_text(request_body.prompt, context_list, request_body.withoutContext),
            )
            while True:
                try:
                    USR_LOG.info(f"用户{request_body.userId}使用{request_body.mode}模型提问")
                    response = self.registry.resolve(request_body.mode).stream(request_body.prompt, [], request_body.mode)
                    USR_LOG.info("GPT内容为： None")
                    break
                except Exception as e:
                    USR_LOG.warning(e)
                    if "reduce the length of the messages" in e.__str__() or "Connection reset by peer" in e.__str__():
                        time.sleep(1)
                        continue
                    return self._limit_stream("当前对话出错，请重试，如果前面对话数量过多（开启了上下文模式），请创建新的对话")
        else:
            if context_list:
                text_count = 0
                for i in _parse_context_payload(context_list.context):
                    user = i["user"]
                    context.append({"role": "user", "content": user})
                    text_count += len(user)
                    assistant = i["gpt"]
                    text_count += len(assistant)
                    context.append({"role": "assistant", "content": assistant})
                REDIS_USER_ASK_TOKEN.set(
                    f"{request_body.userId}_input_{request_body.mode}",
                    billed_input_text(request_body.prompt, context_list, request_body.withoutContext),
                )
                if "免费" in request_body.mode and text_count > 5000:
                    USR_LOG.warning(f"""用户{request_body.userId} 被拒绝回答""")
                    return self._limit_stream("请创建新的对话， 手机用户请点击左上角唤醒侧边栏创建新对话。当前免费模型仅支持5000字上下文。")
                while True:
                    try:
                        USR_LOG.info(f"用户{request_body.userId}使用{request_body.mode}模型提问")
                        response = self.registry.resolve(request_body.mode).stream(
                            request_body.prompt, context, request_body.mode)
                        USR_LOG.info("GPT内容为： None")
                        break
                    except Exception as e:
                        USR_LOG.warning(e)
                        if "reduce the length of the messages" in e.__str__() or "Connection reset by peer" in e.__str__():
                            time.sleep(1)
                            continue
                        return self._limit_stream("当前对话出错，请重试，如果前面对话数量过多（开启了上下文模式），请创建新的对话")
            else:
                response = self.registry.resolve(request_body.mode).stream(request_body.prompt, [], request_body.mode)

        handler = GptStreamHandler(request_body, common, context_list, start_time)
        return event_stream(handler.generate(response, not request_body.withoutContext, context))

    def create_chat(self, request_body: CreateNewChatContext, common):
        test_exist = common.db.query(User).filter(and_(
            User.user_id == request_body.userId,
            User.is_delete == False
        )).first()
        if test_exist is None:
            raise UnicornException(Code.CONTEXT_ID_WRONG, ERROR_MAP[Code.CONTEXT_ID_WRONG] + ", 该用户不存在")
        chat_id = str(int(time.time() * 1000))
        common.db.add(UserContext(context_id=chat_id, used_by=request_body.userId))
        common.db.commit()
        USR_LOG.info("创建了一个新会话，用户: {}, 会话id: {}".format(request_body.userId, chat_id))
        return NewChatResponse(code=Code.OK, codeMsg=ERROR_MAP[Code.OK], newChatId=chat_id)

    def save_chat_context(self, request_body: SaveChatContextFormat, common):
        """前端走 /v1 生成回复后，把一轮对话写回原上下文表，便于历史列表展示。"""
        user = common.db.query(User).filter(
            and_(User.user_id == request_body.userId, User.is_delete == False)
        ).first()
        if user is None:
            raise UnicornException(Code.CONTEXT_ID_WRONG, ERROR_MAP[Code.CONTEXT_ID_WRONG] + ", 该用户不存在")

        prompt = (request_body.prompt or "").strip()
        answer = (request_body.gpt or "").strip()
        if not prompt or not answer:
            raise UnicornException(Code.CONTEXT_ID_WRONG, "保存失败：问题和回答不能为空")

        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        chat = {
            "user": prompt,
            "start_time": request_body.start_time or now,
            "answer_time": request_body.answer_time or now,
            "gpt": answer,
            "single": False,
            "mode": request_body.mode or "",
        }
        try:
            append_context_message(common, request_body.userId, str(request_body.contextId), chat)
        except ValueError:
            raise UnicornException(
                Code.CONTEXT_ID_WRONG,
                ERROR_MAP[Code.CONTEXT_ID_WRONG] + "，请检查对话 id 是否正确"
            )
        USR_LOG.info(
            "保存会话上下文 user=%s context=%s prompt_len=%s answer_len=%s",
            request_body.userId,
            request_body.contextId,
            len(prompt),
            len(answer),
        )
        return json_response({"code": str(Code.OK), "codeMsg": ERROR_MAP[Code.OK]})

    def delete_chat(self, request_body: QueryUserContextList, common):
        common.db.query(UserContext).filter(UserContext.context_id == request_body.chat_id).update({
            "is_delete": True
        })
        common.db.commit()
        USR_LOG.info(f"用户{request_body.userId}删除了{request_body.chat_id}对话")
        return json_response({"code": str(Code.OK), "codeMsg": ERROR_MAP[Code.OK]})

    def delete_all_chat(self, request_body: QueryUserContextList, common):
        common.db.query(UserContext).filter(UserContext.used_by == request_body.userId).update({
            "is_delete": True
        })
        common.db.commit()
        USR_LOG.info(f"用户{request_body.userId}删除了所有对话")
        return json_response({"code": str(Code.OK), "codeMsg": ERROR_MAP[Code.OK]})

    def search_chat(self, request, request_body: SearchChatContext, common):
        from settings.dependencies import REDIS_TOOL

        token = request.headers.get("token", "")
        authenticated_id = REDIS_TOOL.hget(f"users:{token}", "userId")
        if not authenticated_id or int(authenticated_id) != request_body.userId:
            raise UnicornException(Code.ACCESS_DENY, ERROR_MAP[Code.ACCESS_DENY])

        keyword = request_body.keyword.strip()
        if not keyword:
            return json_response({"code": str(Code.OK), "codeMsg": ERROR_MAP[Code.OK], "context_dict": [], "total": 0})
        # LIKE only narrows candidate rows in MySQL; verify message text after decoding JSON.
        def like_pattern(value):
            return "%" + value.replace("!", "!!").replace("%", "!%").replace("_", "!_").replace("\\", "!\\") + "%"

        content = cast(UserContext.context, String)
        decoded_content = cast(func.json_unquote(UserContext.context), String)
        unicode_keyword = json.dumps(keyword, ensure_ascii=True)[1:-1]
        matches = [content.ilike(like_pattern(keyword), escape="!")]
        if unicode_keyword != keyword:
            matches.append(decoded_content.ilike(like_pattern(unicode_keyword), escape="!"))
        query = common.db.query(UserContext).filter(
            UserContext.used_by == request_body.userId,
            UserContext.is_delete == False,
            or_(*matches),
        )
        total = query.count()
        contexts = query.order_by(UserContext.context_id.desc()).offset(
            (request_body.page - 1) * request_body.page_num
        ).limit(request_body.page_num).all()
        result_list = []
        create_message_context(contexts, result_list)
        return json_response({
            "code": str(Code.OK), "codeMsg": ERROR_MAP[Code.OK],
            "context_dict": jsonable_encoder(result_list), "total": total,
        })

    def get_context_list(self, request_body: QueryUserContextList, common):
        test_exist = common.db.query(UserContext).filter(UserContext.used_by == request_body.userId).first()
        if test_exist is None:
            raise UnicornException(Code.CONTEXT_ID_WRONG, ERROR_MAP[Code.CONTEXT_ID_WRONG] + "，该用户可能没有创建相关的对话")
        user = common.db.query(User).filter(User.user_id == request_body.userId)
        user_obj = user.first()
        pending_cost = 0
        pending_input = 0
        pending_output = 0
        keys = REDIS_USER_ASK_TOKEN.keys(f"{request_body.userId}_input_*")
        USR_LOG.info(f"获取到用户{request_body.userId}的输入为{keys}")
        for key in keys:
            key = key.decode()
            value = REDIS_USER_ASK_TOKEN.get(key)
            if not value:
                REDIS_USER_ASK_TOKEN.delete(key)
                continue
            mode = parse_pending_mode(key, request_body.userId, "input")
            input_tokens = count_tokens(value.decode(), mode)
            pending_input += input_tokens
            pending_cost += chat_cost_cny(mode, input_tokens, 0, discount=1, money_rate=user_obj.money_rate)
            REDIS_USER_ASK_TOKEN.delete(key)
        keys_ass = REDIS_USER_ASK_TOKEN.keys(f"{request_body.userId}_output_*")
        USR_LOG.info(f"获取到用户{request_body.userId}的输出为{keys_ass}")
        for key in keys_ass:
            key = key.decode()
            value = REDIS_USER_ASK_TOKEN.get(key)
            if not value:
                REDIS_USER_ASK_TOKEN.delete(key)
                continue
            mode = parse_pending_mode(key, request_body.userId, "output")
            output_tokens = count_tokens(value.decode(), mode)
            pending_output += output_tokens
            pending_cost += chat_cost_cny(mode, 0, output_tokens, discount=1, money_rate=user_obj.money_rate)
            REDIS_USER_ASK_TOKEN.delete(key)
        pay_all = round(pending_cost * float(user_obj.discount or 1), 6)
        USR_LOG.info(f"{request_body.userId}共计费: {pay_all}")
        user.update({
            "token": user_obj.token - pay_all,
            "token_daily": (user_obj.token_daily or 0) + pending_cost,
            "input_token": (user_obj.input_token or 0) + pending_input,
            "output_token": (user_obj.output_token or 0) + pending_output,
        })
        common.db.commit()
        if request_body.chat_id is None and request_body.allContext is True:
            context_list = common.db.query(UserContext).filter(
                and_(UserContext.used_by == request_body.userId, UserContext.is_delete == False)
            ).all()
            result_list = []
            create_message_context(context_list, result_list)
        elif request_body.chat_id is None:
            context_list = common.db.query(UserContext).filter(
                and_(UserContext.used_by == request_body.userId, UserContext.is_delete == False)
            ).offset(request_body.page_num * (request_body.page - 1)).limit(request_body.page_num).all()
            result_list = []
            create_message_context(context_list, result_list)
        else:
            test_context = common.db.query(UserContext).filter(and_(
                UserContext.used_by == request_body.userId,
                UserContext.context_id == request_body.chat_id,
                UserContext.is_delete == False
            )).first()
            if test_context is None:
                raise UnicornException(
                    Code.CONTEXT_ID_WRONG,
                    ERROR_MAP[Code.CONTEXT_ID_WRONG] + "，用户存在，没有传入对应的对话id，请检查对话id是否正确"
                )
            context = common.db.query(UserContext).filter(and_(
                UserContext.used_by == request_body.userId,
                UserContext.context_id == request_body.chat_id,
                UserContext.is_delete == False
            )).first()
            result_list = []
            create_message_context([context], result_list)
        return ChatListResponse(
            context_dict=result_list,
            allContextNum=common.db.query(UserContext).filter(
                and_(UserContext.used_by == request_body.userId, UserContext.is_delete == False)
            ).count(),
            code=Code.OK,
            codeMsg=ERROR_MAP[Code.OK]
        )


chat_service = ChatService()
