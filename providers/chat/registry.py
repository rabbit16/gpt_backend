from providers.chat.base import ChatProvider
from providers.chat.gpt import GptChatProvider
from utils.public_exception import UnicornException
from utils.res_code import Code, ERROR_MAP


class ChatProviderRegistry:
    def __init__(self):
        self._providers = [GptChatProvider()]

    def resolve(self, mode: str) -> ChatProvider:
        for provider in self._providers:
            if provider.supports(mode):
                return provider
        raise UnicornException(Code.ACCESS_DENY, ERROR_MAP[Code.ACCESS_DENY] + "，当前仅支持 GPT 对话")

    def gpt(self) -> GptChatProvider:
        return self._providers[0]


chat_provider_registry = ChatProviderRegistry()
