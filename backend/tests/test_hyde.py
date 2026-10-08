from app.config import Settings
from app.retrieval.hyde import HyDEError, HyDEGenerator


def test_hyde_generator_sends_question_to_openai_compatible_endpoint() -> None:
    requests: list[tuple[str, dict[str, object], dict[str, str]]] = []

    def transport(url, payload, headers):
        requests.append((url, payload, headers))
        return {
            "choices": [
                {"message": {"content": "A hypothetical academic passage."}}
            ]
        }

    generator = HyDEGenerator(
        settings=Settings(
            llm_enabled=True,
            llm_base_url="https://llm.example/v1",
            llm_model="paper-model",
            llm_api_key="test-key",
        ),
        transport=transport,
    )

    passage = generator.generate("How does the model estimate depth?")

    assert passage == "A hypothetical academic passage."
    assert len(requests) == 1
    url, payload, headers = requests[0]
    assert url == "https://llm.example/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert payload["model"] == "paper-model"
    messages = payload["messages"]
    assert messages[0]["role"] == "system"
    assert "hypothetical" in messages[0]["content"].lower()
    assert messages[1] == {
        "role": "user",
        "content": "How does the model estimate depth?",
    }


def test_hyde_generator_rejects_empty_model_response() -> None:
    generator = HyDEGenerator(
        settings=Settings(
            llm_enabled=True,
            llm_base_url="https://llm.example/v1",
            llm_model="paper-model",
        ),
        transport=lambda *_args: {"choices": [{"message": {"content": " "}}]},
    )

    try:
        generator.generate("How does the model estimate depth?")
    except HyDEError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("empty model output must be rejected")
