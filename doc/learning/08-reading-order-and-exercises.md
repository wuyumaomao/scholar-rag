# 08. 逐文件阅读顺序与练习路线

## 8.1 不要一次读完整个仓库

当前最大的核心文件是 `backend/rag/integration.py`，其次是 `backend/agent/nodes.py`。如果从头到尾硬读，很容易在细节中失去数据流。下面的顺序每次只回答一个问题，并且每个阶段都有可以运行或观察的里程碑。

## 8.2 第一遍：只建立地图

按这个顺序快速浏览，每个文件只写三句话：职责、输入、输出。

1. `README.md`：产品目标、技术栈和安全限制。
2. `docker-compose.yml`：有哪些进程和网络边界。
3. `Makefile`：开发者如何启动、测试和构建。
4. `backend/config.py`：哪些环境变量控制运行行为。
5. `backend/app/main.py`：FastAPI 如何注册应用。
6. `frontend/src/main.jsx`：浏览器从哪里挂载 React。
7. `frontend/src/App.jsx`：页面有哪些共享状态。

第一遍结束时，你不需要知道任何 RRF 公式，只要能画出：

```text
浏览器 -> frontend -> backend -> Milvus / PostgreSQL / 模型 API
```

## 8.3 第二遍：先看最短可运行链

### 阶段 A：健康检查

阅读：

- `app/main.py`
- `app/dependencies.py` 的 `lifespan` 前半部分
- `app/routers/manage.py:health`

问题：backend 启动完成后，`/api/health` 如何分别检查 Milvus 和 LLM？

练习：不打开前端，直接请求健康接口并记录两项状态。

### 阶段 B：会话

阅读：

- `app/store.py`
- `app/routers/sessions.py`
- `frontend/src/components/Sidebar.jsx`

问题：会话列表元数据和完整消息历史为什么来自不同调用？

练习：画出点击侧边栏会话后 `fetchHistory()` 到 UI 的状态变化。

### 阶段 C：聊天入口

阅读：

- `app/routers/chat.py`
- `frontend/src/api.js:streamChat`
- `frontend/src/App.jsx:handleSend`

问题：一次 POST 为什么返回 SSE，而不是普通 JSON？

练习：把事件协议写成表格，并指出每个事件由哪个后端节点触发。

## 8.4 第三遍：数据摄取

按以下顺序，不要反过来：

1. `app/routers/files.py`：谁协调上传流程。
2. `rag/models.py`：中间数据结构是什么。
3. `rag/node_generator.py`：节点文本怎样生成。
4. `rag/integration.py:PDFParser`：如何从 Docling item 得到节点。
5. `rag/integration.py:RAGIntegration`：如何变成 Document 和 chunk。
6. `rag/incremental.py`：删除/更新如何作用于两个 collection。

每读一个文件，追踪同一个字段：`paper_id`。它从文件名生成，进入 PaperNode、Document metadata、Milvus filter、前端 select 和删除流程。能够完整追踪这个字段，就说明你开始理解跨模块契约了。

## 8.5 第四遍：检索

阅读顺序：

```text
rag/factory.py
rag/retrieval.py:Retriever.__init__
rag/retrieval.py:Retriever.retrieve
rag/cache.py
rag/citation.py
agent/nodes.py:retrieve
```

每一层只问一个问题：

| 层 | 问题 |
|---|---|
| factory | 模型和 store 是否重复加载？ |
| retrieve | 候选怎样变成最终 k 个结果？ |
| cache | 为什么相似问题能命中，但不同论文不能串？ |
| citation | 页码和章节从哪来？ |
| agent retrieve | query type 和 paper ID 如何传入？ |

练习：固定一个问题，分别关闭 rerank、parent expansion 和 cache，记录结果数量、内容和延迟。

## 8.6 第五遍：Agent 图

阅读顺序一定是：

1. `agent/states.py`：状态字段和 reducer。
2. `agent/prompts.py`：每个结构化输出的契约。
3. `agent/nodes.py`：节点内的业务逻辑。
4. `agent/graph.py`：节点如何连成主图和子图。
5. `app/routers/chat.py`：图的 stream 如何映射到 SSE。

如果先读 `graph.py`，你会只看到节点名；先读 state 和 prompt，才能知道每条边传递的东西。

练习：手写下面问题的状态变化：

```text
用户问：“方法如何工作？实验结果如何？”
```

至少标注 `query_type`、`sub_queries`、两个子 Agent 的 citations 和最终 synthesis prompt。

## 8.7 第六遍：前端

阅读顺序：

```text
main.jsx -> App.jsx -> api.js -> ChatMessages.jsx
         -> ChatInput.jsx -> Sidebar.jsx
         -> FileUpload.jsx -> SettingsPanel.jsx
```

练习：给每一个 React state 写“谁写它、谁读它、何时清空”。特别关注：

- `currentId`：新聊天、收到 `session_id`、切换会话；
- `messages`：用户输入、累计 answer、citations 完成；
- `paperId`：文件刷新、用户 select、文件删除；
- `loading`：发送、done、error。

## 8.8 按阶段完成的实现练习

### 练习 1：假后端

创建一个只返回固定答案的 `/api/chat`，用当前前端确认 SSE 解析和状态更新正确。不要接数据库。

### 练习 2：假检索

让 Retriever 返回两条内存中的 `Document`，带 `paper_id`、`page_num` 和 `section_path`，验证 citation 在前端能展开显示。

### 练习 3：真实摄取、手工检索

用一份小 PDF 运行解析脚本，检查节点；再写一个脚本只调用 `RAGIntegration` 和 `Retriever`，暂时绕过 Agent。

### 练习 4：单 Agent

实现：

```text
query -> retrieve -> prompt -> llm -> answer
```

要求答案中的每个事实都有 `[i]`，并将 citation 单独返回。

### 练习 5：加入分类和过滤

实现四类 query type，并观察 `method` 问题和 `experiment` 问题的召回章节是否不同。给无结果的过滤增加回退日志。

### 练习 6：多 Agent

先固定 `sub_queries`，只验证 `Send` 和 reducer；再接入 LLM 自动分解。这样可以把图并行问题和 Prompt 问题分开。

### 练习 7：SSE 可观测性

在前端显示当前阶段、子问题数量和最终引用数量。确保错误事件能让输入框恢复可用。

### 练习 8：VLM 接线

只有在普通文本链路稳定后再做：

1. 创建独立的 VLM `ChatOpenAI` 客户端；
2. 创建并缓存 `VisionService`；
3. 将它传入 `build_graph()`；
4. 保证检索证据保留 `image_path`，不要只传展示用的简化 citation；
5. 用一个固定 figure 图片写单独集成测试。

### 练习 9：生产化

添加认证、限制 CORS、统一错误响应、请求超时、日志 trace ID、异步上传任务和 Milvus/PostgreSQL 补偿机制。

## 8.9 每个里程碑的完成证据

| 里程碑 | 不要只说“完成”，要保留的证据 |
|---|---|
| M0 | `/api/health` 返回 JSON |
| M1 | 一次 POST 聊天得到固定或模型答案 |
| M2 | `GET /api/files` 和 `GET /api/sessions` 有记录 |
| M3 | parse report 的节点类型和页码统计 |
| M4 | Milvus parents/children collection 存在 |
| M5 | 固定问题的检索日志和 source metadata |
| M6 | 单 Agent 答案与 citation 对应 |
| M7 | `sub_queries` 和 reducer 结果日志 |
| M8 | 浏览器看到逐步增长的 answer |
| M9 | `docker compose ps` 全部健康 |
| M10 | 固定数据集的指标报告和人工抽样 |

## 8.10 最后形成自己的项目讲解

当你能完成上面的练习后，可以用以下顺序介绍项目：

1. 业务目标：论文上传和带引用问答；
2. 两条数据流：离线摄取与在线问答；
3. 结构化摄取：Docling、PaperNode、父子分块；
4. 混合检索：Dense、BM25、RRF、重排、parent expansion；
5. Agent 编排：记忆、分类、分解、并行子图、合成；
6. 工程交付：FastAPI、SSE、React、Compose、PostgreSQL；
7. 当前取舍和限制：无鉴权、VLM 未完全接线、配置和测试卫生问题；
8. 下一步改进：可观测性、评测、可靠性和生产安全。

如果能按“问题 -> 数据结构 -> 函数 -> 服务 -> 验证证据”讲清每一层，你就不是在背项目，而是在理解它。
