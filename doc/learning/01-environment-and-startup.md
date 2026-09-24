# 01. 环境、配置与启动

## 1.1 这一章要解决的问题

在看 RAG、Agent 或 React 之前，先建立一个运行时模型：哪些服务在运行、每个服务负责什么、配置从哪里读、容器之间怎样通信。很多表面上像代码错误的问题，其实是模型地址、容器网络、依赖安装或数据库还没有准备好。

本章的目标不是让你死记 Docker 命令，而是让你能回答：

> 当浏览器发出一次请求时，它经过了哪些网络地址？每一个地址为什么这样写？

## 1.2 项目需要的外部能力

| 类别 | 当前项目使用的组件 | 是否由 Compose 创建 |
|---|---|---|
| 后端 | Python 3.12、FastAPI、Uvicorn | 是，`backend` |
| 前端 | Node 构建 React，Nginx 服务静态文件 | 是，`frontend` |
| 向量数据库 | Milvus 2.5 standalone | 是，`milvus` |
| 关系数据库 | PostgreSQL 16 | 是，`postgres` |
| 文本模型 | OpenAI-compatible LLM API | 否，外部服务 |
| 视觉模型 | OpenAI-compatible VLM API，可选 | 否，外部服务 |
| Embedding/重排 | Hugging Face / sentence-transformers 模型 | 由 backend 进程加载 |

“项目 Docker 化”不表示所有模型都在 Docker 中。Compose 只明确启动了四个服务；LLM、VLM 可以是本机服务、局域网服务或云端 API。模型地址由 `.env` 提供。

## 1.3 目录和运行入口

```text
scholar-rag/
├── docker-compose.yml       四服务编排
├── Makefile                 本地常用命令
├── backend/
│   ├── Dockerfile           后端镜像构建步骤
│   ├── .env.example         配置模板
│   ├── config.py            环境变量 -> Config 类
│   └── app/main.py          FastAPI 入口
└── frontend/
    ├── Dockerfile           构建 React 后交给 Nginx
    ├── nginx.conf           SPA 与 API 反向代理
    └── vite.config.js       本地开发代理
```

从零实现时，建议先使 `backend/app/main.py` 能启动；之后才加入 Compose。Docker 是对稳定运行方式的封装，而不应替代你对单个进程的理解。

## 1.4 配置是如何进入程序的

`backend/config.py` 的第一行 `load_dotenv()` 会读取 backend 工作目录中的 `.env`。然后 `Config` 类在模块导入时读取环境变量：

```python
class Config:
    TOP_K = int(os.getenv("TOP_K", "5"))
    ENABLE_CACHE = os.getenv("ENABLE_CACHE", "true").lower() == "true"
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
```

这意味着：

- `.env` 是给人编辑的配置文件；`Config` 是给 Python 代码使用的统一入口。
- 变量没有配置时，程序会使用 `os.getenv` 的默认值。
- Compose 的 `environment` 会覆盖 `env_file` 中同名变量。当前 `MILVUS_URI` 和 `POSTGRES_URI` 正是这样被改成容器内服务地址的。
- 密钥不应该写入源码或提交到 Git；`.gitignore` 已忽略 `.env`。

### 重要配置组

| 变量 | 用途 | 学习时应关注的影响 |
|---|---|---|
| `MILVUS_URI` | 连接 Milvus | 本机运行与容器运行的地址不同 |
| `COLLECTION_NAME` | collection 前缀 | 实际会生成 `_parents`、`_children` 两套集合 |
| `EMBEDDING_MODEL` | 检索向量模型 | 影响语义召回质量与首次加载耗时 |
| `RERANKER_MODEL` | CrossEncoder 模型 | 影响候选重排质量与查询延迟 |
| `FETCH_K` | 重排前候选数 | 大一些通常提高召回，但更慢 |
| `TOP_K` | 最终给 LLM 的文档数 | 大一些上下文更全，但 token 更多 |
| `RRF_K` | RRF 融合常数 | 控制 Dense 与 BM25 排名融合的平滑度 |
| `LLM_*` | 文本模型端点和参数 | 用于分类、分解、生成、总结、反思 |
| `MAX_RETRIES` | 子 Agent 是否反思重试 | `<= 0` 时反思节点根本不会编译 |
| `VLM_*` | 图像模型端点 | 当前未完成主聊天链路注入，见第 07 章 |

## 1.5 本机地址、Docker 地址和云端地址

这是最容易混淆的部分。

### backend 在 Docker，Milvus/PostgreSQL 也在 Compose

backend 容器中应使用 Compose 服务名：

```env
MILVUS_URI=http://milvus:19530
POSTGRES_URI=postgresql://postgres:postgres@postgres:5432/scholar_rag
```

这里的 `milvus`、`postgres` 不是 DNS 公网域名，而是 Docker Compose 默认网络中的服务名。

### backend 在 Docker，模型在 Windows 宿主机

容器无法用 `localhost` 指向 Windows 宿主机，因为容器内的 `localhost` 是它自己。Docker Desktop 提供：

```env
LLM_BASE_URL=http://host.docker.internal:8001/v1
VLM_BASE_URL=http://host.docker.internal:8080/v1
```

`host.docker.internal` 的意思只是“容器访问宿主机”。它不会启动模型，也不意味着模型本身是 Docker 容器。

### backend 在 Docker，模型是云端 API

直接填供应商的 OpenAI-compatible 地址：

```env
LLM_BASE_URL=https://example-provider.com/v1
LLM_MODEL=provider-text-model
LLM_API_KEY=真实密钥

VLM_BASE_URL=https://example-provider.com/v1
VLM_MODEL=provider-vision-model
VLM_API_KEY=真实密钥
```

关键要求是 API 接受该项目通过 `langchain_openai.ChatOpenAI` 发送的 OpenAI 风格聊天请求；VLM 还要支持 `image_url` 类型的多模态消息。

### backend 在本机运行，基础设施在 Docker

本机 Python 进程使用端口映射：

```env
MILVUS_URI=http://localhost:19530
POSTGRES_URI=postgresql://postgres:postgres@localhost:5432/scholar_rag
```

不能写 `http://milvus:19530`，因为这个名字只在 Compose 网络内可解析。

## 1.6 Compose 的服务依赖关系

`docker-compose.yml` 描述的启动逻辑如下：

```text
milvus -------------------------┐
  healthz: :9091/healthz        │
                                ▼
postgres ------------------> backend ------------------> frontend
  health: pg_isready          :8000                     :80 -> host :5173
```

细节：

1. Milvus 使用 named volume `milvus_data`，所以容器重建后索引数据仍可保留。
2. PostgreSQL 使用 named volume `postgres_data`，所以会话和 checkpoint 也能保留。
3. backend 将 `backend/uploads` 和 `backend/data` 绑定挂载到容器 `/app/uploads`、`/app/data`，上传 PDF 和裁出的图片会出现在工作区。
4. frontend 不是 React 开发服务器；其 Dockerfile 先构建静态文件，再由 Nginx 服务。开发时使用 Vite 则是另一条路径。

## 1.7 backend 启动时的真实顺序

源码入口：`backend/app/main.py` 和 `backend/app/dependencies.py`。

```text
导入 app.main
  -> 创建 FastAPI(title="Scholar RAG", lifespan=lifespan)
  -> 注册 CORS 和四组 router
  -> 进入 lifespan()
      -> _ensure_postgres_db(): 尝试创建目标数据库
      -> AsyncConnectionPool.open()
      -> init_store(): 创建 sessions/files 表
      -> 创建 ChatOpenAI 文本模型客户端
      -> 创建 Retriever
          -> 加载 EmbeddingService
          -> 加载 RerankerService
          -> 构造 parents / children 的 Milvus store
      -> 创建 PDFParser 和 RAGIntegration
      -> 创建 AsyncPostgresSaver 并执行 setup()
      -> 输出 "Startup complete."
  -> 开始接收 HTTP 请求
```

`ChatOpenAI` 在这里是客户端包装器，不会自动下载大语言模型。它保存 base URL、模型名、API key、温度、超时和重试策略，真正的模型服务仍在外部。

## 1.8 frontend 的两种运行模式

### 开发模式

执行 `npm run dev`。`frontend/vite.config.js` 将 `/api` 代理到 `http://localhost:8000`，浏览器访问 Vite 的开发端口。

```text
浏览器 -> Vite dev server -> localhost:8000/api
```

### Docker / 生产模式

Nginx 的 `location /api/` 将请求代理到 `http://backend:8000`，并关闭 proxy buffering，这对 SSE 流式输出很关键。

```text
浏览器 -> localhost:5173 -> Nginx frontend -> backend:8000
```

因此前端代码统一写相对路径 `/api/...`，不需要硬编码不同环境中的后端域名。

## 1.9 推荐的启动验证顺序

先检查最便宜的东西，再检查最昂贵的东西：

```powershell
# 1. 查看 Compose 最终配置，不启动任何服务
docker compose config

# 2. 构建并启动
docker compose up -d --build

# 3. 看容器状态
docker compose ps

# 4. 看 backend 最近日志
docker compose logs backend --tail=100

# 5. 请求健康检查
curl http://localhost:8000/api/health
```

`/api/health` 会分别测试 Milvus 和文本 LLM。若 `llm: false`，先检查模型 URL、密钥、模型名和容器是否能访问外网/宿主机；不要先怀疑 React。

## 1.10 容易踩的坑

| 现象 | 常见原因 | 优先操作 |
|---|---|---|
| backend 退出或重启 | 依赖、数据库、模型初始化失败 | `docker compose logs backend -f` |
| backend 连接不到 Milvus | 在本机/容器间写错地址 | 确认使用 `localhost` 还是 `milvus` |
| `host.docker.internal` 不通 | 宿主机无服务、端口不监听、不是 Docker Desktop 预期环境 | 在宿主机先访问目标 API，再查看容器网络 |
| 页面能打开但 API 404/502 | backend 未启动或 Nginx 代理错误 | 检查 `frontend/nginx.conf`、backend 日志 |
| LLM 健康检查失败 | API 格式、模型名或认证不兼容 | 用独立 curl/SDK 验证 `/v1` 服务 |
| 上传后长时间无响应 | Docling、Embedding、Milvus 或模型首次加载 | 观察 backend 日志中的具体阶段 |

## 1.11 本章练习

1. 分别画出“全 Compose”和“backend 本机 + 数据库容器”的网络图，标出每一条 URL。
2. 找到 Compose 中覆盖 `.env` 的两个变量，解释为什么必须覆盖。
3. 把 `TOP_K` 改成 2 和 10，预测它会对速度、上下文长度和引用数量产生什么影响；先写预测，再做实验。
4. 打开 `backend/app/dependencies.py`，按启动顺序给每个共享对象写一句职责说明。

## 下一章

下一章从 backend 内部开始：FastAPI 如何注册路由、PostgreSQL 到底保存哪些信息，以及聊天请求怎样进入 LangGraph。
