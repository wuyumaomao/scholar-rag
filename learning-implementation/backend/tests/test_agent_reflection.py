"""Review completeness without silently changing answers or running retries."""

import asyncio
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableLambda

from app.agent.paper_agent import AgentExecutionError, PaperAgent
from app.config import Settings
from test_paper_agent import FakeRetrieval, call


def test_review_reads_current_question_and_answer_and_is_saved_per_turn():
    inspected = []

    def model(messages):
        user_index = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        if not any(isinstance(m, ToolMessage) for m in messages[user_index:]):
            return call()
        return AIMessage(content="Candidate answer")

    def reviewer(messages):
        inspected.append(messages)
        assert len(messages) == 2
        assert "Answer: Candidate answer" in messages[1].content
        return {"is_sufficient": len(inspected) > 1,
                "retry_queries": ["missing experiment"] if len(inspected) == 1 else []}

    service = FakeRetrieval()
    agent = PaperAgent(settings=Settings(), retrieval_service=service,
                       bound_model=RunnableLambda(model), bound_reviewer=RunnableLambda(reviewer))

    async def run():
        results = []
        for question in ["First question", "Second question"]:
            results.append(await agent.run(file_id="paper", pdf_path=Path("p.pdf"),
                                           figure_dir=Path("figures"), query=question, thread_id="thread"))
            snapshot = await agent.checkpointer.aget_tuple({"configurable": {"thread_id": "thread"}})
            assert snapshot.checkpoint["channel_values"]["review"] == results[-1]["review"]
        return results

    first, second = asyncio.run(run())
    assert "Question: First question" in inspected[0][1].content
    assert "Question: Second question" in inspected[1][1].content
    assert not first["review"]["is_sufficient"]
    assert second["review"]["is_sufficient"]
    assert first["answer"] == second["answer"] == "Candidate answer"
    assert first["trace"][-1] == {"node": "reflect", "review": first["review"]}
    assert len(service.calls) == 2  # suggestions are recorded, never executed


@pytest.mark.parametrize("output", [
    {"is_sufficient": "yes", "retry_queries": []},
    {"is_sufficient": True, "retry_queries": "bad"},
    RuntimeError("private provider secret"),
])
def test_failed_or_invalid_review_is_safe_error(output):
    def reviewer(_):
        if isinstance(output, Exception):
            raise output
        return output

    agent = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(),
                       bound_model=RunnableLambda(lambda messages: AIMessage(content="Answer")
                           if any(isinstance(m, ToolMessage) for m in messages) else call()),
                       bound_reviewer=RunnableLambda(reviewer))
    with pytest.raises(AgentExecutionError, match="Agent review failed") as error:
        asyncio.run(agent.run(file_id="paper", pdf_path=Path("p.pdf"),
                             figure_dir=Path("figures"), query="Question"))
    assert str(error.value) == "Agent review failed"


@pytest.mark.parametrize("empty, always_call", [(True, False), (False, True)])
def test_no_evidence_and_tool_limit_skip_reviewer(empty, always_call):
    def reviewer(_):
        pytest.fail("These paths must not invoke a reviewer")

    agent = PaperAgent(settings=Settings(), retrieval_service=FakeRetrieval(empty=empty),
                       max_tool_calls=1, bound_reviewer=RunnableLambda(reviewer),
                       bound_model=RunnableLambda(lambda messages: call() if always_call
                           or not any(isinstance(m, ToolMessage) for m in messages)
                           else AIMessage(content="No evidence")))
    result = asyncio.run(agent.run(file_id="paper", pdf_path=Path("p.pdf"),
                                  figure_dir=Path("figures"), query="Question"))
    assert result["review"] is None
    assert result["status"] == ("tool_limit" if always_call else "no_evidence")
