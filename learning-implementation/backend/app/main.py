"""学习实现 · 阶段 1：最小 FastAPI 服务与健康检查。

对照源码：backend/app/main.py（原项目入口）
"""

import uvicorn
from fastapi import FastAPI

from app.routers.chat import router as chat_router
from app.routers.files import router as files_router
from app.routers.sessions import router as sessions_router

app = FastAPI(title="Learning RAG Backend")
app.include_router(chat_router)
app.include_router(files_router)
app.include_router(sessions_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    """健康检查：证明进程和路由都能正常工作。

    原项目的同名接口在 backend/app/routers/manage.py，会额外探测
    Milvus 与 LLM 的连通性；本阶段还没有这些依赖，所以先返回固定响应。
    """
    return {"status": "ok", "service": "learning-rag-backend"}


if __name__ == "__main__":
    # 端口用 8100：原项目 backend 占用 8000，练习服务错开避免冲突
    uvicorn.run("app.main:app", host="127.0.0.1", port=8100, reload=True)
