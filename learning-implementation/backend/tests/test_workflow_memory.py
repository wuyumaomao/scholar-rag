"""Memory survives workflow instances, but cannot replace retrieved evidence."""

import asyncio

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.agent.paper_agent import AgentConversationError
from test_paper_workflow import workflow, turn, task


def review(decision="pass", source_id="paper-parent"):
    return {"decision": decision, "issues": [] if decision == "pass" else ["Unsupported"],
            "retry_queries": [], "memory_candidates": [
                {"memory_type": "fact", "content": "The method uses depth estimation.",
                 "source_ids": [source_id]}]}


def test_fact_saved_recalled_by_new_thread_and_deduplicated():
    store = InMemoryStore()
    seen = []

    def planner(messages):
        seen.extend(m.content for m in messages)
        return {"tasks": [task("method")]}

    async def scenario():
        first = await turn(workflow(memory_store=store, reviewer=lambda _: review()))
        second = await turn(workflow(memory_store=store, planner=planner,
                                     reviewer=lambda _: review()), "What method?", thread="new")
        return first, second

    first, second = asyncio.run(scenario())
    assert first["trace"][-1]["saved"] == 1
    assert second["memories"][0]["content"] == "The method uses depth estimation."
    assert any("Relevant memories" in m for m in seen)
    assert len(store.search(("paper", "paper"))) == 1
    assert second["llm_calls_used"] == 4  # No extra memory LLM call.


@pytest.mark.parametrize("decision,source_id", [("pass", "invented-id"), ("insufficient", "paper-parent")])
def test_rejected_or_invalid_source_fact_is_not_written(decision, source_id):
    store = InMemoryStore()
    result = asyncio.run(turn(workflow(memory_store=store,
        reviewer=lambda _: review(decision, source_id))))
    assert result["trace"][-1]["saved"] == 0
    assert store.search(("paper", "paper")) == []


def test_recall_is_scoped_and_matches_chinese_topics():
    store = InMemoryStore()
    store.put(("paper", "paper"), "one", {"memory_type": "fact", "content": "模型使用深度估计方法。"})
    store.put(("paper", "other"), "two", {"memory_type": "fact", "content": "深度估计其他论文。"})
    agent = workflow(memory_store=store)
    recalled = agent._recall_memories("深度估计的方法是什么？", "paper")
    assert len(recalled) == 1
    assert recalled[0]["memory_id"] == "one"


def test_thread_cannot_change_user():
    saver = InMemorySaver()

    async def scenario():
        await turn(workflow(saver=saver, user_id="alice"))
        with pytest.raises(AgentConversationError, match="另一用户"):
            await turn(workflow(saver=saver, user_id="bob"))

    asyncio.run(scenario())
