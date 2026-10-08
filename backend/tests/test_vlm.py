import base64
import json
from pathlib import Path

from app.config import Settings
from app.retrieval.vlm import VLMConfig, VLMError, VisionService


def test_vision_service_sends_image_as_openai_compatible_data_url(tmp_path: Path) -> None:
    image_path = tmp_path / "figure.png"
    image_path.write_bytes(b"png-bytes")
    requests: list[tuple[str, dict[str, object], dict[str, str]]] = []

    def transport(url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        requests.append((url, payload, headers))
        return {"choices": [{"message": {"content": "A diagram of an encoder and decoder."}}]}

    service = VisionService(
        VLMConfig(
            enabled=True,
            base_url="http://vlm.test/v1",
            model="Qwen3-vl-4B",
            api_key="test-key",
        ),
        transport=transport,
    )

    description = service.describe_image(image_path, caption="Figure 5: Architecture")

    assert description == "A diagram of an encoder and decoder."
    assert len(requests) == 1
    url, payload, headers = requests[0]
    assert url == "http://vlm.test/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "Qwen3-vl-4B"
    message = payload["messages"][0]
    image_part = message["content"][1]
    expected_data_url = "data:image/png;base64," + base64.b64encode(b"png-bytes").decode()
    assert image_part == {"type": "image_url", "image_url": {"url": expected_data_url}}
    assert "Figure 5: Architecture" in message["content"][0]["text"]


def test_disabled_vision_service_does_not_read_or_call_transport(tmp_path: Path) -> None:
    requests: list[object] = []

    def transport(*_args, **_kwargs):
        requests.append(True)
        raise AssertionError("disabled VLM must not call transport")

    service = VisionService(
        VLMConfig(enabled=False, base_url="http://vlm.test/v1", model="model", api_key=""),
        transport=transport,
    )

    assert service.describe_image(tmp_path / "missing.png") is None
    assert requests == []


def test_vision_service_can_use_explicit_settings(tmp_path: Path) -> None:
    image_path = tmp_path / "figure.png"
    image_path.write_bytes(b"png-bytes")
    requests: list[tuple[str, dict[str, object], dict[str, str]]] = []

    def transport(url: str, payload: dict[str, object], headers: dict[str, str]) -> dict[str, object]:
        requests.append((url, payload, headers))
        return {"choices": [{"message": {"content": "diagram"}}]}

    service = VisionService(
        settings=Settings(
            vlm_enabled=True,
            vlm_base_url="http://settings.test/v1",
            vlm_model="settings-model",
        ),
        transport=transport,
    )

    assert service.describe_image(image_path) == "diagram"
    assert requests[0][0] == "http://settings.test/v1/chat/completions"


def test_vision_service_rejects_invalid_response(tmp_path: Path) -> None:
    image_path = tmp_path / "figure.png"
    image_path.write_bytes(b"png-bytes")

    service = VisionService(
        VLMConfig(enabled=True, base_url="http://vlm.test/v1", model="model", api_key=""),
        transport=lambda *_args, **_kwargs: {"choices": []},
    )

    try:
        service.describe_image(image_path)
    except VLMError as exc:
        assert "choices" in str(exc)
    else:
        raise AssertionError("invalid VLM response should raise VLMError")


def test_vision_service_caches_description_for_unchanged_image(tmp_path: Path) -> None:
    image_path = tmp_path / "figure.png"
    image_path.write_bytes(b"png-bytes")
    calls = 0

    def transport(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {"choices": [{"message": {"content": "cached description"}}]}

    service = VisionService(
        VLMConfig(enabled=True, base_url="http://vlm.test/v1", model="model", api_key=""),
        transport=transport,
    )

    assert service.describe_image(image_path) == "cached description"
    assert service.describe_image(image_path) == "cached description"
    assert calls == 1
