"""Official LangGraph PostgreSQL backends, owned by application lifespan."""

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore


@asynccontextmanager
async def postgres_agent_storage(database_url: str):
    # The learning PostgreSQL service already has a persistent Docker volume.
    # setup() applies additive, versioned LangGraph migrations to existing DBs;
    # docker-entrypoint init.sql alone would not update an existing volume.
    async with AsyncPostgresSaver.from_conn_string(database_url) as saver:
        async with AsyncPostgresStore.from_conn_string(database_url) as store:
            await saver.setup()
            await store.setup()
            yield saver, store
