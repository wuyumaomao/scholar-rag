# 02. 后端骨架、API 与持久化

## 2.1 这一章的位置

上一章解决了“进程怎样启动”，本章解决“请求进入 backend 后发生什么”。在从零实现时，应该先做 API 骨架和最小持久化，再接 PDF、检索和 Agent；这样每个后续模块都有清晰的入口和错误边界。

源码阅读顺序：

1. `backend/app/main.py`
2. `backend/app/dependencies.py`
3. `backend/app/store.py`
4. `backend/app/routers/chat.py`
5. `backend/app/routers/files.py`
6. `backend/app/routers/sessions.py`
7. `backend/app/routers/manage.py`

## 2.2 FastAPI 应用是怎样组装的

`backend/app/main.py` 做四件事：

```python
app = FastAPI(title="Scholar RAG", lifespan=lifespan)
app.add_middleware(CORSMiddleware, ...)
app.include_router(chat.router)
app.include_router(sessions.router)
app.include_router(files.router)
app.include_router(manage.router)
```

### `lifespan` 为什么重要

RAG 系统有很多昂贵资源：数据库连接池、Embedding 模型、重排模型、Milvus 客户端、模型 API 客户端和 LangGraph checkpointer。如果每次请求都新建它们，延迟和资源消耗都会很高。

FastAPI 的 lifespan 把资源生命周期分成两段：

```text
服务器启动：创建共享资源 -> 保存到模块级变量
每个请求：通过 get_xxx() 取得已有资源
服务器关闭：关闭连接池、释放引用
```

当前 `dependencies.py` 的模块级变量有：

```python
_llm
_retriever
_retriever_tool
_pdf_parser
_rag_integration
_checkpointer
```

它们是当前项目的简单依赖注入方式。优点是 router 不需要知道如何初始化复杂对象；缺点是全局状态在单元测试中需要替换或谨慎隔离。

## 2.3 API 总表

| HTTP 方法 | 路径 | 输入 | 输出/作用 |
|---|---|---|---|
| `POST` | `/api/chat` | `query`、可选 `session_id`、可选 `paper_id` | SSE 事件流 |
| `GET` | `/api/sessions` | 无 | 会话元数据列表 |
| `GET` | `/api/sessions/{id}` | 会话 ID | 单个会话元数据 |
| `GET` | `/api/sessions/{id}/history` | 会话 ID | 从 checkpoint 恢复的消息 |
| `DELETE` | `/api/sessions/{id}` | 会话 ID | 删除元数据和 checkpoint thread |
| `POST` | `/api/files/upload` | multipart `files[]` | 每个文件的处理结果 |
| `GET` | `/api/files` | 无 | 文件元数据列表 |
| `DELETE` | `/api/files/{id}` | 文件 ID | 删除文件记录、向量和本地文件 |
| `DELETE` | `/api/collection` | 无 | 清空 collection、上传文件和记录 |
| `GET` | `/api/health` | 无 | Milvus 与 LLM 健康状态 |

这里的 `router = APIRouter(prefix="/api")` 或 `prefix="/api/files"` 决定了接口前缀。前端调用 `/api/...`，Nginx/Vite 再把它转发给 backend。

## 2.4 PostgreSQL 保存的不是一类东西

初学者最容易把“会话数据”当成一张表。当前项目实际上有两类不同的数据：

| 数据 | 保存位置 | 为什么分开 |
|---|---|---|
| 会话 ID、标题、创建/更新时间 | 自建 `sessions` 表 | 适合列表、排序、删除等业务查询 |
| 文件 ID、文件名、paper ID、大小、页数、chunk 数 | 自建 `files` 表 | 适合管理上传文件 |
| LangGraph 完整状态、消息、摘要、图执行 checkpoint | `AsyncPostgresSaver` 管理的表 | 由 LangGraph 根据 `thread_id` 恢复状态 |

`app/store.py` 只负责前两类业务表。它通过 `AsyncConnectionPool` 执行 SQL，并使用 `%s` 参数绑定而不是字符串拼接。

### sessions 表的作用

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at DOUBLE PRECISION NOT NULL,
    updated_at DOUBLE PRECISION NOT NULL
)
```

聊天结束时，`chat.py` 会用用户问题前 50 个字符作为首次会话标题。列表接口按 `updated_at DESC` 排序，因此最近聊天出现在侧边栏上方。

### files 表的作用

```sql
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    paper_id TEXT NOT NULL,
    size_bytes BIGINT NOT NULL DEFAULT 0,
    page_count INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at DOUBLE PRECISION NOT NULL
)
```

`file_id` 是上传实例的 UUID；`paper_id` 当前由 `Path(f.filename).stem` 生成，主要用于 Milvus metadata 过滤。它们不要混为一谈：删除文件 API 接收的是 `file_id`，检索范围选择传递的是 `paper_id`。

## 2.5 最小聊天接口应该怎样演进

从零写时不要一开始把 LangGraph 和 SSE 都塞进去。推荐四步：

```text
第 1 版 POST /api/chat -> 固定 JSON
第 2 版 POST /api/chat -> 调用一个文本模型
第 3 版 POST /api/chat -> 先检索再调用模型
第 4 版 POST /api/chat -> SSE + LangGraph + checkpoint
```

当前代码已经在第 4 版。请求模型是：

```python
class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    paper_id: str | None = None
```

进入 `chat(req)` 后：

1. 如果前端没有传 `session_id`，后端生成 UUID。
2. 如果 `sessions` 表没有记录，先调用 `create_session()`。
3. `_build_graph()` 通过共享 LLM、RetrieverTool、checkpointer 创建 LangGraph。
4. 返回 `EventSourceResponse`，真正处理留给异步生成器 `_stream_response()`。

这是一种很重要的架构分层：HTTP handler 负责鉴别/创建会话并返回流；领域工作在异步生成器和 Agent 图里完成。

## 2.6 SSE 事件是后端与前端的契约

`chat.py:_stream_response()` 产生 JSON 字符串，`sse-starlette` 将它们包装成 SSE 的 `data:` 行。事件顺序如下：

```text
session_id
status: analyzing
sub_queries              （如果分析节点产生子问题）
status: searching
answer                   （重复多次，data 是“目前累计答案”）
citations
done
```

发生异常时发出：

```json
{"type": "error", "data": "错误信息"}
```

注意 `answer` 事件不是单个 token，而是 `answer_buf` 的累计结果。这让前端逻辑简单：直接用事件中的内容替换当前未完成 assistant 消息。代价是越到后面每个 SSE 消息越大；如果要优化带宽，可改成增量 token 协议，但前后端需要一起改。

### 为什么最后还要 `aupdate_state`

流式生成完成后，代码调用：

```python
await graph.aupdate_state(config, {
    "messages": [
        HumanMessage(content=query),
        AIMessage(content=final_answer, additional_kwargs={"citations": final_citations}),
    ],
    "answer": final_answer,
})
```

这里将本轮用户/助手消息与 citation 写回 LangGraph checkpoint。之后 `GET /api/sessions/{id}/history` 才能根据同一 `thread_id` 恢复聊天记录。

## 2.7 文件上传接口的责任边界

`files.py:upload_files()` 不直接理解 Docling 和 Milvus 的内部细节，但负责协调它们：

```text
UploadFile
  -> PDF 后缀检查
  -> 读取内容、限制最大字节数
  -> SHA-256 内容哈希
  -> Milvus metadata 去重
  -> UUID 命名保存原文件
  -> PDFParser.parse()
  -> RAGIntegration.nodes_to_documents()
  -> RAGIntegration.create_chunks()
  -> RAGIntegration.store_in_milvus()
  -> add_file() 写 PostgreSQL
```

异常时，当前代码删除刚写入的原始 PDF，避免留下孤立上传文件。需要注意：若异常发生在部分 Milvus 写入之后，代码没有完整的向量事务回滚；这是未来可以加强的工程点。

## 2.8 删除为什么要跨多个存储系统

删除一个论文不是只删磁盘文件：

```text
DELETE /api/files/{file_id}
  -> 从 files 表取回记录并删除记录
  -> IncrementalUpdater.delete_paper(paper_id)
       -> 删除 parents/children collection 中同 paper_id 的向量
  -> 删除 uploads/{file_id}.pdf
  -> 删除 data/figures/{paper_id}/
```

这说明同一个业务对象有多个副本：关系数据、原始文件、裁图、父文档向量和子文档向量。设计删除流程时必须把它们全部列出来，否则就会产生“界面显示已删除但仍能检索到”的数据一致性问题。

## 2.9 管理接口与安全边界

`DELETE /api/collection` 会 drop 两个 Milvus collection、删除上传 PDF、删除裁图目录并清空 files 表。当前接口没有认证和权限检查。

`main.py` 还设置了：

```python
allow_origins=["*"]
allow_credentials=True
```

这对本地学习很方便，但不应直接暴露到公网。生产环境至少需要：身份认证、受限 CORS、删除操作权限、速率限制、文件内容安全检查和审计日志。

## 2.10 本章建议的最小验证

在未配置真实模型时，仍可逐层验证：

```bash
# 路由是否被注册
curl http://localhost:8000/openapi.json

# 会话列表（空数组也说明路由/数据库链路有效）
curl http://localhost:8000/api/sessions

# 健康接口
curl http://localhost:8000/api/health
```

真实上传与聊天需要 Docling、Milvus、Embedding/重排模型和 LLM 都可用。出现错误时先查看 backend 日志，再决定是 API 层、摄取层还是模型服务层的问题。

## 2.11 本章练习

1. 用自己的话解释 `sessions` 表和 LangGraph checkpoint 的区别。
2. 画出 `POST /api/chat` 到 `GET /api/sessions/{id}/history` 的完整状态流。
3. 写出删除一篇论文时必须删除的五类资源，并在源码中找到每一步。
4. 设计一个最小的“假 Retriever”，让 `/api/chat` 即使没有 Milvus 也能返回一段固定证据；这能帮助你分离 API 调试与检索调试。

## 下一章

下一章进入数据摄取：从一份 PDF 的二进制字节开始，跟踪它怎样变成 `PaperNode`、`Document`、chunk 和 Milvus 向量。
