# 07. 部署、评测与改进

## 7.1 为什么部署和评测放在最后

先能解释一条本地请求，再谈容器编排和指标。否则遇到“回答不对”时，你不知道是容器地址、PDF 解析、Milvus 写入、检索召回、Prompt，还是模型本身出了问题。本章把这些问题拆成可验证的层级。

## 7.2 Docker 镜像怎样构建

### backend 镜像

`backend/Dockerfile` 的顺序是：

- `python:3.12-slim` 作为基础镜像；
- 安装 Docling/PyMuPDF 所需系统库；
- 安装 CPU 版 torch 和 `requirements.txt`；
- 复制 backend 源码、创建 uploads、暴露 8000；
- 启动 `uvicorn app.main:app`。

使用 Python 3.12 是现实约束：Docling、PyTorch、PyMilvus 等含原生扩展的依赖不一定及时支持最新 Python。学习时尽量使用 Dockerfile 声明的版本。

### frontend 镜像

frontend 是多阶段构建：

- `node:18-alpine` 阶段执行 `npm ci` 和 `npm run build`；
- `nginx:alpine` 阶段只复制 `dist` 和 `nginx.conf`。

最终 frontend 容器不带 Node，也不运行 Vite，只提供静态资源和反向代理。

## 7.3 Compose 的服务和持久化边界

| 资源 | 挂载方式 | 内容 |
|---|---|---|
| `milvus_data` | named volume | Milvus collection、索引和元数据 |
| `postgres_data` | named volume | PostgreSQL 数据 |
| `./backend/uploads` | bind mount | 上传的原始 PDF |
| `./backend/data` | bind mount | 裁出的 figure 图片等运行数据 |

`docker compose down` 会停止并删除容器，但保留 named volumes。`docker compose down -v` 会删除卷，丢失 Milvus 和 PostgreSQL 持久化数据；它不是普通的重启命令。

## 7.4 从健康检查到端到端检查

建议按四层检查：

### 层 1：进程和网络

先执行 `docker compose config` 检查配置，再执行 `docker compose up -d --build`。随后用 `docker compose ps` 查看状态，用 `docker compose logs backend --tail=100` 查看后端启动日志，最后请求 `http://localhost:8000/api/health`。

### 层 2：数据摄取

上传一份小 PDF，确认 API 返回 `status=ok`；`backend/uploads/` 有 UUID 命名的原文件；若论文有图，`backend/data/figures/` 出现裁图；`/api/files` 能看到页数和 chunk 数；Milvus 出现 parents/children collection。

### 层 3：检索

用固定问题直接调用 `Retriever.retrieve()` 或运行检索脚本，打印 `chunk_id`、`node_type`、`page_num`、`section_path` 和文本预览。不要先看最终答案：若这里没有正确证据，Agent 再强也不能可靠回答。

### 层 4：生成与前端

通过 `/api/chat` 或浏览器确认事件顺序：`session_id -> status -> sub_queries -> answer* -> citations -> done`。

## 7.5 测试代码怎样分类

当前 `backend/test/` 混合了单元逻辑、手工脚本和依赖外部服务的测试。可以按三类理解。

### 纯逻辑测试

`test_paper_filter.py` 不需要真实 PDF：它检查不同 `paper_id` 的缓存不会串结果，也检查 paper、node type、section type 条件能正确组合并转义。这类测试最适合先写，因为反馈快、失败原因明确。

### 本地资源/模型测试

`test_pdf_parser.py`、`test_pdf_parsing.py` 需要 PDF 和 Docling；`test_retrieval.py` 需要 Milvus、Embedding、Reranker 和测试论文。它们更像诊断脚本，不能在缺少资源时简单解释为业务代码错误。

### Agent/VLM 集成测试

`test_agent.py`、`test_vlm.py` 需要模型端点；`test_vlm_integration.py` 还引用了项目中当前不存在的 `rag.vision` 模块，不能直接视为稳定可运行的测试。测试文件存在不等于测试已经通过。

## 7.6 Makefile 提供的学习入口

`Makefile` 提供 `install`、`backend`、`frontend`、`dev`、`build`、`docker-up`、`docker-down`、`lint` 和 `test`。Windows 环境没有 GNU Make 时，可以把目标里的命令拆开运行；不要为了执行一个目标而忽略它实际做了什么。

## 7.7 检索评测：衡量“找得对不对”

`backend/eval/eval_retrieval.py` 支持三种测试样例：

1. `relevant_ids`：答案相关 chunk 的 ID；
2. `reference_answer`：让评估 LLM 判断 chunk 是否包含回答所需信息；
3. `relevant_pages` / `relevant_layouts`：按页面或布局命中，适合 MMDocIR 适配。

主要指标：

| 指标 | 含义 |
|---|---|
| Recall@k | 所有相关证据中，有多少进入前 k 个 |
| Precision@k | 前 k 个里有多少是相关的 |
| MRR | 第一个相关结果出现得有多靠前 |
| MAP | 多个相关结果的整体排序质量 |

调参数时不要只看一个指标：Recall 高但 Precision 低，表示召回广但噪声多；Precision 高但 Recall 低，表示结果准但漏证据；MRR 低则说明相关证据排序靠后。

## 7.8 生成评测：衡量“答得好不好”

`backend/eval/eval_generation.py` 使用 RAGAS，将一次 Agent 运行收集为 `SingleTurnSample`，包括 `user_input`、`response`、`retrieved_contexts` 和可选 `reference`。

当前默认指标包含：

- `Faithfulness`：回答是否被检索上下文支持；
- `AnswerRelevancy`：是否回答了问题；
- `FactualCorrectness`：有 reference 时，事实是否正确。

评测本身也依赖 LLM 和 Embedding，因此不是完全脱离模型的数学真值。应结合人工抽样查看具体回答和证据。

还有一个当前代码层面的限制需要注意：`collect_samples()` 试图从每个 `sub_answer` 的 `documents` 字段收集 `retrieved_contexts`，但 `_collect_sub_answer()` 目前只保存 `query`、`answer`、`citations`。因此生成评测通常拿不到真实检索上下文，最终会退回到空字符串列表。若要让 Faithfulness 等指标可信，需要把 documents 或独立的检索证据字段纳入子答案/评测结果，而不是只保存展示用 citation。

## 7.9 VLM：配置、服务和接线是三件事

一份 VLM 配置可能是：

```env
VLM_ENABLED=false
VLM_BASE_URL=https://provider.example/v1
VLM_MODEL=vision-model
VLM_API_KEY=...
```

必须区分：

1. **有配置**：字符串存在于 `.env`；
2. **有服务**：URL 确实运行，支持图片+文字请求，并接受模型名与密钥；
3. **已接线**：应用启动创建 VLM `ChatOpenAI`，构造 `VisionService`，传给 `build_graph()`，且证据对象保留 `image_path`。

当前项目有 `VisionService` 和视觉查询判断函数，但 `dependencies.py` 没有创建它，`chat.py:_build_graph()` 也没有传入 `vision_service`。另外 `CitationExtractor` 返回的是简化 citation，VLM 代码却从 citation 中读取 `metadata.image_path`，数据字段也没有完整贯通。因此把 `VLM_ENABLED` 改成 `true` 不会自动让聊天具备视觉理解。

如果使用云端 VLM，backend 容器直接访问云端 HTTPS API，不需要本机下载模型，也不需要使用 `host.docker.internal`。后者只适用于模型运行在宿主机的情况。

## 7.10 生产化风险清单

### 安全

- 当前没有认证/授权，session ID 不是可靠的用户隔离边界；
- CORS 全开放；
- `DELETE /api/collection` 无权限保护，可清空全库；
- `.env` 密钥不能提交，默认 PostgreSQL 密码应替换；
- 上传只有扩展名和大小检查，生产环境还应检查 MIME、内容、恶意文件和资源消耗。

### 可靠性

- 每次请求重建 graph、每个子 Agent 重新 compile 子图，存在额外开销；
- PDF 入库跨文件系统、Milvus 和 PostgreSQL，缺少完整事务/补偿机制；
- 云端模型、Milvus、PostgreSQL 失败时需要更细的错误分类与重试；
- 当前 VLM 证据路径不完整，不能只看开关判断是否可用。

### 可维护性

- `agent/tools.py` 的 `paper_retrieval` 与 ContextVar 目前不是主图路径，容易误导读者；
- `CACHE_MAX_SIZE` 没有传入 `RetrievalCache` 构造函数；
- `uploadFiles` 的 `onProgress` 参数暂未实现；
- 测试脚本和 pytest 测试混在一起，建议区分单元、集成和诊断脚本。

## 7.11 推荐改进顺序

1. 固定依赖版本和可复现启动方式；
2. 补充纯逻辑单元测试；
3. 为摄取、检索、Agent 建立小型 fixture；
4. 修正 VLM 端到端接线和证据字段；
5. 缓存已编译的 graph/subgraph；
6. 增加统一 API 错误、超时和日志；
7. 加认证、受限 CORS 和删除权限；
8. 最后做多实例部署和成本优化。

## 7.12 本章练习

1. 写一份“空 Milvus -> 上传 -> 检索 -> 聊天”的验收清单，每步只有一个可观察结果。
2. 设计一个 10 条问答的检索评测集，给每条问题标注 relevant page 或 chunk。
3. 用一个 OpenAI-compatible 多模态 API 画出 VLM 从图片路径到 `VisionService.analyze_figure()` 的连接图。
4. 为 `DELETE /api/collection` 设计最小认证方案，并说明前端确认框为什么不等于后端权限控制。
