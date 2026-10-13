"""Exercise the actual compiled graph without LLM, Milvus or PDF parsing."""

import asyncio
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from app.agent.paper_agent import AgentExecutionError, PaperAgent
from app.config import Settings
from app.documents.chunker import Chunk
from app.retrieval.retriever import RetrievalHit


def call(query="method", *, name="search_paper", args=None, call_id="call-1"):
    return AIMessage(content="", tool_calls=[{
        "name": name, "args": args if args is not None else {"query": query},
        "id": call_id, "type": "tool_call",
    }])


class FakeRetrieval:
    def __init__(self, *, empty=False, fail=False):
        self.calls = []
        self.empty, self.fail = empty, fail

    def retrieve(self, file_id, pdf_path, query, figure_dir, **kwargs):
        self.calls.append((file_id, pdf_path, query, figure_dir, kwargs))
        if self.fail:
            raise RuntimeError("secret-key at private provider URL")
        if self.empty:
            return []
        return [RetrievalHit(Chunk(f"{file_id}-parent", f"Evidence for {query}",
                                  {"page_nums": [3], "section_path": ["Method"]}), .9)]


def run(service, fn, *, limit=3):
    agent = PaperAgent(settings=Settings(), retrieval_service=service,
                       bound_model=RunnableLambda(fn), max_tool_calls=limit,
                       bound_reviewer=RunnableLambda(lambda _: {
                           "is_sufficient": True, "retry_queries": []}))
    return asyncio.run(agent.run(file_id="paper-1", pdf_path=Path("paper-1.pdf"),
                                 figure_dir=Path("figures/paper-1"), query="Explain the method"))


def test_real_graph_retrieves_twice_and_returns_tools_to_model():
    seen = []

    def model(messages):
        seen.append(messages)
        tool_results = [m for m in messages if isinstance(m, ToolMessage)]
        if len(tool_results) == 0:
            return call("method")
        if len(tool_results) == 1:
            assert tool_results[0].tool_call_id == "call-1"
            assert json.loads(tool_results[0].content)["sources"][0]["pages"] == [3]
            return call("limitations", call_id="call-2")
        return AIMessage(content="Answer [paper-1-parent, p. 3].")

    service = FakeRetrieval()
    result = run(service, model)
    assert result["status"] == "completed"
    assert result["tool_calls_used"] == 2
    assert result["answer"] == "Answer [paper-1-parent, p. 3]."
    assert [c[2] for c in service.calls] == ["method", "limitations"]
    assert all(c[0] == "paper-1" and c[4]["top_k"] == 5 for c in service.calls)
    assert len(result["sources"]) == 1
    assert [step["node"] for step in result["trace"]] == ["agent", "tools", "agent", "tools", "agent", "reflect"]
    assert len(seen[-1]) == 6  # system, user, AI, Tool, AI, Tool


def test_repeated_calls_stop_at_exact_budget():
    service = FakeRetrieval()
    result = run(service, lambda _: call(), limit=2)
    assert result["status"] == "tool_limit"
    assert result["tool_calls_used"] == len(service.calls) == 2
    assert "尚未完成" in result["answer"]
    assert "not executed" in result["trace"][-2]["result"]


def test_over_budget_batch_is_not_partially_executed():
    service = FakeRetrieval()
    batch = AIMessage(content="", tool_calls=call().tool_calls + call(call_id="call-2").tool_calls)
    result = run(service, lambda _: batch, limit=1)
    assert result["status"] == "tool_limit"
    assert result["tool_calls_used"] == 0
    assert service.calls == []


@pytest.mark.parametrize("first", [
    call(args={"query": " "}),
    call(args={"query": 123}),
    call(args={"query": "method", "file_id": "other-paper"}),
    call(name="delete_file"),
])
def test_invalid_requests_return_tool_errors_and_consume_budget(first):
    service = FakeRetrieval()

    def model(messages):
        results = [m for m in messages if isinstance(m, ToolMessage)]
        if not results:
            return first
        assert results[0].status == "error"
        return AIMessage(content="Unable to answer.")

    result = run(service, model)
    assert service.calls == []
    assert result["tool_calls_used"] == 1
    assert result["status"] == "no_evidence"


@pytest.mark.parametrize("service", [FakeRetrieval(empty=True), FakeRetrieval(fail=True)])
def test_empty_or_failed_search_does_not_return_unsupported_answer(service):
    def model(messages):
        if not any(isinstance(m, ToolMessage) for m in messages):
            return call()
        return AIMessage(content="An invented claim.")

    result = run(service, model)
    assert result["status"] == "no_evidence"
    assert "invented" not in result["answer"]
    assert "secret-key" not in json.dumps(result)


def test_direct_answer_without_search_is_marked_no_evidence():
    result = run(FakeRetrieval(), lambda _: AIMessage(content="Unsupported fact"))
    assert result["status"] == "no_evidence"
    assert result["tool_calls_used"] == 0


@pytest.mark.parametrize("output", [AIMessage(content=" "), "wrong message type",
    AIMessage(content="", invalid_tool_calls=[{"name": "search_paper", "args": "{",
                                               "id": "bad", "error": "bad JSON"}])])
def test_invalid_model_response_is_safe_error(output):
    with pytest.raises(AgentExecutionError, match="output|empty answer"):
        run(FakeRetrieval(), lambda _: output)


def test_provider_exception_is_sanitized():
    def fail(_):
        raise RuntimeError("secret-key and private URL")
    with pytest.raises(AgentExecutionError) as error:
        run(FakeRetrieval(), fail)
    assert str(error.value) == "Agent model call failed"


def test_two_concurrent_tasks_do_not_share_messages_or_document_scope():
    service = FakeRetrieval()

    def model(messages):
        tools = [m for m in messages if isinstance(m, ToolMessage)]
        if not tools:
            return call(messages[1].content)
        source = json.loads(tools[0].content)["sources"][0]
        return AIMessage(content=source["file_id"])

    agent = PaperAgent(settings=Settings(), retrieval_service=service,
                       bound_model=RunnableLambda(model),
                       bound_reviewer=RunnableLambda(lambda _: {
                           "is_sufficient": True, "retry_queries": []}))

    async def two_tasks():
        return await asyncio.gather(*[
            agent.run(file_id=f, pdf_path=Path(f"{f}.pdf"), figure_dir=Path(f), query=f)
            for f in ["paper-a", "paper-b"]
        ])

    a, b = asyncio.run(two_tasks())
    assert a["answer"] == "paper-a" and b["answer"] == "paper-b"
    assert a["tool_calls_used"] == b["tool_calls_used"] == 1
    assert all(s["file_id"] == "paper-a" for s in a["sources"])


def test_disabled_llm_fails_before_model_or_retrieval():
    agent = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval())
    with pytest.raises(AgentExecutionError, match="disabled"):
        asyncio.run(agent.run(file_id="paper", pdf_path=Path("p.pdf"),
                             figure_dir=Path("figures"), query="question"))
