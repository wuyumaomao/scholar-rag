"""Lifecycle unit checks and optional live PostgreSQL restart checks."""

import asyncio
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from app.agent.persistence import postgres_agent_storage
from app.main import app
from app.routers import agent as api
from test_paper_workflow import workflow, turn
from test_workflow_memory import review


def test_application_lifespan_initializes_and_closes_storage(monkeypatch):
    saver, store = object(), object()
    events = []

    @asynccontextmanager
    async def storage(url):
        events.append("open")
        yield saver, store
        events.append("close")

    monkeypatch.setattr("app.main.postgres_agent_storage", storage)
    with TestClient(app) as client:
        assert api.checkpointer is saver
        assert api.memory_store is store
        assert client.get("/api/health").status_code == 200
    assert api.checkpointer is api.memory_store is None
    assert events == ["open", "close"]


def test_agent_storage_unavailable_never_falls_back_to_ram(monkeypatch):
    monkeypatch.setattr(api, "checkpointer", None)
    monkeypatch.setattr(api, "memory_store", None)
    response = TestClient(app).post("/api/agent", json={"file_id": "paper", "query": "method"})
    assert response.status_code == 503


LIVE_URL = os.getenv("AGENT_PERSISTENCE_TEST_URL")


@pytest.mark.skipif(not LIVE_URL, reason="Set AGENT_PERSISTENCE_TEST_URL for live PostgreSQL checks")
def test_workflow_recovers_completed_thread_and_fact_with_new_connections():
    thread, file_id = "persistence-test-" + str(uuid4()), "paper"
    seen = []

    async def scenario():
        try:
            async with postgres_agent_storage(LIVE_URL) as (saver, store):
                first = await turn(workflow(saver=saver, memory_store=store,
                    reviewer=lambda _: review()), "What method?", thread=thread, file_id=file_id)
                assert first["trace"][-1]["saved"] == 1
            # All backend connections/resources are closed, like a shutdown.
            async with postgres_agent_storage(LIVE_URL) as (saver, store):
                def planner(messages):
                    seen.extend(m.content for m in messages if isinstance(m, HumanMessage))
                    return {"tasks": [{"question": "method", "background": ""}]}
                second = await turn(workflow(saver=saver, memory_store=store, planner=planner),
                    "Explain the method", thread=thread, file_id=file_id)
                assert second["memories"][0]["source_ids"] == ["paper-parent"]
                snapshot = await saver.aget_tuple({"configurable": {"thread_id": thread}})
                assert len(snapshot.checkpoint["channel_values"]["messages"]) == 4
                assert "What method?" in seen
        finally:
            async with postgres_agent_storage(LIVE_URL) as (saver, store):
                await saver.adelete_thread(thread)
                for item in await store.asearch(("paper", file_id)):
                    await store.adelete(item.namespace, item.key)

    # psycopg async on Windows requires a selector loop (also used by reload).
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
        runner.run(scenario())


@pytest.mark.skipif(not LIVE_URL, reason="Set AGENT_PERSISTENCE_TEST_URL for live PostgreSQL checks")
def test_checkpoint_and_store_survive_separate_python_processes():
    identity = "process-test-" + str(uuid4())
    code = '''
import asyncio, os, sys
from langgraph.graph import StateGraph, START, END, MessagesState
from langchain_core.messages import HumanMessage
from app.agent.persistence import postgres_agent_storage
async def main():
    identity, mode = sys.argv[1:]
    config = {"configurable": {"thread_id": identity}}
    async with postgres_agent_storage(os.environ["AGENT_PERSISTENCE_TEST_URL"]) as (saver, store):
        builder = StateGraph(MessagesState)
        builder.add_node("echo", lambda state: {})
        builder.add_edge(START, "echo")
        builder.add_edge("echo", END)
        graph = builder.compile(checkpointer=saver)
        if mode == "write":
            await graph.ainvoke({"messages": [HumanMessage(content="persisted")]}, config)
            await store.aput(("test", identity), "fact", {"content": "persisted"})
        elif mode == "read":
            state = await graph.aget_state(config)
            assert state.values["messages"][0].content == "persisted"
            assert not state.next
            assert (await store.aget(("test", identity), "fact")).value["content"] == "persisted"
        else:
            await saver.adelete_thread(identity)
            await store.adelete(("test", identity), "fact")
with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None) as runner:
    runner.run(main())
'''
    try:
        for mode in ("write", "read"):
            result = subprocess.run([sys.executable, "-c", code, identity, mode],
                                    capture_output=True, text=True, timeout=60)
            assert result.returncode == 0, result.stderr
    finally:
        subprocess.run([sys.executable, "-c", code, identity, "cleanup"],
                       capture_output=True, text=True, timeout=60, check=True)
