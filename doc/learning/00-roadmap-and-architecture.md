# 00. 从 0 到 1 的路线与整体架构

## 0.1 先把问题说具体

ScholarRAG 的目标不是泛泛地“做一个聊天机器人”，而是解决一个可验证的论文问答任务：

> 用户上传一篇或多篇学术 PDF，用自然语言提出问题；系统从论文中找到相关证据，生成答案，并告诉用户证据来自哪篇论文、哪一节、哪一页。

这句话决定了系统不能只调用 LLM。LLM 本身不知道用户刚上传的论文，因此它需要一套外部知识流程：把 PDF 解析、保存、检索，再将检索证据放回模型上下文。这个模式叫 **Retrieval-Augmented Generation，RAG**。

对 ScholarRAG 来说，“论文”又比普通网页或纯文本复杂：它包含章节、双栏段落、表格、图片、图注和公式。所以这里是**结构感知 RAG**，不是简单地按固定字符数把整份 PDF 切开。

## 0.2 两条必须分开的主链路

系统有两种不同时间发生的工作。先把它们分开，后面的模块才不会混乱。

### A. PDF 摄取链路：上传时发生

```text
浏览器选择 PDF
  -> POST /api/files/upload
  -> 校验类型、大小、内容哈希
  -> 保存原始 PDF
  -> Docling 解析论文结构
  -> PaperNode（段落、表格、图片等）
  -> Document（检索文本 + metadata）
  -> parent/child 分块
  -> 写入 Milvus
  -> 在 PostgreSQL 写入文件元数据
```

这条链路的产物是“可搜索的论文知识库”。它耗时相对长，尤其是 PDF 解析、下载 Embedding 模型和第一次写入向量库时。

### B. 在线问答链路：每次提问发生

```text
浏览器发送问题
  -> POST /api/chat
  -> LangGraph 恢复会话状态
  -> 总结历史 / 分类问题 / 拆分子问题
  -> 一个或多个子 Agent 并行检索
  -> 每个子 Agent 根据证据生成局部答案
  -> 汇总子答案和引用
  -> 最终 LLM 流式生成
  -> SSE 回传浏览器
  -> 将本轮消息保存到 checkpoint
```

这条链路追求低延迟和正确性。它不应该重复解析 PDF，而应直接使用摄取阶段建好的索引。

## 0.3 当前项目的总体架构

```text
┌─────────────────────── 浏览器 ───────────────────────┐
│ React: 会话列表 / 聊天 / 上传 / 设置 / 论文范围选择    │
└───────────────────────┬──────────────────────────────┘
                        │ HTTP + SSE
┌───────────────────────▼──────────────────────────────┐
│ FastAPI backend                                        │
│  app/routers: chat / files / sessions / manage         │
│  app/dependencies: 生命周期、共享单例、连接池           │
│  agent/: LangGraph 主图和子图                           │
│  rag/: 解析、分块、入库、检索、缓存、引用               │
└───────┬───────────────────┬─────────────────────┬─────┘
        │                   │                     │
        ▼                   ▼                     ▼
   PostgreSQL            Milvus         OpenAI-compatible API
  会话/文件元数据       父子文档索引      文本 LLM；可选 VLM
  LangGraph checkpoint  Dense + BM25
```

部署时，`docker-compose.yml` 创建四个本地服务：

| 服务 | 当前职责 | 对外端口 |
|---|---|---:|
| `backend` | FastAPI、LangGraph、PDF/RAG 代码 | 8000 |
| `frontend` | Nginx 静态站点和 `/api/` 代理 | 5173 映射到容器 80 |
| `milvus` | 向量数据库、Dense 与 BM25 索引 | 19530、9091 |
| `postgres` | 会话、文件元数据、checkpoint | 5432 |

外部文本模型和 VLM 不是 Compose 中的服务；项目通过 API URL 调用它们。它们可以运行在宿主机、另一台机器，或云端。

## 0.4 为什么“从零实现”的顺序不能按文件夹顺序

一个模块能否实现取决于它的输入是否已经存在：

```text
配置与运行环境
       ↓
FastAPI 生命周期和基础接口
       ↓
文件 / 会话持久化
       ↓
PDF -> PaperNode
       ↓
PaperNode -> Document -> parent/child chunks
       ↓
Milvus 检索
       ↓
单 Agent 检索问答
       ↓
LangGraph 分类、拆分、并行子 Agent
       ↓
SSE 流式传输与 React 界面
       ↓
Docker、评测、安全与性能优化
```

例如：

- `agent/nodes.py:retrieve()` 的输入是 Retriever 返回的 `Document`，所以必须先有分块和 Milvus。
- `frontend/src/api.js` 的 `streamChat()` 等待 SSE 事件，所以必须先定义 `chat.py` 发出的事件协议。
- “反思重试”依赖已有一次生成答案，不能在最小版本中优先实现。

这个依赖图就是本文档的章节顺序。

## 0.5 建议的 12 个实现阶段

### 阶段 0：写出最小问题与接口契约

先定义输入和输出，而不是先选框架：

```json
// 请求
{"query": "这篇论文的核心方法是什么？"}

// 最小响应
{"answer": "暂未接入检索。"}
```

目标：证明“用户问题可以到达后端并返回结果”。第一版可以没有数据库、没有 PDF、没有模型。

### 阶段 1：FastAPI 最小骨架

实现 `app/main.py`、`/api/health`、`/api/chat`。把环境变量集中放入 `config.py`，不要将地址、模型名和密钥散落在业务函数里。

完成标准：启动 Uvicorn 后，浏览器或 curl 能得到 JSON 响应。

### 阶段 2：会话与文件元数据

接入 PostgreSQL。此时先保存 `session_id`、标题、上传文件名、大小和处理结果；不要把整篇 PDF 或聊天原文塞进普通业务表。

完成标准：创建会话后可以列出、删除；文件上传后可以列出文件记录。

### 阶段 3：PDF 结构化解析

实现 `PDFParser`。先用 Docling 抽取结构项，随后处理页眉页脚、页码、阅读顺序、章节路径、图注和表格。这一步的输出是 `PaperNode`，不是向量。

完成标准：对一篇测试论文打印节点数量、类型、页码和前几段文本。

### 阶段 4：检索文档、分块与入库

将 `PaperNode` 转为 LangChain `Document`，并给每个文档添加 `paper_id`、`node_type`、页码、章节等 metadata。然后建立完整 parent 和更细 child 两套文档，写入 Milvus。

完成标准：Milvus 中出现 `{collection}_parents` 与 `{collection}_children` 两个 collection。

### 阶段 5：最小检索

先实现“问题 -> 向量搜索 -> 返回几段文本”。这一步的作用是让你能独立测量检索，而不是把检索错误误判为 LLM 错误。

完成标准：一个固定问题能返回可人工检查的原文片段和页码。

### 阶段 6：检索增强

在最小检索工作后，增加 BM25、RRF、CrossEncoder 重排、父块回溯、过滤条件、缓存和引用提取。每一项都应当可以单独开关或做 A/B 对比。

完成标准：知道参数 `FETCH_K`、`TOP_K`、`RRF_K` 分别在何处生效。

### 阶段 7：单 Agent 基于证据回答

把检索结果编号并加入 Prompt，调用一个 LLM 生成答案。先确保模型只根据上下文回答，并且能给出来源编号；此时不急着拆子问题。

完成标准：普通问题能拿到答案与 citation 列表。

### 阶段 8：升级为 LangGraph 多 Agent

增加会话摘要、意图分类、查询分解、子 Agent 并行执行和最终合成。此时 LangGraph 的价值才出现：它让过程变成有状态的图，而不是一串难以维护的 `if/else`。

完成标准：复杂问题会产生 `sub_queries`，并且多个子 Agent 返回的答案被统一合成。

### 阶段 9：SSE 流式输出

让最终生成时逐块返回文本，后端发出状态、子问题、答案、引用和完成事件，前端实时更新 UI。

完成标准：浏览器在答案生成期间持续显示内容，而不是等全部完成才显示。

### 阶段 10：React 产品界面

实现会话侧边栏、消息列表、输入框、上传面板、文件设置和论文范围选择。前端只管理 UI 状态；论文解析、检索和生成仍在 backend。

完成标准：用户不需要 curl 就能完成上传、提问、切换会话和删除文件。

### 阶段 11：Docker 化

将服务运行环境变成可复现配置：backend、frontend、Milvus、PostgreSQL 各自封装，Compose 描述网络、卷、端口和启动依赖。

完成标准：新机器配置 `.env` 后能用 `docker compose up -d --build` 启动。

### 阶段 12：评测与生产化改进

最后再测 Recall@k、MRR、MAP、RAGAS，处理鉴权、CORS、超时、模型费用、日志、错误恢复与可观测性。不要在最小链路没跑通前提前做这些优化。

## 0.6 当前源码入口表

| 领域 | 优先阅读的文件 |
|---|---|
| 配置和启动 | `backend/config.py`、`backend/app/main.py`、`backend/app/dependencies.py` |
| 路由和数据库 | `backend/app/routers/*.py`、`backend/app/store.py` |
| PDF 结构 | `backend/rag/models.py`、`backend/rag/integration.py` |
| 检索文本 | `backend/rag/node_generator.py` |
| 检索 | `backend/rag/retrieval.py`、`backend/rag/cache.py`、`backend/rag/citation.py` |
| Agent | `backend/agent/states.py`、`graph.py`、`nodes.py`、`prompts.py` |
| 前端 | `frontend/src/App.jsx`、`frontend/src/api.js`、`frontend/src/components/` |
| 部署和测试 | `docker-compose.yml`、Dockerfile、Makefile、`backend/test/`、`backend/eval/` |

## 0.7 当前代码的边界，学习时要如实区分

1. 当前应用确实实现了主文本问答、论文范围 `paper_id` 过滤、父子检索和 SSE。
2. VLM 的 `VisionService` 与配置变量已经存在，但 `app/dependencies.py` 没有构造它，`chat.py:_build_graph()` 也没有向 `build_graph()` 传入 `vision_service`。因此 VLM 不是当前聊天链路的已启用能力。
3. `MAX_RETRIES` 在 `.env.example` 中是 `0`，在 `config.py` 的默认值是 `2`。真正运行时以你的 `.env` 为准；`0` 会使反思节点完全不编译进子图。
4. 测试中既有可用于逻辑验证的代码，也有依赖本地 PDF、模型和 Milvus 的脚本。不能把“文件存在”误解成“CI 已全部跑通”。

## 0.8 下一章

下一章从环境与启动开始：解释 Docker 为什么要有多个容器、backend 如何读配置，以及本机、容器和云端模型 API 的地址应该怎样区分。
