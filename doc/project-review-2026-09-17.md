# ScholarRAG 项目问题清单

审查时间：2026-09-17
审查范围：仓库结构、`backend/`、`frontend/`、配置与文档一致性、git 工作区状态
审查基线：工作区 `main` @ `3dfc5dc`（含未提交改动）
说明：本次**只做只读审查，未修改任何代码**。

---

## 一、结论摘要

项目整体健康。模块切分清晰（`models → integration → retrieval → agent → routers`），
依赖注入和单例装配（`app/dependencies.py` 的 `lifespan`）设计合理，节点函数是纯函数便于测试，
README 详实度高于多数同类项目。

主要风险**不在代码质量，而在工程卫生**：

1. 一整套完整功能长期未提交，悬在工作区（最高优先级）
2. 一个配置项把宣传的核心能力静默关掉了
3. 文档与实际实现存在 4 处偏差
4. 仓库根目录混入临时/无关文件
5. 本地 Python 版本与项目要求不匹配
6. `agent/tools.py` 整体已沦为死代码（仅无功能影响，但误导性强）

安全方面：**API 密钥未泄漏到 git 历史**（详见 §5），无需改写历史。

---

## 二、P0 — 未提交的功能链（风险最高）

`git status` 显示 **17 个文件已修改**（+184 / −48），构成一条完整的「按论文限定检索」特性：

### 改动清单

| 层 | 文件 | 改动内容 |
|---|---|---|
| 前端 UI | `frontend/src/App.jsx` | 顶栏新增论文作用域 `<select>`；新增 `files` / `paperId` 状态；`handleFilesChanged` 同时刷新文件与会话 |
| 前端 API | `frontend/src/api.js` | `streamChat()` 增加 `paperId` 参数，body 带 `paper_id` |
| 前端面板 | `frontend/src/components/SettingsPanel.jsx` | 回调由 `onCollectionCleared` 改为 `onFilesChanged` |
| 接口层 | `backend/app/routers/chat.py` | `ChatRequest.paper_id`；透传进 `_stream_response` 与 `graph_input` |
| 依赖层 | `backend/app/dependencies.py` | `RetrieverTool.invoke()` 增加 `paper_id` 形参并下传 |
| 图编排 | `backend/agent/graph.py` | `Send` 与 `sub_agent_node` 传递 `paper_id` |
| 状态定义 | `backend/agent/states.py` | `AgentState` / `SubAgentState` 增加 `paper_id` |
| 节点 | `backend/agent/nodes.py` | `retrieve()` 读取 `paper_id`，两条 `retriever.invoke` 路径都传入 |
| 检索 | `backend/rag/retrieval.py` | `_build_expr()` 拼接并转义 `paper_id == "..."`；缓存 scope 加入 `paper_id` |
| 缓存 | `backend/rag/cache.py` | 键改为 `(query, scope)`；新增 `threading.RLock`；`get/put/clear` 加锁 |
| 工厂 | `backend/rag/factory.py` | 新增 `MilvusStoreFactory._register_orm_connection()`，桥接 `MilvusClient` handler 到 PyMilvus ORM 注册表 |
| 依赖声明 | `backend/requirements.txt` | 补 `aiofiles>=24.1.0` |
| 部署 | `docker-compose.yml` | `milvusdb/milvus` v2.4.0 → **v2.5.0** |
| 部署 | `backend/Dockerfile` | apt/pip 换阿里云源；补 `libglib2.0-0`/`libgl1`/`libsm6` 等 Docling 运行库；预装 CPU 版 torch |
| 部署 | `frontend/Dockerfile` | npm 换 `registry.npmmirror.com` |
| 部署 | `frontend/nginx.conf` | `client_max_body_size 100m`；proxy 超时 600s |

### 配套新文件（未跟踪）

- `backend/test/test_paper_filter.py` — 覆盖缓存跨论文不串号、过滤器拼接与引号转义
- `backend/test/test_pdf_parsing.py` — PDF 解析检查脚本（可 `--output` 导出 JSON 报告）
- `backend/eval/datasets/prednet_eval.jsonl` + `prednet_eval_summary.md` — 评测数据集与摘要

### 为什么是 P0

- **完整性已验证**：这条链从 UI 一路串到 Milvus 过滤表达式，中间没有断点
- **风险集中**：17 个文件跨前后端与部署配置，一旦被别的工作覆盖或误 `checkout` 就丢失
- **耦合隐患**：`factory.py` 的 ORM 桥接依赖 `MilvusClient._using`、`connections._alias_handlers`
  等**私有属性**，且与 Milvus 2.5 强绑定——这类改动最难重建，最值得先固化

### 建议

按逻辑拆成 3~4 个 commit，而不是一次性 `git add -A`：

```
feat: scope retrieval to a single paper (paper_id filter + UI selector)
fix: isolate retrieval cache by paper/filter scope, add lock
fix: bridge MilvusClient handler for PyMilvus ORM collection lookup
chore(deploy): bump Milvus to 2.5.0, add mirrors and nginx timeouts
```

提交前先 `git add` 需要的文件，**显式排除** §4 列出的临时文件。

---

## 三、P1 — 配置把核心能力静默关闭

### 3.1 `MAX_RETRIES=0` 导致反思重试永不触发

位置：`backend/.env:27`

调用链：

```
chat.py:34        build_graph(max_retries=Config.MAX_RETRIES)   # = 0
graph.py:54       should_retry(state, max_retries=0)
nodes.py:367      if not is_sufficient and retries(0) < max_retries(0):   # 恒为假
```

后果：

- `reflect` 节点**仍然每次调用 LLM 做充分性判断**（`graph.py:63` 的边是固定的），
  但 `is_sufficient` / `retry_queries` 对流程不再有任何影响 → **纯消耗 token，无收益**
- 每次问答都会多一次 `with_structured_output(ReflectionResult)` 的 LLM 往返
- README:98「Sub-agents self-evaluate sufficiency, retry with refined queries」与
  README:360「retries, up to `MAX_RETRIES` (default 2)」**描述的重试能力实际不生效**

**已核实、不受影响的部分**：VLM fallback **仍然有效**。它的实现位于 `reflect()` 内部
（`nodes.py:319-355`），条件是 `not is_sufficient and vision_service and not needs_vlm`，
与 `max_retries` 无关——`should_retry` 只在 reflect 返回**之后**做路由判断。
所以 `MAX_RETRIES=0` 关掉的是**补充查询重试**，不是 VLM 兜底。

### 决定项（二选一）

- **有意关闭**（省成本）→ 建议让图跳过 `reflect` 节点，省掉无用的 LLM 调用，
  同时修正 README 描述
- **想保留能力** → `.env` 设回 `MAX_RETRIES=2`

> 注：`config.py:30` 的默认值是 `2`，是 `.env` 覆盖成了 `0`。
> 所以直接删掉 `.env` 里这一行也会回到 2。

---

## 四、P1 — 文档与实现偏差

| # | 位置 | 文档写的 | 实际是 |
|---|---|---|---|
| 1 | `README.md:123` | `store.py` 用 **SQLite**，零配置文件数据库 | 已是 **PostgreSQL**（`app/store.py` 用 `psycopg_pool.AsyncConnectionPool`，`dependencies.py:100` 调 `init_store(pool)`） |
| 2 | `README.md:372` | Milvus `milvusdb/milvus:v2.4.0` | `docker-compose.yml:36` 是 **v2.5.0**（且 2.5 是 BM25 built-in function 的前提） |
| 3 | `README.md:236` | 重排器 `BAAI/bge-reranker-v2-m3` | `backend/.env:8` 实为 `cross-encoder/ms-marco-MiniLM-L6-v2` |
| 4 | `README.md` 全文 | 未提及按论文限定检索 | 代码已实现（未提交），含 UI 下拉框 |

另：`README.md:30` 的视频链接指向 `github.com/user-attachments/...`，非项目自有资源，
建议换成仓库内已有的 `resource/ScholarRAG.mp4`。

### 过时的模块注释

- `README.md:123` 的 SQLite 描述属于**历史遗留**（早期版本注释），应改为 PostgreSQL

### P3 — 一次多余的会话刷新

`FileUpload` 上传成功后触发 `handleFilesChanged`，它同时调用 `loadFiles()` 与 `loadSessions()`
（`frontend/src/App.jsx`）。从后端实现看上传接口**不创建或变更会话**，所以
`loadSessions()` 这一次是冗余刷新。

你的学习笔记（`doc/learning-progress-2026-08-17.md:182`）已经独立发现了这一点，**判断是对的**。
因为操作是幂等的，影响仅为多一次无效 HTTP 请求，优先级最低。

---

## 五、P2 — 安全与密钥（已核实，风险可控）

### 结论：密钥未泄漏

核查过程与证据：

```
git ls-files --error-unmatch backend/.env
  → error: pathspec did not match        # 当前未被跟踪

git cat-file -e HEAD:backend/.env
  → fatal: exists on disk, but not in HEAD   # HEAD 树中不存在

git ls-tree -r 4abc7e9 -- backend/.env
  → 100644 blob e69de29bb2d1d6434b8b29ae775ad8c2e48c5391   # 空文件（0 字节）

git ls-files | Select-String '\.env'
  → backend/.env.example                 # 只有模板被跟踪
```

`git log --all -- backend/.env` 会列出 `91a6a10`、`4abc7e9`，但这**只是路径历史上出现过**；
其中 `91a6a10` 实际不含该文件，`4abc7e9`（已推到 `origin/main`）含的是一份**空 `.env`**。

因此：`backend/.env:24` 的真实 key（`sk-fcc2481...`）**仅存在于本地磁盘，从未提交、从未推送**。
仓库历史无需清洗。

### 残留建议

1. **不要 `git add -f backend/.env`** —— `.gitignore:25` 已覆盖，保持现状即可
2. 该 key 已在本轮对话文本中出现，**建议轮换一次**（低成本保险）
3. `.env` 中 `POSTGRES_URI` 用的是默认 `postgres:postgres`，
   `docker-compose.yml:58` 同样是弱口令 —— 仅限本地/内网，勿直接暴露公网
   （README:539 的 Security Notice 已说明这一点）

---

## 六、P2 — 仓库卫生

### 未跟踪且**未被 ignore**、随时可能被误提交

| 路径 | 性质 | 建议 |
|---|---|---|
| `backend/1.py` | Docling 试验脚本，`1.py:6` 硬编码 `G:\scholar-rag\...` 绝对路径，产物写到仓库根目录 | 移入 `tmp/` 或删除 |
| `backend/2.py` | `PDFParser` 试验脚本，路径 `backend/uploads/...` 依赖启动目录 | 移入 `tmp/` 或删除 |
| `paper.docling.md` | 由 `1.py:18` 写出的 60KB 中间产物，位于**仓库根目录** | 删除并 ignore |
| `tmp/badminton_frames/**` | 21 张羽毛球视频帧 + montage/seg/seq，与本项目**完全无关** | 删除或 `tmp/` 整体 ignore |
| `backend/1543_Neural_Prediction_Errors_.pdf` | 测试 PDF，`backend/uploads/` 下已有同一份副本 | 删除（`*.pdf` 已在 `.gitignore:18`，但此文件未被跟踪状态易混淆） |

> `doc/learning-progress-2026-08-17.md` 是你的学习笔记，**建议保留提交**，
> 这类文档对项目是有价值的。

### 建议补充的 `.gitignore` 规则

```gitignore
tmp/
paper.docling.md
```

### 其他观察

- `backend/.agents/` 为空目录（glob 未显示任何内容），无实际作用
- `backend/data/figures/` 下有 5 个论文目录共 15 张图，其中 `王一博简历`、`丁柯军的简历`、
  `基于视觉匹配与拓扑结构推理的立方体展开图选择方法` 属于简历/中文论文测试数据，
  与学术论文主线场景不同——若为临时验证，可清理（`data/` 已在 `.gitignore:34`）
- 仓库根目录 `data/figures/demo-paper/` 是 `backend/2.py` 以 `paper_id="demo-paper"`
  跑出来的产物，与 `backend/data/figures/` 并存，位置不统一

---

## 六点五、P2 — 死代码与重复定义

### 6.5.1 `agent/tools.py` 整体已是死代码

核查引用关系：

```
grep -E "paper_retrieval|set_query_type|_query_type_ctx" backend/**/*.py
  tools.py:17   _query_type_ctx: ContextVar[str] = ContextVar("query_type", default="general")
  tools.py:40   def set_query_type(query_type: str)
  tools.py:45   @tool def paper_retrieval(query: str)
  nodes.py:87   from .tools import set_query_type
  nodes.py:102  set_query_type(query_type)
```

- `paper_retrieval`（`tools.py:44-76`）**从未被任何地方调用**
- 因此 `_query_type_ctx`（`tools.py:17`）**从未被读取**——`set_query_type()` 是只写不读的写入
- `nodes.py:87,102` 的唯一作用是给这个死变量赋值，属于纯粹的无用执行

历史原因推测：早期用 LangChain tool-calling 让 LLM 自行决定检索，后来改成了
`Send` 显式分发 + `retrieve()` 节点直连 retriever，但 `tools.py` 没跟着删。

**影响**：无功能影响，但 `README.md:136` 仍把它描述为
「Tool definitions: paper_retrieval (retrieval tool with query_type routing), ContextVar context variables」，
会误导读者以为检索靠 tool calling 驱动。

**注意**：若未来想恢复 tool-calling 路线，需先确认 ContextVar 能否跨
`Send` 分发的子任务传播——`set_query_type()` 在顶层 `classify` 节点（`graph.py:108`）执行，
而读取发生在子图节点中，二者的 context 是复制关系而非共享关系，**很可能是失效的**。
即当前设计下 ContextVar 路线本身就不成立，这也是改直连的合理动机。

### 6.5.2 `_ROUTE_CONFIG` 被重复定义

同一份映射表存在两份副本：

- `backend/agent/tools.py:19-24`（死代码中）
- `backend/agent/nodes.py:198-203`（实际生效的这份）

`nodes.py` 里这份还是**函数内局部变量**，每次 `retrieve()` 调用都重新构造一次字典。
建议提取为模块级常量，两处统一引用（或直接删掉 `tools.py` 那份）。

---

## 七、P2 — 本地环境版本不匹配

实测本机：

```
Python 3.14.7      # 项目要求 Python 3.12（backend/Dockerfile:1 用 python:3.12-slim）
Node   v24.21.0    # 项目要求 Node 18（frontend/Dockerfile:3 用 node:18-alpine）
```

`docling` / `pymilvus` / `sentence-transformers` / `torch` 这类含原生扩展的包，
在 Python 3.14 上很可能缺少预编译 wheel，`pip install -r backend/requirements.txt` 会尝试源码编译或直接失败。
README:218 写的是「Python 3.12+」，但实际**建议锁 3.12**。

**建议**：本地用 `py -3.12 -m venv .venv` 建独立环境，不要用系统 3.14。
（Node 24 跑 Vite 5 通常没问题，优先级低。）

---

## 八、建议执行顺序

| 顺序 | 事项 | 章节 | 理由 |
|---|---|---|---|
| 1 | 提交 paper scope 功能链（拆分 commit，排除临时文件） | §2 | 悬空改动风险最高，且含难以重建的 Milvus 私有 API 桥接 |
| 2 | 决定 `MAX_RETRIES` 语义（改配置或改图），并同步 README | §3 | 影响功能真实性，改动很小 |
| 3 | 修正 README 4 处偏差 | §4 | 纯文档，低风险 |
| 4 | 清理临时文件 + 补 `.gitignore` | §6 | 防止后续误提交 |
| 5 | 建 Python 3.12 虚拟环境 | §7 | 否则本地可能根本跑不起来 |
| 6 | 清理 `tools.py` 死代码、合并 `_ROUTE_CONFIG` | §6.5 | 纯清理，但需先确认没有外部引用 |
| 7 | 轮换 LLM API key（可选保险） | §5 | 历史已确认干净，非必须 |

---

## 九、未检查项（诚实声明）

本次审查**未执行**以下内容，故不对其作任何结论：

- **未运行任何测试**（`make test` / `pytest`）—— 环境版本不匹配，且未安装依赖
- **未启动服务**，未验证前后端实际联通、SSE 流式输出、Milvus 检索效果
- **未审计** `rag/integration.py`（619 行，项目最大文件）的内部逻辑正确性
- **未逐行通读** `agent/nodes.py`（376 行）—— 已读第 1-234 行与第 300-376 行，
  第 235-299 行（generate 节点主体）仅粗略浏览
- **未评估** 检索质量 / RAGAS 指标 —— `backend/eval/` 下的评测脚本未运行
- **未做**前端 lint（`npm run lint`）

如需覆盖以上任一项，请单独提出。
