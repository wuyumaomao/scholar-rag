"""Central application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def _load_env_file(path: Path) -> None:
    """Load learning backend .env without overriding process-level settings."""
    load_dotenv(path, override=False)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} 必须是 true/false")


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    value = default if raw is None else int(raw)
    if value < minimum:
        raise ValueError(f"{name} 必须大于等于 {minimum}")
    return value


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    raw = os.getenv(name)
    value = default if raw is None else float(raw)
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} 必须大于等于 {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} 必须小于等于 {maximum}")
    return value


@dataclass(frozen=True)
class Settings:
    """Model, retrieval, and remote API settings shared by application services."""

    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    reranker_enabled: bool = False
    reranker_model: str = DEFAULT_RERANKER_MODEL
    rerank_candidate_k: int = 10
    fetch_k: int = 20
    top_k: int = 5
    min_score: float = 0.8
    rrf_k: int = 60

    llm_enabled: bool = False
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""
    llm_temperature: float = 0.7
    llm_max_tokens: int = 4096

    vlm_enabled: bool = False
    vlm_base_url: str = ""
    vlm_model: str = ""
    vlm_api_key: str = ""
    vlm_timeout_seconds: float = 60.0

    @classmethod
    def from_env(
        cls,
        *,
        env_path: Path | None = None,
        load_dotenv_file: bool = True,
    ) -> "Settings":
        if load_dotenv_file:
            _load_env_file(_ENV_PATH if env_path is None else env_path)
        settings = cls(
            embedding_model=os.getenv("EMBEDDING_MODEL", cls.embedding_model).strip(),
            reranker_enabled=_env_bool("RERANKER_ENABLED", cls.reranker_enabled),
            reranker_model=os.getenv("RERANKER_MODEL", cls.reranker_model).strip(),
            rerank_candidate_k=_env_int(
                "RERANK_CANDIDATE_K", cls.rerank_candidate_k
            ),
            fetch_k=_env_int("FETCH_K", cls.fetch_k),
            top_k=_env_int("TOP_K", cls.top_k),
            min_score=_env_float(
                "MIN_SCORE", cls.min_score, minimum=-1.0, maximum=1.0
            ),
            rrf_k=_env_int("RRF_K", cls.rrf_k),
            llm_enabled=_env_bool("LLM_ENABLED", cls.llm_enabled),
            llm_base_url=os.getenv("LLM_BASE_URL", cls.llm_base_url).strip(),
            llm_model=os.getenv("LLM_MODEL", cls.llm_model).strip(),
            llm_api_key=os.getenv("LLM_API_KEY", cls.llm_api_key),
            llm_temperature=_env_float("LLM_TEMPERATURE", cls.llm_temperature, minimum=0),
            llm_max_tokens=_env_int("LLM_MAX_TOKENS", cls.llm_max_tokens),
            vlm_enabled=_env_bool("VLM_ENABLED", cls.vlm_enabled),
            vlm_base_url=os.getenv("VLM_BASE_URL", cls.vlm_base_url).strip(),
            vlm_model=os.getenv("VLM_MODEL", cls.vlm_model).strip(),
            vlm_api_key=os.getenv("VLM_API_KEY", cls.vlm_api_key),
            vlm_timeout_seconds=_env_float(
                "VLM_TIMEOUT_SECONDS", cls.vlm_timeout_seconds, minimum=0.1
            ),
        )
        if not settings.embedding_model:
            raise ValueError("EMBEDDING_MODEL 不能为空")
        if settings.reranker_enabled and not settings.reranker_model:
            raise ValueError("RERANKER_MODEL 不能为空")
        if settings.vlm_enabled:
            if not settings.vlm_base_url:
                raise ValueError("启用 VLM 时必须配置 VLM_BASE_URL")
            if not settings.vlm_model:
                raise ValueError("启用 VLM 时必须配置 VLM_MODEL")
        return settings
