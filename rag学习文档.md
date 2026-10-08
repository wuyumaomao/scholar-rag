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

这里搜索的是 child；如果要返回完整上下文，可以在构造检索器时传入 `parents`，然后调用 `search(..., expand_parents=True)`。此时 `top_k` 表示最终返回的 parent 数，`child_top_k` 表示展开前考察多少个 child 候选；多个 child 属于同一个 parent 时只保留一次，并使用排名最高的 child 分数。例如：

```python
retriever = InMemoryRetriever(children, child_vectors, parents=chunk_result.parents)
hits = retriever.search(
    query_vector,
    top_k=3,
    child_top_k=6,
    expand_parents=True,
)
```

如果命中的是 figure child，展开后的 figure parent 会保留 `context`、`image_path` 和其他 metadata，后续可以据此读取图片交给 VLM。`top_k=3` 表示最终最多返回三个 parent，不代表答案一定正确；之后要用人工标注的问题集计算 Recall@k 等指标。当前本地检索器把向量保存在内存中，程序退出后数据消失，下一阶段才学习 Milvus 持久化。

可以用真实论文做一次端到端的本地验证：

```cmd
cd learning-implementation\backend
..\.venv\Scripts\python.exe -c "from app.pdf_parser import parse_pdf; from app.chunker import create_chunks; from app.embedding import EmbeddingService; from app.retriever import InMemoryRetriever; r=parse_pdf('../1710.11216v3.pdf'); c=create_chunks(r).children; e=EmbeddingService(); vs=e.embed_texts([x.context for x in c]); hits=InMemoryRetriever(c,vs).search(e.embed_query('How is depth estimated from endoscopy images?'),top_k=3); [print(h.score, h.chunk.chunk_id, h.chunk.context[:160].replace(chr(10), ' ')) for h in hits]"
```

#### 本地 BM25 child 检索

向量检索按语义相似度排序，BM25 按词项是否出现在文本中排序。学习版的 `backend/app/bm25_retriever.py` 在内存中实现 Okapi BM25：先把 child 文本和 query 转成小写词元，再根据词频、逆文档频率和文档长度计算分数。BM25 本身只返回 child；在 RRF 融合阶段，会把 dense 和 BM25 的 child 排名分别映射到 parent，并去除重复 parent。

```python
from app.bm25_retriever import BM25Retriever

bm25 = BM25Retriever(chunk_result.children)
hits = bm25.search("How is depth estimated from endoscopy images?", top_k=20)
for hit in hits:
    print(hit.score, hit.chunk.chunk_id, hit.chunk.context[:160])
```

BM25 的分数和 cosine 分数不是同一种量纲，所以不能直接把两者相加。混合检索时只使用它们各自的排名，通过 RRF 融合；`top_k=20` 表示先保留 20 个 child 候选，最终 parent 数量由后续融合阶段决定。

#### Parent 去重与 RRF 融合

Dense 和 BM25 都返回 child，但同一个 parent 可能包含多个 child。如果直接合并 child，会让一个 parent 因为命中多个 child 而重复出现。因此 `backend/app/rrf.py` 先在每个检索通道内部按 `parent_chunk_id` 分组，只保留该 parent 的最佳排名，再使用 Reciprocal Rank Fusion：

```text
RRF(parent) = 1 / (rrf_k + dense_rank)
            + bm25_weight / (rrf_k + bm25_rank)
```

学习版的 `fuse_parent_hits()` 默认使用 `rrf_k=60`，输入 Dense 和 BM25 的 child 命中以及 parent 列表，输出去重后的 parent 命中。某个 parent 只在一个通道出现时只获得一项分数；两个通道都出现时会累加两项分数。当前应用配置 `BM25_WEIGHT=1.25`，表示 BM25 的排名贡献乘以 1.25；它仍然是排名融合，不是把原始 BM25 分数与 Dense 分数相加。默认可以先取 `top_k=10`，再交给 Cross-Encoder 做精排。

#### 本地检索 API

`POST /api/retrieve` 将 Dense 与 BM25 混合检索接入主流程：

```text
解析 PDF → 创建 parent/child → 建立 Dense 向量索引和 BM25 索引
                                  ↓
查询时：Dense child top fetch_k + BM25 child top fetch_k
                                  ↓
各通道按 parent 去重 → RRF 融合 →（可选 Cross-Encoder 重排）
                                  ↓
返回 top_k parent → VLM 图片增强
```

请求必须提供已上传 PDF 的 `file_id` 和非空 `query`。`child_top_k`（默认配置项 `FETCH_K=20`）控制 Dense 和 BM25 各自最多取多少个 child 候选；`top_k`（默认 `TOP_K=5`）控制融合后最多返回多少个 parent。当前默认 `MIN_SCORE=0.8`，只过滤 Dense 候选；BM25 候选独立参与融合，因此即使某个 parent 的 Dense 分数低于阈值，它仍可能通过 BM25 被召回。`RRF_K` 控制倒数排名融合的平滑参数。默认值集中在 `Settings`，可由环境变量或单次请求显式覆盖。

##### 元数据过滤

`/api/retrieve` 可以在 Dense 和 BM25 给 child 打分之前，按 chunk metadata 缩小候选范围。过滤器作为请求里的 `filters` 对象传入，支持元素类型、PDF 物理页码范围和章节路径前缀：

```json
{
  "filters": {
    "element_types": ["figure", "table"],
    "page_from": 2,
    "page_to": 8,
    "section_path_prefix": ["Methods"]
  }
}
```

条件组之间采用 AND；`element_types` 列表内采用 OR。页码范围两端都包含，chunk 有任一页落入范围就符合。章节路径按完整层级项匹配前缀，因此 `Methods` 会包含 `Methods > Experiments`，但不会误匹配 `MethodsX`。类型可用 `paragraph`、`figure`、`table`、`formula`、`list_item`、`caption`、`footnote`、`section_header` 和 `unknown`；其中不会生成 chunk 的标题类型自然返回空结果。没有传 `filters` 或传空对象时，原检索行为不变。BM25 会按过滤后的候选集合重新计算文档频率和平均长度，避免不相关章节影响过滤范围内的词法排序。

例如，只查第 2–8 页 Methods 章节里的图和表：

```cmd
curl.exe -X POST "http://127.0.0.1:8100/api/retrieve" -H "Content-Type: application/json" -d "{\"file_id\":\"替换为上传响应中的file_id\",\"query\":\"What does the architecture diagram show?\",\"filters\":{\"element_types\":[\"figure\",\"table\"],\"page_from\":2,\"page_to\":8,\"section_path_prefix\":[\"Methods\"]}}"
```

##### 元数据过滤的 benchmark 对照

现有 7 篇论文、116 题中，有 9 题明确问 Figure，1 题明确问 Table。只对这 10 题启用严格类型过滤（Figure 题只保留 `figure`，Table 题只保留 `table`），其余问题不加过滤；没有用 evidence 的 element、页码或章节反推 filter，避免答案泄漏。Dense/BM25 均取 child Top 20，`min_score=0.7`，RRF 的 `k=60`、BM25 权重 `1.25`，rerank 候选 20、最终 Top 5。

| 范围 | 设置 | Recall@5 | Precision@5 | MRR@5 |
| --- | --- | ---: | ---: | ---: |
| 全部 116 题 | 不加类型过滤 | 0.7862 | 0.2414 | 0.7233 |
| 全部 116 题 | 只在点名 Figure/Table 的题上严格过滤 | 0.7798 | 0.2379 | 0.7319 |
| 10 道 Figure/Table 题 | 不加类型过滤 | 0.5500 | 0.2000 | 0.6500 |
| 10 道 Figure/Table 题 | 严格按图/表类型过滤 | 0.4750 | 0.1600 | 0.7500 |

严格类型过滤让这 10 题的第一个相关结果排名更靠前（MRR 上升），但整体召回和 Precision 下降。原因是问题虽然点名图表，答案证据仍常包含解释图表的正文段落；只允许 `figure` 或 `table` 会把这些段落挡掉。比如 Figure 5 的网络结构题仍把对应图 parent 排在首位，而另一题的图表说明也能更早命中；但这不足以抵消被过滤掉的正文 evidence。对“只看图表”这个明确意图，类型过滤有价值；如果想回答“图表说明了什么”，更合适的策略是让图表和正文都可检索，或将相关正文/图注绑定为同一返回上下文，而不是默认强制只搜图表。

速度用原始 `1710.11216v3.pdf` 的 Figure 5 问题单独测量：该文档有 219 个 child，其中 10 个 figure child。固定已生成的 query vector，预热后交替重复 100 次 Dense + BM25 + RRF（不含 query embedding、解析/建索引和 Cross-Encoder），中位查询时间从 5.38 ms 降至 0.64 ms，约快 88%。这说明当过滤结果远少于全文时，过滤可减少查询打分开销；该微基准只有一篇论文、一个查询，不能外推成整体服务延迟提升。首次请求解析和向量化整篇 PDF 的时间不变。

现阶段结论：元数据过滤提供了用户明确限定范围时的控制能力，也能减少查询阶段的候选打分；严格类型过滤会牺牲部分 Recall，不能默认套在所有图表问题上。benchmark 没有用户指定的页码或章节范围，所以本轮没有用 gold 的页码/section 做过滤实验。

默认关闭 Cross-Encoder 时，响应中的 `score` 是 RRF 融合分数，不再是 cosine 相似度；不同查询的 RRF 分数也不适合直接当作概率比较。启用重排后，`score` 是 Cross-Encoder 输出的相关性分数，同样不是概率，且它和 RRF 分数不在同一量纲。响应还包含 `chunk_id`、`context` 和 `metadata`；figure parent 的 metadata 会包含 `image_path`，随后继续执行 VLM 图片描述增强。

第一次查询某个 PDF 时，服务会解析并向量化整份文件，因此可能需要等待 Docling 和 embedding 模型完成加载；后续查询复用进程内缓存。服务重启后缓存会消失，并在下次查询时重新构建。当前还没有把 parent、child 或向量持久化到 Milvus/PostgreSQL。

在 CMD 中先上传 PDF：

```cmd
curl.exe -X POST "http://127.0.0.1:8100/api/files/upload" -F "file=@G:\scholar-rag\learning-implementation\1710.11216v3.pdf"
```

从响应中复制 `file_id`，再查询（把示例 ID 替换成实际返回值）：

```cmd
curl.exe -X POST "http://127.0.0.1:8100/api/retrieve" -H "Content-Type: application/json" -d "{\"file_id\":\"替换为上传响应中的file_id\",\"query\":\"How is depth estimated from endoscopy images?\",\"top_k\":5,\"child_top_k\":6,\"min_score\":0.8}"
```

应看到最多三个按排序分数排列的 parent 结果。由于这是英文论文和通用 Embedding 模型，先观察结果是否落在 depth estimation 相关段落，不要把一次 Top-k 输出当成正式评测结论。

#### 检索基线评测：Recall@k、Precision@k 和 MRR

单次查询只能看到几个结果，不能说明检索器整体好不好。因此用 `evaluation-dataset\` 中的 JSONL benchmark 做批量评测。每条数据有一个英文问题和一组 gold `element_ids`；runner 把检索返回的 parent metadata 中的 `source_element_ids` 与 gold 对齐。多个 child 如果展开成同一个 parent，只计一次。

三个指标的定义是：

```text
Recall@k    Top-k 命中的 gold element 数 / gold element 总数
Precision@k Top-k 命中的结果数 / k
Precision@returned 实际返回的结果中命中的结果数 / 实际返回结果数
MRR         Top-k 内第一个命中 gold 的排名倒数，再对所有问题取平均
```

评测脚本支持 `--retrieval-mode dense`、`hybrid` 和 `hybrid-rerank`。第三种模式先用 Dense + BM25 + RRF 选出 parent 候选，再用 Cross-Encoder 对候选逐个评分、重新排序，最终只返回前 `k` 个。默认候选数由 `RERANK_CANDIDATE_K=20` 控制；BM25 的 RRF 权重默认是 `BM25_WEIGHT=1.25`。模型由 `RERANKER_MODEL` 指定，学习版默认使用较小的英文模型 `cross-encoder/ms-marco-MiniLM-L-6-v2`。为了公平比较，模式之间使用相同 benchmark、PDF、`k`、child 候选数和 `min_score`。Dense 模式保留旧基线；Hybrid 的 `RRF_K` 默认从配置读取。例如，对 7 篇论文、116 个问题运行三组对照：

```cmd
cd learning-implementation\backend
..\.venv\Scripts\python.exe scripts\evaluate_benchmark.py --retrieval-mode dense --pdf-dir C:\Users\93655\Desktop\paper --k 5 --child-top-k 20 --min-score 0.7 --output ..\evaluation-results-dense-comparison.json
..\.venv\Scripts\python.exe scripts\evaluate_benchmark.py --retrieval-mode hybrid --pdf-dir C:\Users\93655\Desktop\paper --k 5 --child-top-k 20 --min-score 0.7 --rrf-k 60 --output ..\evaluation-results-hybrid.json
..\.venv\Scripts\python.exe scripts\evaluate_benchmark.py --retrieval-mode hybrid-rerank --pdf-dir C:\Users\93655\Desktop\paper --k 5 --child-top-k 20 --min-score 0.7 --rrf-k 60 --rerank-candidate-k 10 --output ..\evaluation-results-hybrid-rerank.json
```

benchmark 默认启用本地索引缓存，目录为 `backend/data/benchmark-cache/`（该运行时目录被 Git 忽略）。每篇论文的缓存保存 Docling 结构化解析结果和 child 文本向量；命中后仍会从解析元素重建 parent/child chunk，并照常运行检索与 rerank。缓存文件使用 gzip JSON 和原子替换写入；损坏或不兼容时会显示警告并重新解析、向量化。

缓存指纹会在 PDF 内容、解析器或 chunker 源码、Docling/相关依赖版本、embedding 模型名称、chunk 长度/重叠参数或图片输出目录发生变化时失效。相同文件路径的旧缓存会被新版本覆盖。`--no-cache` 会忽略已有缓存并且不写缓存，不会删除已有缓存；`--cache-dir` 可更改目录。例如：

```cmd
..\.venv\Scripts\python.exe scripts\evaluate_benchmark.py --retrieval-mode hybrid-rerank --pdf-dir C:\Users\93655\Desktop\paper --k 5 --child-top-k 20 --min-score 0.7 --rrf-k 60 --bm25-weight 1.25 --rerank-candidate-k 20 --cache-dir data\benchmark-cache --output ..\evaluation-results-cached.json
```

2026-10-08 对 7 篇论文、116 个问题做了冷/热缓存验证，固定相同检索参数和本地 reranker：冷跑 387.4 秒，热跑 114.1 秒；7 篇全部 cache HIT，耗时减少约 70.5%。两次逐题检索结果完全一致，Recall@5=`0.7862`、Precision@5=`0.2414`、MRR=`0.7233`。节省主要来自跳过 Docling 和文档向量生成；热跑仍需加载模型并执行每个问题的 Dense/BM25/RRF 和 rerank。缓存约 6.51 MiB，不包含 PDF 原文。若要强制完整重建，可在命令末尾添加 `--no-cache`。

第一次运行 `hybrid-rerank` 需要下载 Cross-Encoder 权重；模型会在进程内复用，不会为每篇论文重新加载。API 在线启用时，在 `backend/.env` 设置 `RERANKER_ENABLED=true` 和 `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`，可选设置 `RERANK_CANDIDATE_K=10`，然后重启后端。候选 parent 少于 10 个时会全部参与重排。Cross-Encoder 只改变这批候选的顺序，不能找回未进入 RRF 候选集的 parent。

结果分别写入两个 JSON 文件，不会覆盖此前保存的 baseline。2026-10-07 使用 7 篇论文、116 个问题运行得到：

| 指标 | Dense | Dense + BM25 + RRF |
|---|---:|---:|
| Recall@5 | 0.6035 | 0.7151 |
| Precision@5 | 0.1776 | 0.2155 |
| Precision@returned | 0.1989 | 0.2155 |
| MRR | 0.5289 | 0.6467 |

使用本地 `cross-encoder/ms-marco-MiniLM-L-6-v2`，在 RRF 后保留 10 个 parent 候选并重排，得到第三组结果：

| 指标 | Dense | Dense + BM25 + RRF | Hybrid + Cross-Encoder |
|---|---:|---:|---:|
| Recall@5 | 0.6035 | 0.7151 | 0.7762 |
| Precision@5 | 0.1776 | 0.2155 | 0.2397 |
| Precision@returned | 0.1989 | 0.2155 | 0.2397 |
| MRR | 0.5289 | 0.6467 | 0.7228 |

这批数据上 Hybrid 的四项指标都高于 Dense，Cross-Encoder 重排后继续提升了四项指标，说明它改善了已经召回的 parent 候选顺序。它不能找回没有进入 RRF 候选池的 parent。当前 benchmark 以正向可回答问题为主，且 BM25 使用简单英文词元化；这些结果适合用作学习项目的阶段性对照，不代表不可答问题上的拒答能力。

#### HyDE：为 Dense 检索生成假设段落

HyDE（Hypothetical Document Embeddings）先让 LLM 根据问题写一段“看起来像论文证据”的假设文本，再把这段文本送入 embedding 模型。它的目的，是让短问题转换成更接近论文正文的语义表达；假设段落本身不是证据，也不会直接返回给用户。

学习版默认关闭 HyDE。启用时，Dense 使用生成的段落计算 query vector；BM25 和 Cross-Encoder 仍接收原始问题，以保留词面检索和问题相关性判断。配置 `LLM_ENABLED=true`、`LLM_BASE_URL` 和 `LLM_MODEL` 后，可通过检索 API 单次启用：

```cmd
curl.exe -X POST "http://127.0.0.1:8100/api/retrieve" -H "Content-Type: application/json" -d "{\"file_id\":\"替换为上传响应中的file_id\",\"query\":\"What does Figure 5 show about the depth estimation architecture?\",\"use_hyde\":true}"
```

运行 benchmark 时添加 `--use-hyde`，其余参数和不启用时保持一致，才能比较指标变化：

```cmd
..\.venv\Scripts\python.exe scripts\evaluate_benchmark.py --retrieval-mode hybrid-rerank --use-hyde --pdf-dir C:\Users\93655\Desktop\paper --k 5 --child-top-k 20 --min-score 0.7 --rrf-k 60 --rerank-candidate-k 10 --output ..\evaluation-results-hybrid-rerank-hyde.json
```

评测报告根级和每个数据集记录 `use_hyde`。如果显式开启但没有 LLM 配置，程序会报出需要补充的设置；如果远程生成请求失败，则记录 warning 并对该问题改用原始 query，评测仍可继续。启用 HyDE 会增加一次远程 LLM 请求及其延迟/费用，因此应在同一 benchmark 上对照 `use_hyde=false` 和 `true`，再决定是否保留。

2026-10-08 使用 `deepseek-flash` 对 7 篇论文、116 个问题做了同参数对照，检索器均为 `hybrid-rerank`，`k=5`、`child_top_k=20`、`min_score=0.7`、`rrf_k=60`、rerank 候选数 10，reranker 固定为本地 `cross-encoder/ms-marco-MiniLM-L-6-v2`：

| 指标 | 原始 query | HyDE | 变化 |
|---|---:|---:|---:|
| Recall@5 | 0.7762 | 0.7575 | -0.0187 |
| Precision@5 | 0.2397 | 0.2328 | -0.0069 |
| Precision@returned | 0.2397 | 0.2328 | -0.0069 |
| MRR | 0.7228 | 0.7277 | +0.0049 |

当前结果没有显示 HyDE 带来整体提升：Recall 和 Precision 略降，MRR 小幅上升。还要考虑模型有 25/116 次返回空文本，系统按设计回退到原问题；所以这次评测中约 21.6% 的问题并未真正使用 HyDE，结论只适用于当前模型、服务稳定性和 benchmark。两份逐题报告分别为 `evaluation-results-hyde-baseline.json` 和 `evaluation-results-hyde-deepseek-flash.json`。

#### 拆解 Dense、BM25、RRF 与重排的召回率

为了区分“候选阶段没召回”与“最终 Top K 截断”，对同一批 116 个问题统计各阶段的 evidence Recall。Dense/BM25 各取最多 20 个 child；Dense 使用 `min_score=0.7`；随后 parent 级 RRF 取 10 个候选，再由 Cross-Encoder 重排。Recall 按 gold Docling element 计算；child 命中后映射到它对应的 parent context，避免把同一个 parent 的多个 child 重复计算。

| 阶段 | Recall |
|---|---:|
| Dense Top 20 child（映射 parent context） | 0.7384 |
| BM25 Top 20 child（映射 parent context） | 0.8575 |
| RRF Top 10 parent 候选 | 0.8275 |
| Cross-Encoder 重排后 Top 10 | 0.8275 |
| RRF 排序直接截取 Top 5（未重排） | 0.7151 |
| Cross-Encoder 重排后 Top 5 | 0.7762 |
| RRF 排序直接截取 Top 3（未重排） | 0.5690 |
| Cross-Encoder 重排后 Top 3 | 0.6890 |
| Cross-Encoder 重排后 Top 2 | 0.6121 |

这说明候选召回总体较高，但 Dense Top 20 本身还有约四分之一的 gold element 没进入候选。RRF Top 10 的召回上限为 0.8275；重排不会增加候选，只改变顺序，所以 Top 10 的 Recall 不变。若用较小的 Top K，覆盖会下降；但在相同 K 下，当前 Cross-Encoder 把更多相关 parent 排到前面：@3 从 0.5690 提到 0.6890，@5 从 0.7151 提到 0.7762。因此，不能把 Top 3 比 Top 5 的差异归因于 reranker 伤害 Recall；主要是最终上下文数量减少，reranker 实际上缓解了这部分损失。

Dense Top 20 因 `min_score=0.7` 平均实际返回 15.87 个 child（约 13.53 个不同 parent）；BM25 平均返回 20 个 child（约 16.32 个不同 parent）。这些是当前 benchmark 和参数下的宏平均，不能直接当作其他语料或查询的召回保证。

#### BM25 权重与 rerank 候选数对照

为了验证是否应该提高 BM25 在 RRF 中的影响，并增加 Cross-Encoder 的重排候选数，在同一批 7 篇论文、116 个问题上做了参数 sweep。固定 `dense_weight=1`、`rrf_k=60`、`child_top_k=20`、`min_score=0.7`，比较 `bm25_weight=1.0/1.25/1.5/2.0`、`rerank_candidate_k=10/15/20`，最终分别观察 Top 3 和 Top 5。RRF 的加权分数为：

```text
score(parent) = dense_weight / (rrf_k + dense_rank)
              + bm25_weight / (rrf_k + bm25_rank)
```

这里提高 BM25 权重，是放大 BM25 排名在 RRF 中的贡献；不是把原始 BM25 分数和向量分数直接相加。候选数表示进入 Cross-Encoder 的 parent 数量。完整汇总如下：

| BM25 权重 | rerank 候选数 | Recall@3 | Precision@3 | MRR@3 | Recall@5 | Precision@5 | MRR@5 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.00 | 10 | 0.6890 | 0.3420 | 0.7069 | 0.7762 | 0.2397 | 0.7228 |
| 1.00 | 15 | 0.6933 | 0.3448 | 0.7069 | 0.7776 | 0.2397 | 0.7211 |
| 1.00 | 20 | 0.6890 | 0.3420 | 0.7055 | 0.7819 | 0.2397 | 0.7218 |
| 1.25 | 10 | 0.6760 | 0.3362 | 0.6954 | 0.7518 | 0.2328 | 0.7088 |
| 1.25 | 15 | 0.6890 | 0.3420 | 0.7040 | 0.7791 | 0.2379 | 0.7191 |
| 1.25 | 20 | 0.6933 | 0.3448 | 0.7069 | 0.7862 | 0.2414 | 0.7233 |
| 1.50 | 10 | 0.6760 | 0.3362 | 0.6954 | 0.7518 | 0.2328 | 0.7088 |
| 1.50 | 15 | 0.6804 | 0.3391 | 0.6954 | 0.7618 | 0.2345 | 0.7088 |
| 1.50 | 20 | 0.6933 | 0.3448 | 0.7069 | 0.7862 | 0.2414 | 0.7233 |
| 2.00 | 10 | 0.6760 | 0.3362 | 0.6954 | 0.7518 | 0.2328 | 0.7088 |
| 2.00 | 15 | 0.6804 | 0.3391 | 0.6954 | 0.7618 | 0.2345 | 0.7088 |
| 2.00 | 20 | 0.6933 | 0.3448 | 0.7069 | 0.7862 | 0.2414 | 0.7233 |

在本轮参数里，最好的 Top 5 是 `bm25_weight=1.25, rerank_candidate_k=20`：Recall@5=`0.7862`、Precision@5=`0.2414`、MRR=`0.7233`。与原来的 `1.0/10` 对照相比，三项分别增加 `0.0100/0.0017/0.0005`；Top 3 Recall 只从 `0.6890` 到 `0.6933`。更高的权重 `1.5/2.0` 没有超过 `1.25`，而在候选数只有 10 时，提高 BM25 权重反而使指标下降。用户确认采用 `1.25/20` 作为学习版默认配置。

随后把这两个值接入 `Settings`、主检索服务和 benchmark CLI，并用本地 Cross-Encoder 对 116 个问题重新运行。结果复现了 sweep：Recall@5=`0.7862`、Precision@5=`0.2414`、Precision@returned=`0.2414`、MRR=`0.7233`。逐题报告为 `evaluation-results-hybrid-rerank-bm25-1.25-candidate20.json`。`RERANKER_ENABLED` 仍是独立开关，默认关闭；只有启用它时，候选数 20 才会在 API 主流程中触发模型重排。benchmark 的 `hybrid-rerank` 模式会实际运行 reranker。benchmark 以正向可回答问题为主，且 BM25 词元化仍较简单，结果不代表拒答或其他语料表现。

#### Reranker 不只有一种模型

当前学习版用 `CrossEncoderReranker` 包装了一个模型：`cross-encoder/ms-marco-MiniLM-L-6-v2`。它通过 `RERANKER_MODEL` 配置，代码实际调用 `sentence_transformers.CrossEncoder`，所以可以换成兼容的 Cross-Encoder 模型；换模型后要在同一 benchmark 上重跑，不能只看模型名称或参数规模判断优劣。

除了换模型，rerank 还可以从几个方面优化：扩大或缩小候选数（当前默认 20；从 10 增至 20 会多计算一倍左右的 query-parent 配对，延迟尚未单独测量）；改善送入模型的 query 与 parent 文本，例如确认标题/章节路径是否作为上下文；检查模型输入长度截断是否丢掉关键证据；比较更强模型的 Recall、Precision、MRR 和运行耗时。当前实现已经支持候选数和模型名配置，尚未实现可配置的输入模板、最大长度或模型微调。Reranker 分数是相关性排序分数，不是概率；候选池之外的内容也无法被它找回来。

#### 阈值和 top_k 对照

为了观察“只返回高于相似度阈值的结果”与最终返回数量之间的取舍，固定 `min_score=0.80`，并让最终 `top_k` 从 3 到 8 逐组运行。其他参数保持不变：`child_top_k=20`、`rrf_k=60`、`rerank_candidate_k=10`，检索模式为 `hybrid-rerank`，数据集为 7 篇论文的 116 个问题。

| top_k | Recall@k | Precision@k | Precision@returned | MRR |
|---:|---:|---:|---:|---:|
| 3 | 0.6739 | 0.3333 | 0.3333 | 0.6882 |
| 4 | 0.7163 | 0.2716 | 0.2716 | 0.6925 |
| 5 | 0.7565 | 0.2310 | 0.2310 | 0.7011 |
| 6 | 0.7781 | 0.1983 | 0.1983 | 0.7040 |
| 7 | 0.7893 | 0.1749 | 0.1749 | 0.7065 |
| 8 | 0.8013 | 0.1562 | 0.1562 | 0.7076 |

这组结果说明，`top_k` 越大，系统覆盖到正确 evidence 的机会越高，但同时会带回更多无关 parent。面试项目采用 `top_k=5` 作为默认平衡点；如果更强调上下文精简和结果准确率，可以单次请求设为 `top_k=3` 或 `4`；如果更强调召回覆盖，可以设为 `top_k=6`。当前默认 `min_score=0.80` 只控制 Dense 候选，BM25 候选仍可独立进入 RRF，因此它不是“最终结果分数必须大于 0.80”的硬过滤。结果文件分别为 `evaluation-results-rerank-score080-top3.json` 到 `evaluation-results-rerank-score080-top8.json`。

#### Figure parent 与图注 element 的映射

图片本身没有可用于文本 embedding 的正文，所以 chunker 会把 figure 的图注文字合并到 figure parent 的 `context` 中。例如 Figure 5 的结构化元素是：`element-000065`（图片）关联 `element-000066`（图注）。因此生成的 `element-000065-parent` 仍然只有一个检索结果，但 metadata 会记录：

```json
{
  "source_element_ids": ["element-000065"],
  "context_element_ids": ["element-000065", "element-000066"]
}
```

`source_element_ids` 用来说明 parent 的主要来源，`context_element_ids` 用来说明这个 parent 的文字上下文还包含哪些结构化元素。评测按 parent 计排名和 Precision；判断是否命中 gold evidence 时再检查整个 `context_element_ids` 组。这样 q006 的 gold 图注 `element-000066` 可以由第 2 名的 `element-000065-parent` 命中，同时不会把图片和图注错误地算成两个返回结果。benchmark 仍保存原始 Docling evidence ID，不直接改成 chunk ID。

#### 用 related IDs 把关联图表加入正文上下文

解析器会用 Docling 的 caption 关系连接图表与图注；正文或列表项明确提到 Figure/Table 编号时，若编号唯一对应到解析出的图表，也会把正文和图表互相写入 `related_ids`。过去 chunk 只保留了这些关系 metadata，没有把关联图表内容加入命中正文的上下文；而单独的 Figure parent 还可能在 reranker 最终 Top-k 截断时被排除。

现在检索先照常完成 Dense/BM25、RRF、rerank 和最终 Top-k，再检查每个命中 parent 的 `related_element_ids`。如果它关联到一个 figure parent，就把该图的图注和可用的 VLM 图片描述附加到正文 context 中；同一个图在一组结果内只扩展一次。关联图不作为额外排名结果，因此不会改变 Top-k 名额和原 parent 顺序。返回 metadata 的 `context_element_ids` 会包含实际加入上下文的 Figure 与 caption element，并用 `expanded_related_element_ids` 标明这些扩展来源。VLM 未启用或调用失败时，图注仍会加入，正文检索保持可用。

benchmark runner 在同一排序阶段之后运行相同的关联上下文扩展，再按 `context_element_ids` 评分；所以 Recall@k 衡量最终 parent 上下文覆盖了多少 gold element，Precision@k 仍按命中的 parent 数计算，关联图不另占一名。benchmark 不调用远程 VLM，因此这项评测验证结构化关联和图注上下文覆盖，不验证 VLM 描述是否准确。对 7 篇论文、116 题的同参对照结果为：

| 指标 | 原 parent context | 加入 related figure context |
|---|---:|---:|
| Recall@5 | 0.7862 | 0.8008 |
| Precision@5 | 0.2414 | 0.2466 |
| Precision@returned | 0.2414 | 0.2466 |
| MRR | 0.7233 | 0.7319 |

5 个问题的逐题分数发生变化，其余 111 题不变。新的逐题报告保存在 `evaluation-results-hybrid-rerank-related-context.json`；此前的 baseline 文件保留。指标上升来自相关图表证据现在确实随正文进入上下文，不代表 Dense、BM25 或 reranker 的原始排序本身变好了。

#### 统一模型配置

模型配置集中在 `backend/app/config.py` 的 `Settings` 中。它负责加载 `backend/.env` 和进程环境变量，并进行类型校验；它不负责加载模型或发送请求，`EmbeddingService`、`VisionService` 等服务通过配置获得模型名和 API 参数。

```text
环境变量
    ↓
Settings.from_env()
    ↓
EmbeddingService / VisionService / 后续 Reranker、LLM 服务
```

当前集中管理的配置包括：

```text
EMBEDDING_MODEL       向量模型
RERANKER_ENABLED      是否启用模型重排
RERANKER_MODEL        重排模型
RERANK_CANDIDATE_K    RRF 后交给重排模型的 parent 候选数
BM25_WEIGHT           BM25 排名在 RRF 中的权重（默认 1.25）
FETCH_K               每个检索通道先保留的候选数量
TOP_K                 最终返回的 parent 数量上限
MIN_SCORE             Dense 余弦相似度最低阈值
RRF_K                 RRF 算法参数，不是模型
LLM_BASE_URL          生成模型 API 地址
LLM_MODEL             生成模型 ID
LLM_API_KEY           生成模型密钥
VLM_ENABLED           是否启用图片描述
VLM_BASE_URL          远程视觉模型 API 地址
VLM_MODEL             视觉模型 ID，例如服务商提供的 GPT 视觉模型
VLM_API_KEY           视觉模型密钥
```

例如远程服务商提供 GPT 视觉模型时，只需要配置：

```cmd
set VLM_ENABLED=true
set VLM_BASE_URL=https://服务商域名/v1
set VLM_MODEL=服务商返回的视觉模型ID
set VLM_API_KEY=服务商API_KEY
```

`VLM_MODEL` 可以是 GPT，只要该模型支持图片输入，并且服务商兼容 OpenAI 的多模态 `chat/completions` 请求。本地开发时编辑 `backend/.env`；模板在 `backend/.env.example`。进程环境变量会覆盖 `.env` 中的同名值，因此也可以用 CMD 临时覆盖配置。API Key 不写进 Python 源码，也不提交到 Git。

`Settings.from_env()` 默认读取学习版 backend 目录下的 `.env`；测试可以传入临时 `env_path`，或使用 `load_dotenv_file=False`，这样不会受到本机真实密钥的影响。`.env.example` 默认关闭 VLM，复制模板后必须明确填写服务地址、模型 ID，并把 `VLM_ENABLED` 改为 `true` 才会发起远程请求。检索 API 的 `top_k`、`child_top_k` 和 `min_score` 默认值也来自同一个 `Settings` 实例，避免路由和服务使用两套参数。

#### Figure 图片描述与 VLM

图片本身没有可直接用于文本 embedding 的内容，但 figure parent 的 metadata 会保存 `image_path`。学习版现在由后端直接读取这个路径，把图片编码成 base64，并调用 OpenAI 兼容的 `/chat/completions` 接口生成图片描述；前端不参与这个过程。

```text
检索命中 figure parent
        ↓
读取 image_path
        ↓
后端调用 VLM
        ↓
生成 image_description
        ↓
追加到 parent context
        ↓
交给后续 LLM
```

`backend/app/vlm.py` 负责 VLM 请求、响应解析和按图片修改时间缓存。`backend/app/retrieval_service.py` 在返回 figure parent 时调用它，并把结果放入：

```json
{
  "metadata": {
    "image_path": "...",
    "image_description": "The figure shows ..."
  },
  "context": "Figure: ...\n\nImage description: The figure shows ..."
}
```

VLM 默认关闭；关闭时检索流程仍正常返回，不会读取图片。你使用远程 VLM API 时，启动后端前在 CMD 中填写服务商提供的真实地址、模型 ID 和 API Key：

```cmd
set VLM_ENABLED=true
set VLM_BASE_URL=https://your-provider.example/v1
set VLM_MODEL=provider-model-id
set VLM_API_KEY=your-api-key
set VLM_TIMEOUT_SECONDS=60
```

上面三个 `your-*` 只是占位符，不能原样使用。`VLM_BASE_URL` 必须是服务商的 OpenAI 兼容 API 根地址，`VLM_MODEL` 必须使用服务商实际返回的模型 ID。后端运行在本机还是 Docker，都可以访问远程地址，因此以后容器化时通常不需要修改这三个配置；只需要通过环境变量向容器注入 API Key。

当前版本只会在最终命中的 parent 自身带有 `image_path` 时调用 VLM。正文 parent 的 `related_element_ids` 还不会自动扩展为 figure；后续实现关系扩展时，可以在命中正文后再找到关联图片并补充描述。VLM 调用失败会记录警告并保留原始检索结果，不会让整个检索请求失败。

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
