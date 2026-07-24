"""Multi-provider AI client — Groq, OpenAI, or Claude. Drop-in swappable."""

from abc import ABC, abstractmethod
from typing import Literal

AIProviderType = Literal["groq", "openai", "claude"]

DEFAULT_MODELS: dict[str, str] = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "claude": "claude-haiku-4-5-20251001",
}

# A single chat turn in conversation history
ChatMessage = dict  # {"role": "user"|"assistant", "content": str}


class AIClient(ABC):
    @abstractmethod
    async def chat(
        self,
        system: str,
        user: str,
        history: list[ChatMessage] | None = None,
    ) -> str: ...

    @property
    @abstractmethod
    def provider_name(self) -> str: ...


class GroqClient(AIClient):
    def __init__(self, api_key: str, model: str):
        try:
            from groq import AsyncGroq  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("Groq not installed. Run: pip install groq") from exc
        self._client = AsyncGroq(api_key=api_key)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "groq"

    async def chat(self, system: str, user: str, history: list[ChatMessage] | None = None) -> str:
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user})
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=1500,
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""


class OpenAIClientWrapper(AIClient):
    def __init__(self, api_key: str, model: str):
        try:
            from openai import AsyncOpenAI  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("OpenAI not installed. Run: pip install openai") from exc
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "openai"

    async def chat(self, system: str, user: str, history: list[ChatMessage] | None = None) -> str:
        messages: list[dict] = [{"role": "system", "content": system}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user})
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=1500,
            temperature=0.1,
        )
        return resp.choices[0].message.content or ""


class ClaudeClientWrapper(AIClient):
    def __init__(self, api_key: str, model: str):
        try:
            from anthropic import AsyncAnthropic  # type: ignore[import]
        except ImportError as exc:
            raise RuntimeError("Anthropic not installed. Run: pip install anthropic") from exc
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    @property
    def provider_name(self) -> str:
        return "claude"

    async def chat(self, system: str, user: str, history: list[ChatMessage] | None = None) -> str:
        messages: list[dict] = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user})
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1500,
            system=system,
            messages=messages,
        )
        return resp.content[0].text


def get_client(provider: AIProviderType, api_key: str, model: str | None = None) -> AIClient:
    resolved_model = model or DEFAULT_MODELS[provider]
    if provider == "groq":
        return GroqClient(api_key, resolved_model)
    if provider == "openai":
        return OpenAIClientWrapper(api_key, resolved_model)
    if provider == "claude":
        return ClaudeClientWrapper(api_key, resolved_model)
    raise ValueError(f"Unknown AI provider: {provider}")
