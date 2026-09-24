# RAG 学习文档

这是一份伴随代码实践持续维护的学习笔记。每次遇到重要概念，先用自己的话记录，再回到项目源码中确认它的实际用法。

## 1. 学习代码与原项目

- `backend/` 和 `frontend/` 是原项目的完整实现，主要用来阅读和对照。
- `learning-implementation/` 是从小到大亲手编写的练习项目。
- `main` 和 `codex/learning-from-zero` 是不同的 Git 分支。分支隔离提交历史；目录是否显示某个文件，取决于当前分支的提交快照。
- 练习代码提交到 `codex/learning-from-zero`，不会自动出现在 `main`。
- 普通分支切换使用同一个工作目录；`git worktree` 才会为另一个分支创建额外的实际工作目录。

## 2. Docker、容器与 Docker Compose

### 2.1 Docker 容器是什么

Docker 容器是一个相对独立的运行环境。应用程序、依赖和启动命令可以放在容器中运行，避免因为本机环境不同而出现“在我的电脑上可以运行”的问题。

这个项目需要多个程序共同工作：后端、前端、向量数据库和关系数据库。它们可以分别运行在不同的容器中。

### 2.2 Compose 是什么

Docker Compose 不是后端程序，也不是数据库。它是一个根据配置文件统一管理多个容器的工具。

```text
docker-compose.yml = 多容器配置表
docker compose up   = 按配置创建并启动
docker compose down = 停止并移除本次创建的容器
```

Compose 配置可以描述：

- 每个服务使用什么镜像，或者从哪个目录构建镜像；
- 服务需要暴露哪些端口；
- 服务之间如何连接；
- 环境变量、数据卷和启动依赖；
- 健康检查和重启策略。

## 3. 当前项目由哪些服务组成

根目录的 `docker-compose.yml` 在 `services:` 下定义了四个服务：

| 服务 | 作用 | 容器内程序 | 宿主机端口 |
|---|---|---|---|
| `backend` | 提供 FastAPI API、上传、检索和问答逻辑 | 项目自己的后端镜像 | `8000` |
| `frontend` | 提供浏览器页面 | 项目自己的前端镜像和 Nginx | `5173` |
| `milvus` | 保存和检索向量 | Milvus standalone | `19530`、`9091` |
| `postgres` | 保存结构化数据和会话数据 | PostgreSQL 16 | `5432` |

运行以下命令时，Compose 会按配置管理这四个服务：

```powershell
docker compose up
```

后台运行可以使用：

```powershell
docker compose up -d
```

查看状态和日志：

```powershell
docker compose ps
docker compose logs backend
docker compose logs -f
```

停止服务：

```powershell
docker compose down
```

## 4. 服务之间如何连接

Compose 会为同一个项目的服务建立内部网络。容器之间连接时，通常使用 Compose 中的服务名，而不是 `localhost`：

```text
backend -> http://milvus:19530
backend -> postgresql://postgres:postgres@postgres:5432/scholar_rag
```

这里的 `milvus` 和 `postgres` 是服务名，Docker 内部会把它们解析到对应容器。

`localhost` 的含义取决于执行请求的位置：

- 在 backend 容器中，`localhost` 指 backend 容器自己；
- 在宿主机中，`localhost:5432` 指宿主机映射出来的 PostgreSQL 端口；
- 在浏览器中，`localhost:5173` 指运行浏览器的电脑。

后端配置中有两类设置：

- `env_file: ./backend/.env` 读取后端环境变量；
- `environment:` 可以直接覆盖同名变量。

当前 Compose 文件明确把 `MILVUS_URI` 和 `POSTGRES_URI` 设置成容器内部地址，所以后端容器会连接 Compose 中的 Milvus 和 PostgreSQL。

`depends_on` 表示启动顺序和依赖关系。backend 依赖 Milvus 与 PostgreSQL 的健康检查通过后再启动；frontend 依赖 backend。

## 5. 数据库是在本地还是云端

当前项目的默认 Compose 配置使用的是本地 Docker 容器，不是云端数据库：

- `milvus` 使用 `milvusdb/milvus:v2.5.0` 镜像；
- `postgres` 使用 `postgres:16-alpine` 镜像；
- `milvus_data` 和 `postgres_data` 是 Docker volumes，用于在容器重建后保留数据。

因此，“backend、Milvus、PostgreSQL 都在 Compose 中”表示它们都由本机 Docker 环境运行和管理。

云端数据库是另一种部署方式。云厂商提供数据库服务和连接地址，backend 只需要通过连接 URI 和凭据访问它。这时通常要：

1. 修改 `MILVUS_URI` 和 `POSTGRES_URI`；
2. 配置云端账号、密码、证书和网络白名单；
3. 不再启动本地的 `milvus`、`postgres` 服务，或者为本地和云端分别维护 Compose 配置。

数据库也不一定通过 HTTP API 调用。PostgreSQL 通常使用数据库协议，Milvus 使用自己的客户端协议；连接 URI 决定客户端连接到哪里。

## 6. 与 LLM、VLM 的区别

Compose 当前管理的是 backend、frontend、Milvus 和 PostgreSQL。LLM/VLM 可以是外部 API，也可以运行在宿主机或另一个容器里，取决于环境变量：

- 云端模型：backend 容器访问云端 HTTPS API；
- 宿主机模型：backend 容器可以通过 `host.docker.internal` 访问宿主机服务；
- 模型容器：可以在 Compose 中增加模型服务，并使用服务名连接。

因此，`host.docker.internal` 只表示“容器访问宿主机”，不表示模型一定在云端，也不表示 Docker 会自动启动模型。

## 7. 记忆要点

### 7.1 后端：FastAPI 与 Uvicorn

所有后端框架的基本职责都相似：接收前端的 HTTP 请求，按照路径和方法匹配路由，执行业务逻辑，再返回响应。ScholarRAG 选择 FastAPI，主要因为它使用 Python，能方便地使用 RAG 相关的 Python 库，并且适合异步调用数据库、模型 API 和 SSE 流式响应。

FastAPI 是定义 API 和业务入口的框架。例如：

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/health")
def health():
    return {"status": "ok"}
```

这段代码创建了应用对象和一个路由，但不会自己监听网络端口。Uvicorn 是 ASGI Web 服务器，它监听端口、接收 HTTP 请求，并把请求交给 FastAPI：

```text
浏览器 -> Uvicorn（监听 8000 端口） -> FastAPI（匹配路由） -> 业务函数
```

本机运行学习版后端时，需要在 Python 虚拟环境中安装依赖。把依赖写到 `requirements.txt`，再执行 `pip install -r requirements.txt`；其中可包含：

```text
fastapi
uvicorn[standard]
```

启动命令示例：

```powershell
uvicorn app.main:app --reload --port 8000
```

其中 `app.main:app` 表示导入 `app/main.py` 文件中的 `app` 对象；`--reload` 表示开发时修改代码后自动重启。最终放入 Docker 时，这些依赖安装在 backend 镜像中，不要求安装到宿主机的全局 Python。

#### FastAPI 与开发者的责任边界

`app = FastAPI()` 创建的是整个后端应用的入口对象。路由、中间件、请求校验规则、异常处理规则、启动/关闭钩子和自动 API 文档都会注册或关联到这个对象上。

开发者通常需要编写或配置：

- 路由：路径、HTTP 方法和处理函数；
- 业务逻辑：数据库读写、调用模型、文件处理等；
- 请求与响应模型：用类型和 Pydantic 模型声明接口数据；
- 项目需要的中间件：例如 CORS、认证、日志；
- 资源生命周期：创建和关闭数据库连接池、模型客户端等共享资源。

FastAPI 会自动处理通用的 Web 工作：接收和解析 HTTP 请求、按路由分发、依据类型标注校验数据、将普通 Python 返回值转为 JSON、生成基础错误响应和 `/docs` 交互式接口文档。

例如下面的 `ChatRequest` 告诉 FastAPI 请求 JSON 必须有字符串 `query`；解析和校验不需要手写：

```python
from pydantic import BaseModel

class ChatRequest(BaseModel):
    query: str

@app.post("/api/chat")
async def chat(request: ChatRequest):
    return {"answer": f"你问的是：{request.query}"}
```

Pydantic 是独立的数据模型和数据校验库，不是 FastAPI 本身；但 FastAPI 深度集成它。当路由参数标注为 `request: ChatRequest` 时，FastAPI 会使用 Pydantic 自动读取请求 JSON、构造 `ChatRequest` 对象，并检查字段是否满足定义。

例如下面的数据符合模型：

```json
{
  "query": "这篇论文讲什么？",
  "session_id": "abc123"
}
```

若必填的 `query` 缺失或类型不正确，FastAPI 会在业务函数执行前返回 HTTP `422 Unprocessable Entity` 校验错误。模型结构也会显示在 `/docs` 中。这样不需要在每个路由函数里手写 JSON 解析和重复的 `if` 校验。

框架不会替项目猜测数据库或模型如何初始化和释放，因此这类资源仍要由开发者在应用启动、关闭阶段配置。可以把职责记为：

```text
FastAPI：提供通用 Web 运行机制
开发者：声明接口、配置项目、编写业务逻辑、管理项目专属资源
```

### 7.2 前端：Vite 与 Nginx

前端也需要 Web 服务器来把 React 页面交给浏览器，但开发和部署使用不同工具：

| 模式 | 前端服务器 | 运行位置 | 主要职责 |
|---|---|---|---|
| 开发 | Vite dev server | 宿主机 | 编译开发代码、热更新、代理 API |
| Docker 部署 | Nginx | frontend 容器 | 提供已构建的静态文件、反向代理 API |

开发时执行 `npm run dev`，Vite 通常监听 `localhost:5173`。前端代码请求相对路径 `/api/health` 时，Vite 会依据 `vite.config.js` 代理到 `http://localhost:8000/api/health`：

```text
浏览器 -> Vite（localhost:5173） -> Uvicorn/FastAPI（localhost:8000）
```

这里使用 `localhost:8000`，是因为 Vite 运行在宿主机；Compose 的 `8000:8000` 端口映射会再把请求送入 backend 容器。

运行 `docker compose up` 时，前端不再运行 Vite，而是运行 frontend 容器里的 Nginx。Nginx 配置会把 `/api/` 代理到 `http://backend:8000`，因为 Nginx 和 backend 都位于 Compose 内部网络：

```text
浏览器 -> localhost:5173 -> Nginx（frontend 容器） -> backend:8000（backend 容器）
```

因此，开发阶段通常有两个独立进程：Vite 运行前端代码，Uvicorn 运行后端代码。Docker 部署阶段通常也有两个对应的 Web 服务角色：Nginx 提供前端静态文件，Uvicorn 在 backend 容器中运行 FastAPI。

```text
Docker       运行容器的技术
容器         一个相对独立的运行环境
Compose      用配置统一管理多个容器
服务名       Compose 网络中连接其他容器的名字
宿主机端口   让电脑或浏览器访问容器的入口
云端数据库   不由本地 Compose 启动，需使用云端连接地址
FastAPI      定义后端 API、路由和业务入口的 Python 框架
Pydantic     定义、解析和校验请求/响应数据的 Python 库
Uvicorn      监听端口并将 HTTP 请求交给 FastAPI 的 ASGI 服务器
Vite         开发阶段的前端服务器，支持热更新和 API 代理
Nginx        部署阶段提供前端静态文件并代理 API 的 Web 服务器
```

## 8. 数据库与 PostgreSQL 持久化

### 8.1 为什么从内存迁移到数据库

最初的学习版使用 Python 字典保存会话：

```python
sessions = {}
```

它适合先理解路由和数据流，但后端进程重启后，字典会清空，聊天历史也随之丢失。PostgreSQL 把数据保存在独立数据库服务中，因此后端重启后仍可以查询已有会话和消息。

```text
内存字典：后端进程退出 -> 数据丢失
PostgreSQL：后端进程退出 -> 数据仍保存在数据库 volume 中
```

### 8.2 学习版 PostgreSQL 容器

学习版在 `learning-implementation/docker-compose.yml` 中单独定义 PostgreSQL 服务，不与原项目数据库混用：

```text
镜像：postgres:16-alpine
数据库：learning_rag
容器端口：5432
宿主机端口：55432
数据卷：learning_postgres_data
```

本机运行的 Uvicorn 后端使用这个连接地址：

```text
postgresql://postgres:postgres@localhost:55432/learning_rag
```

连接地址格式为：

```text
postgresql://用户名:密码@主机:端口/数据库名
```

常用命令：

```cmd
cd G:\scholar-rag\learning-implementation
docker compose up -d
docker compose ps
docker compose exec postgres psql -U postgres -d learning_rag
docker compose down
```

`55432:5432` 的含义是“宿主机 55432 端口映射到容器内部 PostgreSQL 的 5432 端口”。本机进程通过 `localhost:55432` 访问容器；同一 Compose 网络中的其他容器则应使用 `postgres:5432`。

### 8.3 表与关系

学习版有两张业务表：

```text
sessions（一条会话）
    1
    └── 多条 messages（一条条用户问题和助手回答）
```

`sessions` 保存会话元数据：

```text
session_id、title、created_at、updated_at
```

`messages` 保存对话内容：

```text
message_id、session_id、role、content、created_at
```

`messages.session_id REFERENCES sessions(session_id)` 定义外键：消息必须关联一个已经存在的会话。被引用的 `sessions.session_id` 是主键，因此能唯一定位父记录。

```sql
session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE
```

`ON DELETE CASCADE` 表示删除一条会话时，数据库自动删除它所属的所有消息，避免留下没有父会话的“孤儿消息”。

`role TEXT NOT NULL CHECK (role IN ('user', 'assistant'))` 是检查约束，限制角色只能是用户或助手。

### 8.4 索引

```sql
CREATE INDEX IF NOT EXISTS idx_messages_session_id
ON messages(session_id);
```

这会建立数据库内部索引，不会改变 SQL 查询写法。查询仍然写成：

```sql
SELECT role, content
FROM messages
WHERE session_id = '某个会话 ID';
```

数据库会自行判断是否使用 `idx_messages_session_id`，以更快定位该会话的消息。索引也可能帮助 `JOIN`、`UPDATE`、`DELETE` 等按 `session_id` 查找的操作；代价是占用额外空间，并且写入数据时需要维护索引，因此应优先为常用于 `WHERE`、`JOIN` 或 `ORDER BY` 的字段建立。

### 8.5 Python 如何连接并执行 SQL

Python 使用 `psycopg[binary]` 驱动连接 PostgreSQL。`backend/app/database.py` 只负责提供连接：

```python
def get_connection() -> Connection:
    return psycopg.connect(DATABASE_URL)
```

`backend/app/store.py` 负责数据访问；router 不直接写 SQL。这种分层是：

```text
chat.py / sessions.py（HTTP 路由）
        -> store.py（会话与消息读写）
        -> database.py（创建 PostgreSQL 连接）
        -> PostgreSQL（sessions、messages 表）
```

参数化 SQL 示例：

```python
cur.execute(
    """
    INSERT INTO sessions (session_id, title, created_at, updated_at)
    VALUES (%s, %s, to_timestamp(%s), to_timestamp(%s))
    """,
    (session_id, title, now, now),
)
```

第一个参数是 SQL 模板，第二个参数元组依次填入四个 `%s`。`psycopg` 会安全传递参数；不要用 f-string 把用户数据直接拼入 SQL。`to_timestamp()` 把 Python 的 `time.time()` Unix 秒数转换为 PostgreSQL 的 `TIMESTAMPTZ` 时间。

当前存储层的 SQL 映射：

```text
create_session()  -> INSERT INTO sessions
list_sessions()   -> SELECT ... FROM sessions ORDER BY updated_at DESC
get_session()     -> SELECT ... FROM sessions WHERE session_id = %s
touch_session()   -> UPDATE sessions SET updated_at = NOW()
delete_session()  -> DELETE FROM sessions
add_message()     -> INSERT INTO messages
list_messages()   -> SELECT ... FROM messages WHERE session_id = %s
```

上下文管理器写法：

```python
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(...)
```

表示完成后会关闭游标和连接；正常结束时，连接上下文会提交事务，异常时会回滚。

以后新增知识点时，优先补充到最具体的章节；如果是新的主题，再增加一个二级标题，并附上对应源码文件或验证命令。
