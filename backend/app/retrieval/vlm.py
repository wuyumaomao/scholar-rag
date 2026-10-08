"""Small OpenAI-compatible vision model client for figure descriptions."""

from __future__ import annotations

import base64
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable
from urllib.request import Request, urlopen

from app.config import Settings


class VLMError(RuntimeError):
    """Raised when a vision model request cannot produce a description."""


@dataclass(frozen=True)
class VLMConfig:
    """Runtime settings for an OpenAI-compatible VLM endpoint."""

    enabled: bool = False
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "VLMConfig":
        settings = Settings.from_env()
        return cls(
            enabled=settings.vlm_enabled,
            base_url=settings.vlm_base_url,
            model=settings.vlm_model,
            api_key=settings.vlm_api_key,
            timeout_seconds=settings.vlm_timeout_seconds,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "VLMConfig":
        return cls(
            enabled=settings.vlm_enabled,
            base_url=settings.vlm_base_url,
            model=settings.vlm_model,
            api_key=settings.vlm_api_key,
            timeout_seconds=settings.vlm_timeout_seconds,
        )


Transport = Callable[[str, dict[str, object], dict[str, str]], dict[str, object]]


class VisionService:
    """Describe local figure images through an OpenAI-compatible VLM API."""

    _PROMPT = (
        "Analyze this figure from an academic paper. Describe the diagram or chart type, "
        "important labels and components, visible trends or relationships, and numerical "
        "values when they are readable. Be concise and focus on information useful for "
        "answering research questions."
    )

    def __init__(
        self,
        config: VLMConfig | None = None,
        *,
        settings: Settings | None = None,
        transport: Transport | None = None,
    ) -> None:
        if config is not None and settings is not None:
            raise ValueError("config 和 settings 只能传一个")
        self.config = config or VLMConfig.from_settings(settings or Settings.from_env())
        self._transport = transport or self._http_transport
        self._cache: dict[tuple[str, int, str], str] = {}
        self._lock = RLock()

    def describe_image(self, image_path: Path, caption: str = "") -> str | None:
        """Return a cached figure description, or ``None`` when VLM is disabled."""
        if not self.config.enabled:
            return None
        if not image_path.is_file():
            raise VLMError(f"图片不存在: {image_path}")

        stat = image_path.stat()
        cache_key = (str(image_path.resolve()), stat.st_mtime_ns, caption)
        with self._lock:
            cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        prompt = self._PROMPT
        if caption.strip():
            prompt += f"\n\nCaption context: {caption.strip()}"
        payload: dict[str, object] = {
            "model": self.config.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            },
                        },
                    ],
                }
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.config.api_key and self.config.api_key.lower() != "empty":
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        try:
            response = self._transport(self._completion_url(), payload, headers)
            description = self._extract_description(response)
        except VLMError:
            raise
        except Exception as exc:
            raise VLMError(f"VLM 请求失败: {exc}") from exc

        with self._lock:
            self._cache[cache_key] = description
        return description

    def _completion_url(self) -> str:
        base_url = self.config.base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"

    @staticmethod
    def _extract_description(response: dict[str, object]) -> str:
        try:
            choices = response["choices"]
            first = choices[0]  # type: ignore[index]
            message = first["message"]  # type: ignore[index]
            content: Any = message["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise VLMError("VLM 响应缺少 choices[0].message.content") from exc

        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and isinstance(item.get("text"), str)
            ).strip()
            if text:
                return text
        raise VLMError("VLM 返回了空的图片描述")

    def _http_transport(
        self, url: str, payload: dict[str, object], headers: dict[str, str]
    ) -> dict[str, object]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            raw = response.read()
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VLMError("VLM 返回的不是有效 JSON") from exc
        if not isinstance(decoded, dict):
            raise VLMError("VLM 返回格式不是 JSON 对象")
        return decoded
