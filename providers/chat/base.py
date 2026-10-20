from abc import ABC, abstractmethod


class ChatProvider(ABC):
    """对话提供方抽象。后续 Claude / Gemini 等实现同一接口即可接入。"""

    name = ""

    @abstractmethod
    def supports(self, mode: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def stream(self, prompt: str, context: list, mode: str):
        """返回带 iter_lines() 的流式响应。"""
        raise NotImplementedError

    def ask_once(self, prompt: str, mode: str = None):
        raise NotImplementedError
