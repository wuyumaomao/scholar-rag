# ScholarRAG 项目总览（面试介绍稿）

> 面向学术论文的多 Agent RAG 问答系统。
> 上传 PDF → 结构化解析入库 → 自然语言提问 → 并行检索与生成 → 带引用的流式回答。

本文对应代码为当前工作区版本，行号与参数均可在源码中复核。

---

## 1. 一句话定位与亮点

**ScholarRAG** 是一个端到端的学术论文问答系统：它不是「把 PDF 切片塞进向量库」的简单 RAG，
而是围绕**文档结构感知**（章节树 / 表格 / 图片 / 公式）、**混合检索**（BM25 + 向量 + 重排 + 父子块回溯）、
**多 Agent 编排**（LangGraph 查询分解与并行子代理）三件事构建的完整系统。

30 秒版本：

1. 上传论文，Docling 按文档结构解析成 6 类语义节点，父子双粒度分块写入 Milvus（稠密 + BM25 双索引）
2. 提问时，LangGraph 主图先压缩多轮记忆、分类查询意图、分解子问题，
   再用 `Send` 机制并行派发多个子代理独立走「检索 → 生成」子图
3. 检索侧：混合召回 + RRF 融合 + CrossEncoder 重排 + 父块回溯 + 按论文范围过滤
4. 最后汇总各子答案、重编号引用，以 SSE 流式输出带 `[n]` 引用的回答

---

## 2. 技术栈总览

| 层 | 选型 | 说明 |
|---|---|---|
| 语言 / 运行时 | Python 3.12, Node 18 | Docker 内锁版本 |
| 编排 | LangGraph + LangChain | 主图 + 子图两级状态机，`Send` 并行分发 |
| 后端 | FastAPI + Uvicorn + sse-starlette | SSE 流式接口 |
| 向量库 | Milvus 2.5 standalone | 单 collection 双索引：dense + BM25 `BuiltInFunction` |
| 嵌入 / 重排 | BAAI/bge-small-en-v1.5；CrossEncoder（ms-marco MiniLM） | sentence-transformers 单例加载 |
| 解析 | Docling + PyMuPDF | 结构解析 + bbox 裁图 |
| 持久化 | PostgreSQL 16 | LangGraph checkpointer + 会话/文件元数据（双用途） |
| 前端 | React 18 + Vite + TailwindCSS | 手写 fetch + ReadableStream 解析 SSE |
| 部署 | docker-compose 四服务 | backend / frontend(nginx) / milvus / postgres，带健康检查 |

代码规模：后端约 4200 行 Python，前端约 700 行 JSX/JS。

---

## 3. 整体架构图

```text
┌─────────────────────────── 数据摄取链路（上传时，离线一次） ───────────────────────────┐
│                                                                                      │
│  PDF 上传 ──> 校验/50MB ──> SHA256 内容去重(查 Milvus metadata)                        │
│      │                                                                               │
│      └──> Docling 解析 ──> 噪声过滤(页眉/页脚/页码) ──> 双栏阅读序排序(bbox)            │
│              │                                                                       │
│              ├──> PaperNode × 6 类: section_header/paragraph/table/figure/caption/formula │
│              ├──> 图注↔图片关联、正文引用关联                                          │
│              └──> PyMuPDF 按 bbox 2x DPI 裁图 ──> data/figures/{paper_id}/            │
│                      │                                                               │
│              node_generator(6 类生成器, 表格线性化 key=value)                          │
│                      │                                                               │
│              父子分块: parent=完整语义单元 / child=500字,50重叠(结构节点不切)            │
│                      │                                                               │
│              └──> Milvus: papers_parents + papers_children (dense + BM25 sparse)      │
│              └──> PostgreSQL files 表(元数据)                                         │
└──────────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────── 问答链路（在线，每次请求） ────────────────────────────────┐
│                                                                                      │
│  POST /api/chat (SSE)                                                                │
│      │                                                                               │
│      └──> LangGraph 主图:                                                            │
│             summarize(窗口6轮,超窗压缩) ─> classify(四分类意图) ─> analyze(分解子查询)  │
│                    │                                                                 │
│                    └─ Send × N ──> 子代理(并行): retrieve ─> generate ─(>END)         │
│                                          │                                           │
│                             混合检索(BM25+dense, RRF) ─> CrossEncoder 重排             │
│                             ─> 父块回溯 ─> 去重 ─> Top-K                              │
│                    │                                                                 │
│             prepare_synthesis(聚合子答案, 引用重编号) ─> synthesize(LLM 流式生成)       │
│      │                                                                               │
│      └──> SSE 事件流: session_id → status → sub_queries → answer(token) → citations → done │
│      └──> aupdate_state 写回 PostgreSQL checkpointer(多轮记忆)                         │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 链路一：PDF 摄取（`app/routers/files.py` + `rag/integration.py`）

**步骤与关键细节（面试可展开的点加粗）：**

1. **校验与去重**：只收 PDF、限 50MB；去重不是比文件名，而是 **SHA256 内容哈希查 Milvus metadata**
   （`IncrementalUpdater.has_content_hash`），同名不同内容能各自入库，同内容不同名只入一次。
2. **Docling 解析**：识别 `SectionHeaderItem / TextItem / TableItem / PictureItem / FormulaItem` 等结构元素。
3. **OCR 兜底**：先按快速文本模式解析；若全文 < 1000 字符或平均每页 < 200 字符，判定为扫描件，
   自动开 OCR 重新解析——**避免对纯文本 PDF 浪费 OCR 时间**。
4. **噪声过滤与阅读序**：去掉页眉/页脚/页码；按 bbox 做「行分组 + 页内从上到下、行内从左到右」排序，
   **正确处理双栏论文的阅读顺序**；用章节标题维护一个 section_stack 得到层级路径。
5. **语义节点**：统一为 `PaperNode`（node_id / paper_id / node_type / text / page_num / section_path / bbox / image_path / related_ids）。
6. **图文关联与裁图**：图注匹配到图片节点、正文 "Figure 3" 类引用关联到对应节点；
   PyMuPDF 按 Docling 给的 bbox 以 2x DPI 裁 PNG（**坐标系转换**：Docling 原点在左下，fitz 在左上，
   `fitz_y = page_height - docling_y`）。
7. **检索文本生成**（`node_generator.py`）：工厂模式按 node_type 选生成器——段落补章节路径、
   **表格线性化成 `Row N: header1=val1, ...`**（让表格可被 BM25/向量召回）。
8. **父子分块**（`RAGIntegration.create_chunks`）：每个 Document 保留为 parent（完整语义单元）；
   普通长文本按 500 字符 / 50 重叠切 child；**表格、图片、标题、图注不切分**。
   child 带 `chunk_parent_id` 指回 parent。
9. **入库**：写入 `papers_parents` 与 `papers_children` 两个 collection，
   **同时建 dense 向量索引和 BM25 sparse 索引**；元数据落 PostgreSQL `files` 表。

**为什么父子双粒度**：child 短、语义聚焦，检索命中率高；parent 长、上下文完整，命中后回溯取全文给 LLM。
这是「检索精度」与「生成上下文质量」的解耦。

---

## 5. 链路二：问答（`app/routers/chat.py` + `agent/`）

### 5.1 主图流程

```text
START → summarize → classify → analyze → [sub_agent × N 并行] → prepare_synthesis → synthesize → END
```

| 节点 | 职责 | 关键点 |
|---|---|---|
| `summarize` | 多轮记忆管理 | 滑动窗口 6 轮；超窗历史用 LLM 压缩成 summary，`RemoveMessage` 清理旧消息防 context 膨胀 |
| `classify` | 意图分类 | 结构化输出四类：`experimental_result / method / background / general`，失败兜底为 general |
| `analyze` | 查询分解 | LLM 把复杂问题拆成若干子查询（原子查询排首位）；**通过 `Send` 机制每个子查询独立派发一个子代理，天然并行** |
| `prepare_synthesis` | 聚合 | 收集各子代理答案与引用，**引用编号按偏移重映射**（每个子代理都从 [1] 开始编号），构造汇总 prompt |
| `synthesize` | 最终生成 | `llm.astream()` 逐 token 流式输出，SSE 实时推给前端 |

### 5.2 子代理子图（每个子查询独立执行）

```text
START → retrieve → generate → END          （MAX_RETRIES=0，默认：反思关闭）
START → retrieve → generate → reflect → [retry | done]   （MAX_RETRIES≥1 时编译进图）
```

- `retrieve`：按 `query_type` 取 `section_type` 过滤（如实验类问题只搜实验章节）；
  多个查询用 `run_in_executor` 并发检索；**某过滤条件下检索为空时，自动放弃该过滤重试一次**（宁可宽不可空）；
  前端选了论文范围时，附带 `paper_id` 过滤表达式（引号已转义）。
- `generate`：把检索文档编号成 `[1] ... [n]` 填入上下文，要求回答挂引用；
  视觉类问题可触发 VLM 分析图片（默认关闭，见 §7）。
- `reflect`（可选）：LLM 结构化判断「答案是否充分」，不充分则生成补充查询回环重试。
  **`MAX_RETRIES=0` 时这两个节点根本不编译进图**——这是刻意的成本取舍：反思每轮要多一次
  结构化 LLM 调用，默认配置下选择省掉它；能力保留，一个环境变量可开。

### 5.3 SSE 事件协议（前后端契约）

```text
session_id → status(analyzing) → sub_queries → status(searching)
           → answer(token × N) → citations → done
```

前端 `api.js` 用 `fetch + ReadableStream` 手动解析 SSE，`AbortController` 支持中途取消；
回答完成后后端 `aupdate_state` 把本轮 Human/AI 消息写回 PostgreSQL checkpointer，实现跨请求多轮记忆。

---

## 6. 检索管道细节（`rag/retrieval.py`，面试重点）

```text
Query → [可选 HyDE] → 混合召回(dense + BM25, RRF k=60, fetch_k×2 候选)
      → CrossEncoder 重排 → 父块回溯(chunk_parent_id) → chunk_id 去重 → Top-K(5)
```

- **RRF 融合**：稠密与稀疏两路结果按倒数排名融合，`k=60` 抑制头部排名的过度主导；
  不用加权分数是因为两路分数量纲不可比，RRF 只用排名，鲁棒。
- **语义缓存**：不是精确 key，而是查询 embedding 余弦相似度 ≥ 0.95 即命中；
  **缓存 scope = (paper_id, node_type_filter, section_type_filter)**——
  相似问题跨论文/跨过滤条件绝不串号；读写加 `RLock`，LRU 上限 1000。
- **过滤表达式安全**：`paper_id` 拼进 Milvus 表达式前做反斜杠/双引号转义，并有单测覆盖
  （`test/test_paper_filter.py`）。
- **一个真实的工程坑**（面试好素材）：langchain-milvus 内部用 `MilvusClient`，
  但读取已有 collection schema 走 PyMilvus ORM 的 `Collection(using=alias)`，
  新版 pymilvus 不会自动把 client 的连接注册进 ORM 注册表，导致运行时报找不到 collection。
  解决方案是在 `MilvusStoreFactory` 里把 `MilvusClient` 的 handler 桥接注册进
  `connections` 注册表（`_register_orm_connection`），并升级 Milvus 2.4 → 2.5 以获得
  内置 BM25 function 支持。

---

## 7. 默认关闭的能力与设计取舍（主动讲，体现判断力）

| 能力 | 状态 | 取舍理由 |
|---|---|---|
| 反思重试（reflect + retry） | **默认关**（`MAX_RETRIES=0`，节点不编译进图） | 每个子查询省一次结构化 LLM 调用；能力保留，配置即可开启。适合演示环境延迟与成本优先 |
| VLM 图表理解 | 默认关（`VLM_ENABLED=false`） | 挂在 reflect 内部的兜底路径 + 视觉关键词主动触发双路设计仍在；需要多模态端点 |
| HyDE 查询扩展 | 实现了，默认不启用 | 每查询多一次 LLM 调用，收益依赖场景 |
| 鉴权 | 无 | 定位为本地/内网学习与研究工具，README 有明确 Security Notice |

这段的面试话术：**「这些能力都实现了，但我根据部署场景做了默认关闭的取舍，并且关闭方式是
『不编译进图』而不是『跑了再丢弃』——省掉的是整次 LLM 往返，而不只是忽略结果。」**

---

## 8. 数据一致性：删除与增量

- 删除文件（`DELETE /api/files/:id`）：删 PostgreSQL 记录 → `IncrementalUpdater` 按
  `paper_id` 同时清理 parents/children 两个 collection 的向量 → 删 PDF 原件与裁图目录。
- 清空向量库（`DELETE /api/collection`）：整库 drop + 本地文件清理。
- 上传失败回滚：处理异常时删除已落盘的 PDF，不留脏文件。

---

## 9. 评测（`backend/eval/`）

- `eval_retrieval.py`：检索指标 Recall@k / Precision@k / MRR / MAP，直打完整检索管道（含重排与父块回溯）。
- `eval_generation.py`：RAGAS 指标 Faithfulness / AnswerRelevancy / ContextPrecision / FactualCorrectness，
  端到端跑 agent 收集答案与上下文出 CSV 报告。
- 自建数据集样例在 `eval/datasets/`（PredNet 论文问答对）。

---

## 10. 已知限制与改进方向（面试收尾用）

1. **子图重复编译**：`build_graph` 在每次请求时重建，子代理每次调用也重新 `compile()` 子图——
   正确但浪费，可按 (llm, retriever, max_retries) 缓存编译结果。
2. **无鉴权**：会话 ID 即访问边界；生产化需加 auth 与受限 CORS。
3. **单机部署**：Milvus standalone + 单实例 FastAPI；横向扩展时 checkpointer 与 Milvus 天然支持，应用层无状态。
4. **引用重映射基于正则**：`[n]` 编号重排依赖生成格式遵循 prompt，极端情况可能错位；
   可改为结构化输出引用块。
5. **反思关闭时缺少质量兜底**：回答充分性完全依赖检索与单轮生成质量；
   可考虑低频抽样反思（按比例触发）平衡成本与质量。

---

## 11. 关键参数速记

| 参数 | 值 | 含义 |
|---|---|---|
| `TOP_K` | 5 | 每个查询最终返回文档数 |
| `FETCH_K` | 20 | 重排前候选数（实际取 2×） |
| `RRF_K` | 60 | RRF 融合常数 |
| child 分块 | 500 字符 / 50 重叠 | 结构节点不切分 |
| 记忆窗口 | 6 轮 | 超窗 LLM 压缩为 summary |
| 语义缓存阈值 | 余弦 ≥ 0.95 | scope 隔离 + LRU 1000 |
| 裁图 DPI | 2x | PNG，按 paper_id 分目录 |
| `MAX_RETRIES` | 0（默认） | ≤0 跳过 reflect 节点；≥1 启用反思重试 |
