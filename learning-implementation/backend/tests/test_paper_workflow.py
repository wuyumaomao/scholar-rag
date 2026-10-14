"""Exercise dynamic Send, isolation, conversation state and bounded review."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.paper_agent import AgentConversationError, AgentExecutionError, PaperAgent
from app.agent.paper_workflow import PaperWorkflow
from app.config import Settings
from test_paper_agent import FakeRetrieval, call


def task(question):
    return {"question": question, "background": ""}


def research_model(messages):
    payload = json.loads(messages[1].content)
    assert payload["sources"]
    return AIMessage(content="Evidence-based result [paper-parent, p. 3].")


def passing_review(_):
    return {"decision": "pass", "issues": [], "retry_queries": []}


def workflow(*, tasks=None, planner=None, model=research_model, writer=None,
             reviewer=passing_review, service=None, budget=6, saver=None, locks=None):
    return PaperWorkflow(settings=Settings(), retrieval_service=service or FakeRetrieval(),
        max_tool_calls=budget, checkpointer=saver, conversation_locks=locks,
        bound_planner=RunnableLambda(planner or (lambda _: {"tasks": tasks or [task("method")]})),
        bound_model=RunnableLambda(model),
        bound_writer=RunnableLambda(writer or (lambda _: AIMessage(content="Final answer [paper-parent, p. 3]."))),
        bound_reviewer=RunnableLambda(reviewer))


def turn(agent, question="Question", *, thread="conversation", file_id="paper"):
    return agent.run(file_id=file_id, pdf_path=Path("paper.pdf"), figure_dir=Path("figures"),
                     query=question, thread_id=thread)


def test_send_researchers_are_parallel_isolated_and_writer_waits_for_all():
    seen, payloads = [], []

    async def scenario():
        started = 0
        ready = asyncio.Event()

        async def model(messages):
            nonlocal started
            seen.append(messages)
            started += 1
            if started == 3:
                ready.set()
            await asyncio.wait_for(ready.wait(), 2)
            return research_model(messages)

        def writer(messages):
            payloads.append(json.loads(messages[1].content))
            assert len(payloads[-1]["research_results"]) == 3
            return AIMessage(content="All three findings [paper-parent, p. 3].")

        agent = workflow(tasks=[task("method"), task("experiments"), task("limitations")],
                         model=model, writer=writer)
        result = await turn(agent)
        snapshot = await agent.checkpointer.aget_tuple({"configurable": {"thread_id": "conversation"}})
        state = snapshot.checkpoint["channel_values"]
        assert len(state["messages"]) == 2
        assert all(not isinstance(m, ToolMessage) for m in state["messages"])
        assert len(state["research_results"]) == 3
        return result

    result = asyncio.run(scenario())
    assert result["status"] == "completed"
    assert result["tool_calls_used"] == 3
    assert result["llm_calls_used"] == 6  # planner, 3×1 researcher calls, writer, reviewer
    assert len(result["research_results"]) == 3
    assert len({t["task_id"] for t in result["tasks"]}) == 3
    assert all(len([m for m in messages if isinstance(m, HumanMessage)]) == 1 for messages in seen)
    assert len(payloads) == 1


def test_review_reads_original_evidence_and_writer_revision_uses_feedback():
    writes, reviews = [], []

    def writer(messages):
        payload = json.loads(messages[1].content)
        writes.append(payload)
        return AIMessage(content="Corrected answer" if payload["review_feedback"] else "Draft")

    def reviewer(messages):
        payload = json.loads(messages[1].content)
        reviews.append(payload)
        assert payload["sources"][0]["evidence"] == "Evidence for method"
        return ({"decision": "revise", "issues": ["Overstates the evidence"], "retry_queries": []}
                if len(reviews) == 1 else passing_review(messages))

    result = asyncio.run(turn(workflow(writer=writer, reviewer=reviewer)))
    assert result["answer"] == "Corrected answer"
    assert result["revision_count"] == 1
    assert result["tool_calls_used"] == 1
    assert writes[1]["review_feedback"]["issues"] == ["Overstates the evidence"]
    assert len(reviews) == 2


def test_supplement_is_fresh_task_with_feedback_and_remaining_shared_budget():
    inputs, seen_reviews = [], []

    def model(messages):
        inputs.append(messages)
        return research_model(messages)

    def reviewer(messages):
        seen_reviews.append(messages)
        if len(seen_reviews) == 1:
            return {"decision": "research", "issues": ["Missing limitations"],
                    "retry_queries": ["limitations"]}
        return passing_review(messages)

    service = FakeRetrieval()
    result = asyncio.run(turn(workflow(model=model, reviewer=reviewer, service=service, budget=2)))
    assert result["revision_count"] == 1
    assert result["tool_calls_used"] == 2
    assert len(result["research_results"]) == 2
    assert "supplement" in result["research_results"][1]["task_id"]
    assert len(inputs[1]) == 2  # system + fresh task payload
    assert "Missing limitations" in json.loads(inputs[1][1].content)["background"]
    assert len(service.calls) == 2


def test_shared_budget_cannot_be_overrun_by_parallel_workers():
    service = FakeRetrieval()
    result = asyncio.run(turn(workflow(tasks=[task("a"), task("b"), task("c")],
        service=service, budget=3,
        reviewer=lambda _: {"decision": "research", "issues": ["More evidence needed"],
                             "retry_queries": ["extra"]})))
    assert len(service.calls) == result["tool_calls_used"] == 3
    assert result["status"] == "tool_limit"
    assert result["revision_count"] == 0
    assert all(r["status"] == "completed" for r in result["research_results"])


def test_second_failed_review_ends_and_saves_explicit_limitations():
    agent = workflow(reviewer=lambda _: {"decision": "revise", "issues": ["Unsupported claim"],
                                         "retry_queries": []})
    result = asyncio.run(turn(agent))
    assert result["revision_count"] == 1
    assert result["status"] == "insufficient"
    assert "Unsupported claim" in result["answer"]

    async def inspect():
        snapshot = await agent.checkpointer.aget_tuple({"configurable": {"thread_id": "conversation"}})
        assert snapshot.checkpoint["channel_values"]["messages"][-1].content == result["answer"]
    asyncio.run(inspect())


def test_new_turn_resets_results_trace_review_and_budget_but_planner_sees_dialogue():
    saver, seen = InMemorySaver(), []

    def planner(messages):
        seen.append(messages)
        return {"tasks": [task("method" if len(seen) == 1 else "method limitations")]}

    async def scenario():
        first = await turn(workflow(planner=planner, saver=saver), "Explain the method")
        second = await turn(workflow(planner=planner, saver=saver), "Its limitations?")
        snapshot = await saver.aget_tuple({"configurable": {"thread_id": "conversation"}})
        state = snapshot.checkpoint["channel_values"]
        assert len(state["messages"]) == 4
        assert len(state["research_results"]) == 1
        return first, second

    first, second = asyncio.run(scenario())
    assert first["tasks"][0]["task_id"] != second["tasks"][0]["task_id"]
    assert first["tool_calls_used"] == second["tool_calls_used"] == 1
    assert len(first["trace"]) == len(second["trace"])
    assert [m.content for m in seen[1] if isinstance(m, HumanMessage)] == ["Explain the method", "Its limitations?"]
    assert not any(isinstance(m, ToolMessage) for m in seen[1])


def test_no_evidence_skips_writer_and_review_and_never_saves_invented_claim():
    def forbidden(_):
        pytest.fail("No-evidence path must not call writer/reviewer")
    agent = workflow(service=FakeRetrieval(empty=True), writer=forbidden, reviewer=forbidden)
    result = asyncio.run(turn(agent))
    assert result["status"] == "no_evidence"
    assert result["review"] is None
    assert result["sources"] == []
    assert result["llm_calls_used"] == 1  # planner only; no evidence to generate


@pytest.mark.parametrize("tasks", [[], [task(" ")], [task(str(i)) for i in range(4)],
                                  [task("same"), task("same")]])
def test_invalid_plan_is_rejected_before_research(tasks):
    service = FakeRetrieval()
    with pytest.raises(AgentExecutionError, match="Planner"):
        asyncio.run(turn(workflow(planner=lambda _: {"tasks": tasks}, service=service)))
    assert service.calls == []


def test_failed_review_does_not_return_completed_or_leak_error():
    def failed(_):
        raise RuntimeError("secret provider URL")
    agent = workflow(reviewer=failed)
    async def scenario():
        with pytest.raises(AgentExecutionError, match="Reflect model call failed") as error:
            await turn(agent)
        assert str(error.value) == "Reflect model call failed"
        with pytest.raises(AgentConversationError, match="中断"):
            await turn(agent)
    asyncio.run(scenario())


def test_workflow_paper_scope_and_same_thread_concurrency_guards():
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def planner(_):
            entered.set()
            await release.wait()
            return {"tasks": [task("method")]}
        agent = workflow(planner=planner)
        first = asyncio.create_task(turn(agent))
        await entered.wait()
        try:
            with pytest.raises(AgentConversationError, match="正在执行"):
                await turn(agent)
        finally:
            release.set()
            await first
        with pytest.raises(AgentConversationError, match="另一篇论文"):
            await turn(agent, file_id="other")
    asyncio.run(scenario())


def test_api_runs_real_workflow_and_returns_tasks_and_review(monkeypatch, tmp_path):
    from app.main import app
    from app.routers import agent as api
    from test_agent_api import setup_file
    setup_file(monkeypatch, tmp_path)
    monkeypatch.setattr(api, "PaperWorkflow", lambda **kwargs: workflow(
        saver=kwargs["checkpointer"], locks=kwargs["conversation_locks"]))
    response = TestClient(app).post("/api/agent", json={"file_id": "paper", "query": "Method?"})
    assert response.status_code == 200
    data = response.json()
    assert data["review"]["decision"] == "pass"
    assert len(data["tasks"]) == 1
    assert data["llm_calls_used"] == 4
    assert [e["node"] for e in data["trace"]] == ["planner", "researcher", "writer", "reflect", "finalize"]


def test_native_planner_writer_and_reviewer_use_normal_chat_without_forced_tool_choice(monkeypatch):
    import httpx
    from langchain_openai import ChatOpenAI
    payloads = []

    def respond(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        assert not any(k in payload for k in ("tools", "tool_choice", "response_format"))
        prompt = payload["messages"][0]["content"]
        if prompt.startswith("Plan research"):
            content = json.dumps({"tasks": [task("method")]})
        elif prompt.startswith("Review the original"):
            material = json.loads(payload["messages"][1]["content"])
            assert material["sources"][0]["evidence"] == "Evidence for method"
            content = json.dumps(passing_review(None))
        else:
            content = "Final answer [paper-parent, p. 3]."
        return httpx.Response(200, json={"id": "mock", "object": "chat.completion",
            "created": 1, "model": "thinking-test", "choices": [{"index": 0,
                "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            model = ChatOpenAI(model="thinking-test", api_key="test", base_url="https://test.invalid/v1",
                               http_async_client=client)
            agent = PaperWorkflow(settings=Settings(), retrieval_service=FakeRetrieval(),
                                  bound_model=RunnableLambda(research_model))
            monkeypatch.setattr(agent, "_chat_model", lambda: model)
            result = await turn(agent)
            assert result["status"] == "completed"
            assert result["review"]["is_sufficient"]
    asyncio.run(scenario())
    assert len(payloads) == 3


def test_old_single_agent_checkpoint_requires_new_conversation():
    saver = InMemorySaver()
    old = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(), checkpointer=saver,
                     bound_model=RunnableLambda(lambda _: AIMessage(content="Unsupported")))
    async def scenario():
        await turn(old)
        with pytest.raises(AgentConversationError, match="旧版"):
            await turn(workflow(saver=saver))
    asyncio.run(scenario())


def test_second_research_review_does_not_launch_third_wave():
    service = FakeRetrieval()
    result = asyncio.run(turn(workflow(service=service, reviewer=lambda _: {
        "decision": "research", "issues": ["Still missing"], "retry_queries": ["extra"]})))
    assert result["status"] == "insufficient"
    assert result["revision_count"] == 1
    assert len(service.calls) == len(result["research_results"]) == 2


def test_independent_conversations_do_not_mix_questions_results_or_paper_scopes():
    async def scenario():
        agent = workflow()
        return await asyncio.gather(turn(agent, "First", thread="a", file_id="paper-a"),
                                    turn(agent, "Second", thread="b", file_id="paper-b"))
    a, b = asyncio.run(scenario())
    assert a["sources"][0]["file_id"] == "paper-a"
    assert b["sources"][0]["file_id"] == "paper-b"
    assert a["tasks"][0]["task_id"] != b["tasks"][0]["task_id"]
