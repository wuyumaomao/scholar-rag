# ScholarRAG 学习实现

这个目录用于跟随 `doc/learning/` 的章节，从最小可运行服务开始，逐步实现一个论文问答 RAG 项目。这里的代码是学习时亲手编写的版本，原项目的完整实现仍保留在 `backend/` 和 `frontend/` 中，供对照阅读。

## 学习约定

- 按 `doc/learning/README.md` 的顺序推进，每章只实现当前阶段需要的功能。
- 先尝试独立实现，再对照原项目，记录差异并运行验证。
- 不直接复制整套原项目代码；每个阶段都保持可运行、可检查。
- 本目录的应用与根目录的 Docker Compose 是分开的。运行练习服务时注意使用不同端口，避免和原项目冲突。

## 后端目录

学习版后端位于 `backend/`，`backend/app/` 按功能分组：

```text
app/
  main.py, config.py       应用入口和环境配置
  routers/                 FastAPI HTTP 接口
  agent/                   LangGraph 单任务模型/工具循环
  documents/               PDF 结构化解析和 parent/child chunk
  retrieval/               Embedding、Dense/BM25、RRF、rerank、HyDE、VLM
  generation/              基于检索证据组装提示词并调用 LLM
  evaluation/              benchmark 指标和解析/向量缓存
  storage/                 PostgreSQL 元数据和 Milvus parent/child 存储
```

## 前端目录

学习版 React + Vite 前端位于 `frontend/`。启动说明和页面/API 结构见 [`frontend/README.md`](frontend/README.md)。本地开发时先启动 8100 端口的 FastAPI，再启动 Vite（默认 5174）；Vite 将 `/api` 代理给学习版后端。

检索算法仍各自放在独立模块中，方便按知识点阅读和单独测试；`scripts/` 放手动运行的导出/评测工具，`tests/` 验证模块行为。

## 单任务 Agent

新增 `POST /api/agent`，使用 `StateGraph`、`MessagesState`、`ToolNode` 与条件边，让模型按需调用论文检索工具。默认最多处理 3 个工具请求，返回答案、状态、证据和执行轨迹。可在后端 `/docs` 输入已上传论文的 `file_id` 与 `query`；模型服务需支持 tool calling。

组件用途、运行方式和逐段讲解见 [agent-loop学习文档.md](agent-loop学习文档.md)。本版状态只存在于一次请求，尚未接入跨会话历史或 checkpoint。

## 计划里程碑

1. 最小 FastAPI 服务与健康检查接口。
2. 会话和最小聊天 API。
3. PDF 上传、解析与元数据存储。
4. 文本切分、向量化、混合检索与 Milvus 持久化。
5. 基于检索结果生成回答。
6. 前端交互、Docker 化和评测。

每完成一个阶段，都应补上对应的运行方式和验证步骤。当前目录从空白开始，后续代码会逐章加入。
