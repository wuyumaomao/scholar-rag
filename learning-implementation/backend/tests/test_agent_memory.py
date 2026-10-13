"""Conversation memory through the actual LangGraph checkpointer."""

import asyncio
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.paper_agent import AgentConversationError, AgentExecutionError, PaperAgent
from app.config import Settings
from test_paper_agent import FakeRetrieval, call


def turn(agent, query, *, thread_id="conversation", file_id="paper"):
    return agent.run(file_id=file_id, pdf_path=Path(f"{file_id}.pdf"),
                     figure_dir=Path(file_id), query=query, thread_id=thread_id)


def test_history_restored_across_agent_instances_and_budget_reset():
    saver, locks, seen = InMemorySaver(), {}, []

    def model(messages):
        seen.append(messages)
        last_user = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        if not any(isinstance(m, ToolMessage) for m in messages[last_user:]):
            return call("method" if last_user == 1 else "limitations")
        return AIMessage(content="Answer [paper-parent, p. 3].")

    def instance():
        return PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(),
                          bound_model=RunnableLambda(model), max_tool_calls=1,
                          bound_reviewer=RunnableLambda(lambda _: {
                              "is_sufficient": True, "retry_queries": []}),
                          checkpointer=saver, conversation_locks=locks)

    async def run():
        first = await turn(instance(), "What method?")
        second = await turn(instance(), "Its limitations?")
        other = await turn(instance(), "Fresh question", thread_id="other")
        return first, second, other

    first, second, other = asyncio.run(run())
    assert first["thread_id"] == second["thread_id"] == "conversation"
    assert first["tool_calls_used"] == second["tool_calls_used"] == 1
    assert second["status"] == "completed"
    assert len(second["trace"]) == 4  # current turn only, including review
    assert [m.content for m in seen[2] if isinstance(m, HumanMessage)] == ["What method?", "Its limitations?"]
    assert "remaining: 1" in seen[2][0].content
    assert len([m for m in seen[4] if isinstance(m, HumanMessage)]) == 1
    assert other["thread_id"] == "other"


def test_thread_cannot_change_paper():
    agent = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(),
                       bound_model=RunnableLambda(lambda _: AIMessage(content="No evidence")))

    async def run():
        await turn(agent, "Question")
        with pytest.raises(AgentConversationError, match="另一篇论文"):
            await turn(agent, "Question", file_id="other-paper")

    asyncio.run(run())


def test_no_evidence_answer_is_replaced_in_saved_history():
    seen = []

    def model(messages):
        seen.append(messages)
        return AIMessage(content="Invented unsupported fact")

    agent = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(),
                       bound_model=RunnableLambda(model))

    async def run():
        first = await turn(agent, "Question")
        second = await turn(agent, "Follow-up")
        return first, second

    first, second = asyncio.run(run())
    assert first["status"] == second["status"] == "no_evidence"
    assert all(m.content != "Invented unsupported fact" for m in seen[1])
    assert first["answer"] in [m.content for m in seen[1]]


def test_same_thread_overlapping_turn_is_rejected():
    async def run():
        started, release = asyncio.Event(), asyncio.Event()

        async def model(_):
            started.set()
            await release.wait()
            return AIMessage(content="No evidence")

        agent = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(),
                           bound_model=RunnableLambda(model))
        first = asyncio.create_task(turn(agent, "first"))
        await started.wait()
        try:
            with pytest.raises(AgentConversationError, match="正在执行"):
                await turn(agent, "second")
        finally:
            release.set()
            await first

    asyncio.run(run())


def test_failed_turn_cannot_append_to_unfinished_tool_protocol():
    def model(messages):
        if any(isinstance(m, ToolMessage) for m in messages):
            raise RuntimeError("provider failed")
        return call()

    agent = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(),
                       bound_model=RunnableLambda(model))

    async def run():
        with pytest.raises(AgentExecutionError):
            await turn(agent, "first")
        with pytest.raises(AgentConversationError, match="中断"):
            await turn(agent, "second")

    asyncio.run(run())


def test_omitted_thread_id_creates_new_conversations():
    agent = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(),
                       bound_model=RunnableLambda(lambda _: AIMessage(content="No evidence")))

    async def run():
        return await turn(agent, "first", thread_id=None), await turn(agent, "second", thread_id=None)

    a, b = asyncio.run(run())
    assert a["thread_id"] != b["thread_id"]
