from settings.macro import GPT_URL
from utils.gpt_ask.gpt_ask_class import GptAsk
from providers.chat.base import ChatProvider


class GptChatProvider(ChatProvider):
    name = "gpt"

    def __init__(self):
        self._client = GptAsk(GPT_URL)

    def supports(self, mode: str) -> bool:
        if not mode or "绘图" in mode:
            return False
        lowered = mode.lower()
        return "gpt" in lowered or lowered.startswith("o1")

    def stream(self, prompt: str, context: list, mode: str):
        return self._client.ask_gpt_by_stream(prompt, model=mode, context=context or [])

    def ask_once(self, prompt: str, mode: str = None):
        return self._client.ask_gpt_single(prompt, model=mode or "gpt-3.5-turbo-16k")
