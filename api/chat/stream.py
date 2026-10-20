import datetime
import json

from api.users.curd import update_context_list_message
from api.users.models import User, UserContext
from settings.billing import (
    billed_input_text,
    chat_cost_cny,
    count_tokens,
    format_billing_stream_chunk,
    parse_usage_tokens,
)
from settings.dependencies import REDIS_USER_ASK_TOKEN
from settings.macro import FILE_STORE_ADDR, SYSTEM_LOG, USR_LOG
from providers.chat.registry import chat_provider_registry


class GptStreamHandler:
    def __init__(self, request_body, common, context_list, start_time):
        self.request_body = request_body
        self.common = common
        self.context_list = context_list
        self.start_time = start_time
        self.provider = chat_provider_registry.gpt()

    @staticmethod
    def format_data_response(data):
        return {
            "id": "chatcmpl-8WHbdstkmyRWPb4BDXmAfR5SYodmv",
            "object": "chat.completion.chunk",
            "created": 1702704865,
            "model": "gemini",
            "system_fingerprint": "fp_772e8125bb",
            "choices": [
                {"index": 0, "delta": {"role": "assistant", "content": data}, "logprobs": None,
                 "finish_reason": ""}]
        }

    def _resolve_tokens(self, answer_text, usage):
        input_tokens, output_tokens = parse_usage_tokens(usage)
        if input_tokens or output_tokens:
            return input_tokens, output_tokens
        billed_prompt = billed_input_text(
            self.request_body.prompt,
            self.context_list,
            self.request_body.withoutContext,
        )
        return (
            count_tokens(billed_prompt, self.request_body.mode),
            count_tokens(answer_text, self.request_body.mode),
        )

    def _finish_success(self, answer_text, usage):
        request_body = self.request_body
        common = self.common
        REDIS_USER_ASK_TOKEN.delete(f"{request_body.userId}_output_{request_body.mode}")
        REDIS_USER_ASK_TOKEN.delete(f"{request_body.userId}_input_{request_body.mode}")
        user_item = common.db.query(User).filter(User.user_id == request_body.userId)
        user_obj = user_item.first()
        user_item.update({
            "answer_num": user_obj.answer_num + 1
        })
        common.db.commit()
        input_tokens, output_tokens = self._resolve_tokens(answer_text, usage)
        base_cost = chat_cost_cny(
            request_body.mode,
            input_tokens,
            output_tokens,
            discount=1,
            money_rate=user_obj.money_rate,
        )
        pay_all = round(base_cost * float(user_obj.discount or 1), 6)
        chat = {
            "user": request_body.prompt,
            "start_time": self.start_time,
            "answer_time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "gpt": answer_text,
            "input_token": input_tokens,
            "output_token": output_tokens,
        }
        if answer_text.strip():
            context_row = common.db.query(UserContext).filter(
                UserContext.context_id == request_body.contextId
            ).first()
            context_rows = []
            if context_row:
                raw = context_row.context
                if isinstance(raw, list):
                    context_rows = raw
                elif raw:
                    try:
                        context_rows = json.loads(raw)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        context_rows = []
            filename = f"{request_body.contextId}_{len(context_rows)}"
            file_download_text = f"""\n\n**目前支持导出文档(请等待对话结束后点击下载)：**
                                                                1. [点我将对话结果导出成docx文档]({FILE_STORE_ADDR}?user_id={request_body.userId}&filename={filename}.docx&file_type=docx&context_id={request_body.contextId}&chat_index={len(context_rows)})
                                                                2. [点我将对话结果导出成PPTX]({FILE_STORE_ADDR}?user_id={request_body.userId}&filename={filename}.pptx&file_type=pptx&context_id={request_body.contextId}&chat_index={len(context_rows)})
                                                                如果开启记忆模式，会将对话的历史文字算入计费，请合理使用。
                                """
            yield json.dumps(self.format_data_response(file_download_text), ensure_ascii=False) + "$_$"
        update_context_list_message(
            self.context_list,
            common,
            chat,
            request_body,
            user_item,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        user_after = common.db.query(User).filter(User.user_id == request_body.userId).first()
        yield json.dumps(
            format_billing_stream_chunk(
                input_tokens,
                output_tokens,
                pay_all,
                user_after.token if user_after else 0,
            ),
            ensure_ascii=False,
        ) + "$_$"
        USR_LOG.info(f"""用户{request_body.userId}, 得到答案: {answer_text}""")

    def generate(self, response, single=True, context=None):
        request_body = self.request_body
        string_restore = []
        count = 0
        usage = {}
        finished = False
        while True:
            try:
                for i in response.iter_lines():
                    try:
                        if not i.decode():
                            continue
                    except Exception as e:
                        USR_LOG.warning(f"""解析流出现问题，已忽略: {e.__repr__()}""")
                        continue
                    SYSTEM_LOG.info(f"""接收到字符: {i.decode()}""")
                    REDIS_USER_ASK_TOKEN.set(
                        f"{request_body.userId}_output_{request_body.mode}",
                        f"{''.join(string_restore)}"
                    )
                    try:
                        raw_line = i.decode()
                        if "maximum" in raw_line:
                            USR_LOG.info(f"""字数过多，拒绝回答""")
                            from api.users.curd import question_limit
                            for item in question_limit("**字数已经超过**模型对承受范围，请创建新对话！"):
                                yield item
                            return
                        if raw_line.startswith("data:"):
                            raw_line = raw_line[5:].strip()
                        if not raw_line or raw_line == "[DONE]":
                            continue
                        i = json.loads(raw_line)
                    except Exception as e:
                        USR_LOG.warning(f"""解析json出现错误：{e.__repr__()}, {i}""")
                        continue
                    if i.get("usage"):
                        usage = i["usage"]
                    choices = i.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    if choice.get("finish_reason") == "stop":
                        finished = True
                        yield json.dumps(i, ensure_ascii=False) + "$_$"
                        continue
                    delta = choice.get("delta") or {}
                    delta["content"] = delta.get("content", "").replace("正在连接互联网：", "")
                    string_restore.append(delta.get("content", ""))
                    yield json.dumps(i, ensure_ascii=False) + "$_$"
                if finished or "".join(string_restore).strip():
                    for item in self._finish_success("".join(string_restore), usage):
                        yield item
                    return
                raise Exception("empty stream")
            except Exception as e:
                count += 1
                string_restore = []
                usage = {}
                finished = False
                if count >= 3:
                    USR_LOG.warning("停止生成，出错")
                    user_item = self.common.db.query(User).filter(User.user_id == request_body.userId)
                    user_item.update({
                        "answer_num": user_item.first().answer_num + 1
                    })
                    self.common.db.commit()
                    result_wrong = self.format_data_response(
                        "由于网络问题，请重新提问即可。也可以选择更换模型重新提问，免费用户推荐使用gpt3.5-turbo或者其他付费模型。"
                        "或者创建新对话，由于字数过多也会导致模型崩溃。"
                    )
                    result_wrong["choices"][0]["finish_reason"] = "stop"
                    yield json.dumps(result_wrong, ensure_ascii=False) + "$_$"
                    break
                USR_LOG.warning(f"流式出错，正在重试{e.__repr__()}")
                if single:
                    context = []
                response = self.provider.stream(request_body.prompt, context, request_body.mode)
                continue
