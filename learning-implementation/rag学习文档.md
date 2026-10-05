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

#### 异步、事件循环与线程池

同步代码按顺序执行：当前函数没有完成，后面的代码就不会开始。异步代码仍然是一行一行执行，但一个异步任务在等待数据库、网络或其他 I/O 时，可以把执行权交还给事件循环，让事件循环去处理其他已经准备好的任务。

事件循环可以理解为异步任务的调度器。Uvicorn 启动事件循环；FastAPI 收到 HTTP 请求后，会为路由函数安排一个协程任务。一个请求对应一个路由任务，多个请求就可能对应多个任务：

```text
请求 A -> 路由任务 A
请求 B -> 路由任务 B
请求 C -> 路由任务 C
```

`async def` 定义的是协程函数：

```python
async def task_a():
    await asyncio.sleep(1)
```

调用 `task_a()` 时，得到的是协程对象，函数体还没有真正执行。协程对象可以直接等待：

```python
result = await task_a()
```

也可以注册成独立任务：

```python
task = asyncio.create_task(task_a())
result = await task
```

这两种写法如果创建任务后马上等待，效果通常很接近。`create_task()` 的作用在于先把协程安排出去，让当前任务可以先做其他事情：

```python
task_a_handle = asyncio.create_task(task_a())
await task_b()
result_a = await task_a_handle
```

如果写成：

```python
await task_a()
await task_b()
```

那么 `task_b()` 要等 `task_a()` 完成后才会被调用。这两个任务按顺序执行。不过，在 `task_a()` 等待期间，事件循环仍能处理其他已经存在的任务。`await` 不会凭空创建新任务，也不会切换到另一个事件循环。

异步函数只有在内部等待异步操作时才能让出事件循环：

```python
await async_database_query()
```

如果在 `async def` 中直接调用同步阻塞函数，它仍会占住事件循环：

```python
async def handler():
    time.sleep(5)  # 阻塞事件循环
```

`asyncio.to_thread()` 用来把这种同步阻塞函数交给线程池：

```python
result = await asyncio.to_thread(blocking_function)
```

它和 `create_task()` 的职责不同：

```text
create_task()：把协程安排给事件循环
to_thread()：把同步阻塞函数安排给线程池
```

当前学习版的 PDF 上传接口使用了 `to_thread()`：

```python
await asyncio.to_thread(UPLOAD_DIR.mkdir, parents=True, exist_ok=True)
size_bytes = await asyncio.to_thread(_save_upload, file.file, temporary_path)
await asyncio.to_thread(os.replace, temporary_path, destination_path)
```

这三个操作属于同一个 HTTP 请求和同一个路由协程任务，并且因为每一步都有 `await`，所以仍然按顺序执行：先创建目录，再保存文件，最后重命名。`to_thread()` 不会让一次上传自动变快，它的作用是让文件读写在线程池中进行，使事件循环可以在等待期间处理其他请求。

因此，异步主要提高并发处理能力，不代表单个请求一定更快。当前学习版的聊天和会话存储仍使用同步 `psycopg` 连接；虽然路由写成了 `async def`，同步数据库调用仍可能阻塞事件循环。以后可以改用异步数据库驱动，或把同步数据库调用放进 `asyncio.to_thread()`。

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

#### 数据卷与挂载

容器自身的文件系统通常跟随容器生命周期。若 PostgreSQL 只把数据库文件写在容器内部，删除并重新创建容器后，原有表和数据可能丢失。

学习版 Compose 中的这行配置：

```yaml
- learning_postgres_data:/var/lib/postgresql/data
```

表示把 Docker 管理的数据卷 `learning_postgres_data` 挂载到容器内 PostgreSQL 保存数据的目录 `/var/lib/postgresql/data`：

```text
Docker 数据卷 learning_postgres_data
        -> 挂载到容器内部 /var/lib/postgresql/data
        -> PostgreSQL 在该目录读写数据库文件
```

`learning_postgres_data` 是 Docker 管理的持久存储名称，底层对应 Docker 自己维护的真实磁盘位置。`/var/lib/postgresql/data` 只是 PostgreSQL 容器看到的路径。即使容器被 `docker compose down` 移除，只要没有删除数据卷，下次新容器重新挂载这个卷后，数据库和已有数据仍然存在。

挂载是一个通用概念：把容器外的存储映射到容器内某个路径。常见来源有两种：

| 类型 | Compose 示例 | 存储位置 | 用途 |
|---|---|---|---|
| Docker volume | `learning_postgres_data:/var/lib/postgresql/data` | Docker 管理的位置 | 保存数据库数据 |
| bind mount | `./db/init.sql:/docker-entrypoint-initdb.d/01-init.sql:ro` | 项目目录中的实际文件 | 提供配置、源码或初始化脚本 |

`init.sql` 的挂载中，左侧是宿主机项目中的文件，右侧是容器路径；末尾 `:ro` 表示只读，容器可以读取脚本但不能修改宿主机的原文件。

Docker volume 默认通常没有单独的固定容量上限，会随着数据库表、索引、事务日志和临时文件增长，直到 Docker 可用磁盘空间不足。可以查看 Docker 使用空间和卷信息：

```cmd
docker system df -v
docker volume inspect learning-implementation_learning_postgres_data
```

Compose 往往会在卷名前加项目名前缀，因此实际卷名可能是 `learning-implementation_learning_postgres_data`，而不是配置里写的 `learning_postgres_data`。

以下命令会删除当前 Compose 项目未被保留的容器，但默认保留 volume：

```cmd
docker compose down
```

以下命令会连同项目数据卷一起删除，因此学习数据库中的表和数据无法恢复，执行前必须确认不再需要它们：

```cmd
docker compose down -v
```

`docker volume prune` 会删除所有未被容器使用的数据卷，也需要先确认没有要保留的数据库数据。

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

### 8.5 文件表与上传接口

上传 PDF 的第一版只负责校验扩展名和大小，并将原始文件保存到 `backend/uploads/{file_id}.pdf`。为了让上传的文件可以被列出和删除，学习版增加了 `files` 表：

```sql
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

`file_id` 同时是数据库主键和磁盘文件名中的 UUID；`filename` 保存用户上传时的原始文件名；`size_bytes` 保存实际写入的字节数；`created_at` 记录元数据写入时间。数据库表保存的是管理信息，PDF 二进制内容仍保存在 `uploads/` 目录。

当前文件接口是：

```text
POST   /api/files/upload       校验并保存 PDF，同时写入 files 表
GET    /api/files               按创建时间倒序返回文件元数据
DELETE /api/files/{file_id}     删除磁盘文件和对应的元数据
```

上传时先将内容写入临时文件，成功后原子重命名为 `{file_id}.pdf`，再写入 `files` 表。元数据写入失败时会清理已保存的文件，避免留下没有记录的 PDF。删除时先查询元数据，找不到文件返回 `404`；找到后删除磁盘文件，再删除表记录。

文件管理完成后，学习版先用独立模块验证 PDF 解析，不把解析逻辑直接塞进上传路由。`backend/app/pdf_parser.py` 使用 Docling 的 `DocumentConverter`，把每个文档元素保存为结构化数据：

```python
from app.pdf_parser import extract_body_text, parse_pdf

result = parse_pdf("paper.pdf")
print(result.page_count)
for element in result.elements:
    print(element.order, element.element_type, element.text)
print(extract_body_text(result))
```

`ParsedPdf` 保存页数和元素列表。每个 `ParsedElement` 保存本次解析内的 ID、学习版类型、Docling 原始类型/类别、文本、原始遍历顺序、页码、bbox、章节路径、来源位置和相关元素 ID。`to_dict()` 可将结果转换为 JSON 可序列化的字典。图片、表格和图注各自是独立元素；图片元素不通过 Markdown 回退重复导出图注。

Docling 的一个文字元素可能跨越多页。`page_num` 和 `bbox` 便于定位该元素的第一个页面来源；`provenance` 列表保留 Docling 返回的全部页码和 bbox，因此不会把跨页段落拆成多个元素，也不会丢掉后续页面的坐标。`order` 记录 Docling 原始遍历位置，过滤图内数字后保留原始序号空档，不按 bbox 自行重排。

`section_path` 根据 Docling 标题层级保存当前章节上下文。当前 Docling 版本对这篇样例论文的标题都返回 `level=1`，所以真实结果中路径会随每个新标题切换；测试也覆盖了 Docling 提供多个层级时，标题栈如何截断旧子级。`related_ids` 用于连接图片/表格与独立图注，也会在明确且唯一匹配时连接正文中的 `Fig. 1`、`Table I` 等引用。遇到重复编号而目标不唯一时，不猜测关系。未知 Docling 类型会以 `unknown` 保留，并同时记录其原始 Python 类型和类别。

需要正文视图时使用 `extract_body_text(result)`。它按 `order` 收集段落、列表项、标题和公式，跳过图片、表格、图注和脚注；元素间以空行分隔，保留 Docling 自身的段落边界，不因为图注或图片而擅自合并前后正文。`include_formulas=False` 可以排除公式。

解析仍是独立模块，不接入上传路由；chunking 也先作为独立模块验证，不自动触发上传解析，不接入向量化或检索。

#### 图片区域中的短数字

PDF 里的文字除了内容，还带有页面坐标（bounding box，简称 bbox）。论文图表中可能有很小或渲染不明显的数字文字对象；Docling 仍可能把它们作为普通文本元素返回。学习版解析器通过 `is_text_inside_picture(text_item, picture_items)` 判断短纯数字是否位于同一页图片 bbox 内，并为图片边缘留 4 个 PDF 坐标点的容差；符合条件的数字不加入正文文本。

这里不能全局删除纯数字，否则可能误删年份、编号或正文数据。过滤条件要同时考虑文字内容、页码和位置。这个规则只移除落在图框内或距边缘 4 点以内的 1–4 位纯数字；被过滤的元素不会进入结构化结果，其余元素保留 Docling 原始顺序。前五页诊断结果中第二页的 `250/200/150/100/50` 被过滤。少数正文块仍可能在图片或图注附近分散；本阶段忠实保留 Docling 的元素边界，不预处理原 PDF，也不擅自合并段落。

#### Parent/Child Chunk 与长文本切分

解析元素保留 Docling 的结构边界；chunk 是为后续检索准备的文本单元。学习版通过 `backend/app/chunker.py` 将每个有文本的正文元素单独转换成一个 parent，不把相邻段落拼在一起。较长的段落、列表项和公式可以拆成多个 child；表格保持完整。若一个 caption 与表格相关联，且 caption 文本已包含在表格元素文本中，chunker 会跳过这个重复 caption chunk；结构化解析结果仍保留原 caption 和关联关系，而 table chunk 的 `related_element_ids` 会排除已折叠 caption 的 ID。章节标题只更新后续正文的 `section_path`，不单独生成 parent 或检索 child，避免短标题占用 Top-k。child 记录 `parent_chunk_id`，并保留来源元素 ID、元素类型、页码、章节路径、相关元素 ID 和页面 provenance。

图片使用 figure chunk 表示。解析阶段仍保留 `figure` 和 `caption` 两个结构化元素；chunk 阶段把关联 caption 的文字合并到 figure 的 `context`，并跳过这个 caption 的独立 chunk，避免同一段图注重复 embedding。figure 不拆分，所以 figure parent 和 figure child 的 `context` 相同；child 用于检索，parent 用于命中后的完整上下文。传入 `parse_pdf(..., figure_dir=...)` 后，学习版会用 PyMuPDF 按 figure 的 bbox 将图片裁剪到独立目录，图片路径写入 parent 和 child 的 metadata：`image_path`。图片二进制本身不做文本 embedding，命中 figure child 后再根据 `image_path` 交给 VLM。

切分使用 LangChain 的 `RecursiveCharacterTextSplitter`，默认目标长度为 500 个字符、重叠 50 个字符。分隔符依次尝试段落换行、换行、句号、问号、感叹号、分号和空格；这里数的是字符，不是模型 token。切分按单个解析元素独立进行，所以不会把图注或下一段混进当前段落。章节路径会作为上下文前缀加到 parent 和每个 child；分隔标点保留在前一个 child 末尾。

parent 和 child 是从解析文本派生的两种表示，不是两份原始 PDF。当前实现只在运行期间返回这两组对象，并写入检查用 Markdown；尚未将 chunk 保存到数据库或 Milvus。若以后持久化，通常会保存 parent 供命中后取回更完整上下文，并单独保存/向量化较小的 child；原 PDF 仍只保留一份。过滤章节标题和表格内重复 caption 后，当前样例生成 175 个 parent、219 个 child，其中 24 个 parent 被拆分；可用下面的命令重新生成完整预览：

```cmd
cd learning-implementation\backend
..\.venv\Scripts\python.exe -X utf8 scripts\export_chunks.py
```

预览默认写入 `backend/docling-inspection/chunks_preview.md`，按 Parents 和 Children 两部分展示，便于检查每个 child 是否保留了足够的上下文、边界是否合适。这个诊断报告位于本地忽略目录，不会作为正式解析结果提交。

#### Child Chunk 的 Embedding

chunk 生成后，下一步是把用于检索的 child 文本转换成向量。学习版的 `backend/app/embedding.py` 用 `EmbeddingService` 封装 Sentence Transformers：`embed_texts()` 批量处理多个 child，`embed_query()` 处理用户问题，`dimension` 返回模型向量维度。默认模型沿用原项目配置的 `BAAI/bge-small-en-v1.5`。

嵌入模型把一段文本映射成固定长度的数字数组。语义相近的文本，其向量通常更接近；后续向量库会根据这种距离返回 Top-k child。服务要求模型返回归一化向量，便于后续使用余弦相似度或内积比较。当前模块只负责“文本 → 向量”，不保存向量，也不连接 Milvus。

第一次真实运行会下载模型文件，因此先安装依赖，再执行最小验证：

```cmd
cd learning-implementation
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
cd backend
..\.venv\Scripts\python.exe -c "from app.embedding import EmbeddingService; s=EmbeddingService(); v=s.embed_texts(['RAG combines retrieval and generation.']); q=s.embed_query('What is RAG?'); print('dimension:', s.dimension); print('document:', len(v), len(v[0])); print('query:', len(q))"
```

验证结果应显示一个文档向量、一个查询向量，并且两者维度相同。这个阶段只验证模型和接口是否正常；等向量化通过后，再实现本地相似度检索，最后接 Milvus。

#### 本地 Cosine Top-k 检索

Embedding 验证后，学习版先用 `backend/app/retriever.py` 的 `InMemoryRetriever` 做本地检索。它接收一组 child 和对应向量，查询时接收问题向量，计算每个 child 与问题的余弦相似度，按分数从高到低返回前 `top_k` 个 `RetrievalHit`。这个阶段不需要 Milvus，目的是单独验证向量化和检索排序是否符合预期。

```python
retriever = InMemoryRetriever(children, child_vectors)
query_vector = embedding_service.embed_query("How is depth estimated from endoscopy images?")
hits = retriever.search(query_vector, top_k=3)
for hit in hits:
    print(hit.score, hit.chunk.chunk_id, hit.chunk.context[:160])
```

这里搜索的是 child；命中后可以用 `hit.chunk.parent_chunk_id` 找到完整 parent。`top_k=3` 表示最多返回三个 child，不代表答案一定正确；之后要用人工标注的问题集计算 Recall@k 等指标。当前本地检索器把向量保存在内存中，程序退出后数据消失，下一阶段才学习 Milvus 持久化。

可以用真实论文做一次端到端的本地验证：

```cmd
cd learning-implementation\backend
..\.venv\Scripts\python.exe -c "from app.pdf_parser import parse_pdf; from app.chunker import create_chunks; from app.embedding import EmbeddingService; from app.retriever import InMemoryRetriever; r=parse_pdf('../1710.11216v3.pdf'); c=create_chunks(r).children; e=EmbeddingService(); vs=e.embed_texts([x.context for x in c]); hits=InMemoryRetriever(c,vs).search(e.embed_query('How is depth estimated from endoscopy images?'),top_k=3); [print(h.score, h.chunk.chunk_id, h.chunk.context[:160].replace(chr(10), ' ')) for h in hits]"
```

应看到三个按分数降序排列的 child。由于这是英文论文和通用 Embedding 模型，先观察结果是否落在 depth estimation 相关段落，不要把一次 Top-k 输出当成正式评测结论。

### 8.6 Python 如何连接并执行 SQL

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
