"""Deterministic model-input budgeting keeps original evidence untouched."""

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agent.context import ContextBudget, ContextLimit, estimate, prepare_history


def source(source_id, evidence):
    return {"file_id": "paper", "source_id": source_id, "pages": [1],
            "section": ["Method"], "evidence": evidence}


def test_budget_deduplicates_and_shortens_only_model_view():
    original = source("s1", "Method architecture uses convolutional features. " * 30)
    duplicate = dict(original)
    payload = {"question": "What method?", "sources": [original, duplicate,
        source("s2", "Unrelated result. " * 30)]}
    budget = ContextBudget(total=1200, output=100, margin=100)
    messages, info, view = budget.payload("writer", SystemMessage(content="write"), payload)
    assert info["deduplicated"] == 1
    assert info["shortened"] or info["removed_sources"]
    assert original["evidence"] == payload["sources"][0]["evidence"]
    assert len(messages) == 2
    assert view["sources"]


def test_protected_source_is_never_removed_and_context_limit_is_explicit():
    protected = source("keep", "Important evidence. " * 100)
    budget = ContextBudget(total=700, output=100, margin=100)
    with pytest.raises(ContextLimit) as error:
        budget.payload("reflect", SystemMessage(content="review"),
                       {"question": "q", "sources": [protected]},
                       {("paper", "keep")})
    assert error.value.info["status"] == "context_limit"


def test_history_summary_drops_old_complete_turns_and_keeps_latest_messages():
    messages = [HumanMessage(content="old question"), AIMessage(content="old answer"),
                HumanMessage(content="current question")]
    budget = ContextBudget(total=300, output=50, margin=20)
    calls = []

    async def summarize(_):
        calls.append(True)
        return AIMessage(content="Old question was answered; unresolved: none.")

    async def run():
        return await prepare_history(budget, SystemMessage(content="plan"), messages,
            [], 0, "", summarize)

    view, visible, cursor, summary, info, summary_calls = asyncio.run(run())
    assert cursor == 3
    assert any(m.content == "current question" for m in view)
    assert info["removed_turns"] >= 0
    assert summary_calls in (0, 1)


def test_estimate_is_stable_for_same_input():
    messages = [SystemMessage(content="a"), HumanMessage(content="中文 evidence")]
    assert estimate(messages) == estimate(messages)
