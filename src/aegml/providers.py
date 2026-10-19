"""A deterministic demo provider and a small Chat Completions HTTP client."""

from __future__ import annotations

import json
from http.client import HTTPException
from typing import TYPE_CHECKING, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

if TYPE_CHECKING:
    from aegml.config import Settings

MAX_RESPONSE_BYTES = 1024 * 1024


class ProviderError(RuntimeError):
    """A provider failed without exposing credentials or remote error bodies."""


class Provider(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str:
        """Return the assistant's text for the supplied conversation."""
        ...


class MockProvider:
    """Offline demonstration; no model inference or ML experiments are run."""

    def complete(self, messages: list[dict[str, str]]) -> str:
        return json.dumps(
            {
                "summary": (
                    "Демонстрационный план: ML-модели не обучались, "
                    "эксперименты не запускались, данные не анализировались."
                ),
                "steps": [
                    "Уточнить постановку задачи, ограничения и целевую метрику.",
                    "Проверить данные и выбрать схему валидации без утечки.",
                    "После получения кейса обучить и оценить простой baseline.",
                    "Сохранить конфигурацию, метрики и артефакты эксперимента.",
                ],
                "assumptions": [
                    "Официальный кейс и данные ещё предстоит подключить.",
                    "Этот ответ создан локальной заглушкой и не зависит от запроса.",
                ],
                "questions": [
                    "Какова целевая метрика и процедура оценки?",
                    "Какие данные, вычисления и внешние API разрешены?",
                ],
            },
            ensure_ascii=False,
        )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A redirect must never forward a bearer token to another endpoint.
        return None


class ChatCompletionsProvider:
    """Client for endpoints that explicitly support Chat Completions requests."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._opener = build_opener(_NoRedirect())

    def complete(self, messages: list[dict[str, str]]) -> str:
        settings = self._settings
        payload = json.dumps(
            {
                "model": settings.model,
                "messages": messages,
                "max_tokens": settings.max_tokens,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if settings.api_key:
            headers["Authorization"] = f"Bearer {settings.api_key}"
        request = Request(
            settings.base_url.rstrip("/") + "/chat/completions",
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=settings.timeout_seconds) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            # Do not include the remote body, reason, URL or exception repr.
            status = exc.code
            exc.close()
            raise ProviderError(f"LLM endpoint вернул HTTP {status}.") from None
        except (URLError, OSError, HTTPException, ValueError):
            raise ProviderError(
                "Не удалось получить ответ LLM endpoint: проверьте адрес, доступность и таймаут."
            ) from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise ProviderError("Ответ LLM endpoint превышает лимит 1 MiB.")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
            raise ProviderError("LLM endpoint вернул некорректный JSON.") from None
        try:
            if not isinstance(result, dict) or not isinstance(result["choices"], list):
                raise TypeError
            content = result["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
        except (KeyError, IndexError, TypeError):
            raise ProviderError(
                "В ответе LLM endpoint отсутствует строка choices[0].message.content."
            ) from None
        return content


def build_provider(settings: Settings) -> Provider:
    if settings.provider == "mock":
        return MockProvider()
    if settings.provider == "chat_completions":
        return ChatCompletionsProvider(settings)
    raise ProviderError("Неизвестный LLM provider в конфигурации.")
