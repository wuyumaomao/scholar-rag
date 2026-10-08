"""Generate hypothetical passages for HyDE dense retrieval queries."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.config import Settings


class HyDEError(RuntimeError):
    """Raised when a HyDE completion cannot produce usable text."""


def _post_json(
    url: str, payload: dict[str, Any], headers: dict[str, str]
) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise HyDEError(f"LLM request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise HyDEError("LLM response must be a JSON object")
    return result


class HyDEGenerator:
    """Call an OpenAI-compatible chat completion endpoint to draft evidence text."""

    def __init__(
        self,
        *,
        settings: Settings,
        transport: Callable[
            [str, dict[str, Any], dict[str, str]], dict[str, Any]
        ] = _post_json,
    ) -> None:
        self._settings = settings
        self._transport = transport

    def generate(self, query: str) -> str:
        if not self._settings.llm_enabled:
            raise HyDEError("LLM_ENABLED must be true to use HyDE")
        if not self._settings.llm_base_url:
            raise HyDEError("LLM_BASE_URL is required to use HyDE")
        if not self._settings.llm_model:
            raise HyDEError("LLM_MODEL is required to use HyDE")
        if not query.strip():
            raise HyDEError("query must not be empty")

        base_url = self._settings.llm_base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            endpoint = base_url
        else:
            endpoint = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self._settings.llm_api_key}"
        payload: dict[str, Any] = {
            "model": self._settings.llm_model,
            "temperature": self._settings.llm_temperature,
            "max_tokens": self._settings.llm_max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Write a concise hypothetical academic passage that could "
                        "answer the user's research question. Include likely domain "
                        "terms and factual relationships. Do not answer conversationally, "
                        "and do not mention that the passage is hypothetical."
                    ),
                },
                {"role": "user", "content": query.strip()},
            ],
        }
        result = self._transport(endpoint, payload, headers)
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HyDEError("LLM response is missing choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise HyDEError("LLM returned empty HyDE text")
        return content.strip()
