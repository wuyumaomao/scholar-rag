import pytest

from app import config
from app.config import Settings
from app.retrieval.retriever import DEFAULT_MIN_SCORE


def test_settings_read_model_and_retrieval_configuration_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL", "custom-embedding")
    monkeypatch.setenv("RERANKER_ENABLED", "true")
    monkeypatch.setenv("RERANKER_MODEL", "custom-reranker")
    monkeypatch.setenv("RERANK_CANDIDATE_K", "12")
    monkeypatch.setenv("BM25_WEIGHT", "1.75")
    monkeypatch.setenv("RRF_K", "42")
    monkeypatch.setenv("FETCH_K", "24")
    monkeypatch.setenv("TOP_K", "4")
    monkeypatch.setenv("MIN_SCORE", "0.65")
    monkeypatch.setenv("VLM_ENABLED", "true")
    monkeypatch.setenv("VLM_BASE_URL", "https://provider.example/v1")
    monkeypatch.setenv("VLM_MODEL", "gpt-4o")
    monkeypatch.setenv("VLM_API_KEY", "remote-key")
    monkeypatch.setenv("MILVUS_ENABLED", "true")
    monkeypatch.setenv("MILVUS_URI", "http://127.0.0.1:19531")
    monkeypatch.setenv("MILVUS_COLLECTION_PREFIX", "learning_test")

    settings = Settings.from_env()

    assert settings.embedding_model == "custom-embedding"
    assert settings.reranker_enabled is True
    assert settings.reranker_model == "custom-reranker"
    assert settings.rerank_candidate_k == 12
    assert settings.bm25_weight == 1.75
    assert settings.rrf_k == 42
    assert settings.fetch_k == 24
    assert settings.top_k == 4
    assert settings.min_score == 0.65
    assert settings.vlm_enabled is True
    assert settings.vlm_base_url == "https://provider.example/v1"
    assert settings.vlm_model == "gpt-4o"
    assert settings.vlm_api_key == "remote-key"
    assert settings.milvus_enabled is True
    assert settings.milvus_uri == "http://127.0.0.1:19531"
    assert settings.milvus_collection_prefix == "learning_test"


def test_settings_use_safe_defaults_without_enabling_remote_services(monkeypatch) -> None:
    for name in (
        "EMBEDDING_MODEL",
        "RERANKER_ENABLED",
        "RERANKER_MODEL",
        "RERANK_CANDIDATE_K",
        "BM25_WEIGHT",
        "RRF_K",
        "FETCH_K",
        "TOP_K",
        "MIN_SCORE",
        "VLM_ENABLED",
        "VLM_BASE_URL",
        "VLM_MODEL",
        "VLM_API_KEY",
        "MILVUS_ENABLED",
        "MILVUS_URI",
        "MILVUS_COLLECTION_PREFIX",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings.from_env(load_dotenv_file=False)

    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"
    assert settings.reranker_enabled is False
    assert settings.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert settings.rerank_candidate_k == 20
    assert settings.bm25_weight == 1.25
    assert settings.rrf_k == 60
    assert settings.fetch_k == 20
    assert settings.top_k == 5
    assert settings.min_score == 0.8
    assert DEFAULT_MIN_SCORE == 0.8
    assert settings.vlm_enabled is False
    assert settings.vlm_api_key == ""
    assert settings.milvus_enabled is False
    assert settings.milvus_uri == "http://localhost:19531"
    assert settings.milvus_collection_prefix == "learning_rag"


def test_settings_reject_invalid_positive_integer(monkeypatch) -> None:
    monkeypatch.setenv("RRF_K", "0")

    with pytest.raises(ValueError, match="RRF_K"):
        Settings.from_env()


def test_settings_require_endpoint_and_model_when_llm_is_enabled(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        Settings.from_env(load_dotenv_file=False)


def test_settings_reject_non_positive_bm25_weight(monkeypatch) -> None:
    monkeypatch.setenv("BM25_WEIGHT", "0")

    with pytest.raises(ValueError, match="BM25_WEIGHT"):
        Settings.from_env(load_dotenv_file=False)


def test_settings_load_backend_dotenv_file(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "VLM_ENABLED=true\nVLM_BASE_URL=https://dotenv.example/v1\nVLM_MODEL=gpt-4o\n",
        encoding="utf-8",
    )
    for name in ("VLM_ENABLED", "VLM_BASE_URL", "VLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "_ENV_PATH", env_path)

    settings = Settings.from_env(env_path=env_path)

    assert settings.vlm_enabled is True
    assert settings.vlm_base_url == "https://dotenv.example/v1"
    assert settings.vlm_model == "gpt-4o"
