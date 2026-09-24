# Workspace Map

## Repository Structure

- `.`: repository root.
- `AGENT_HANDOFF.md`: handoff index and recovery route.
- `.agent-handoff/`: durable handoff state files.
- `backend/`: FastAPI 后端。子包：`app/`（应用与路由，入口 `app/main.py`）、`agent/`、`rag/`（检索与生成）、`db/`、`eval/`（评估）、`test/`（测试）、`data/`、`uploads/`、`log/`。
- `frontend/`: Vite + React 前端（`src/`、`public/`，含 `nginx.conf` 与 `Dockerfile`）。
- `doc/`: 项目文档与图片（`project-overview.md`、`project-review-2026-09-17.md`、`learning-progress-2026-08-17.md`、`learning/`、`architecture.png`、`scholsr_rag.png`）。
- `docs/`: 另有 `docs/superpowers/`。
- `learning-implementation/`: 学习实现目录。
- `data/`、`resource/`、`tmp/`: 数据与临时文件（`data/` 已被 `.gitignore` 忽略）。
- `Makefile`: 统一命令入口。`docker-compose.yml`: 容器编排。

## Main Entry Points

- 后端开发服务：`make backend`（= `cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`）
- 后端 + 前端一体启动：`make start`（先 `make build` 构建前端，再以 `uvicorn app.main:app --port 8000` 同时服务）
- 后端应用入口文件：`backend/app/main.py`
- 后端配置：`backend/config.py`；环境变量经 `backend/.env`（模板见 `backend/.env.example`）
- 前端开发服务器：`make frontend`（= `cd frontend && npm run dev`）
- 前端生产构建：`make build`（= `cd frontend && npm run build`）
- 依赖安装：`make install`（后端 `pip install -r requirements.txt`；前端 `npm install`）
- 容器：`make docker-up` / `make docker-down`

## Test Entry Points

- 全部后端测试：`make test`（= `cd backend && python -m pytest test/ -v`）
- 测试文件位于 `backend/test/`：`test_agent.py`、`test_paper_filter.py`、`test_pdf_parser.py`、`test_pdf_parsing.py`、`test_retrieval.py`、`test_vlm.py`、`test_vlm_integration.py`
- 前端 lint：`make lint`（= `cd frontend && npm run lint`）

## Docs And Specs

- `README.md`：主文档（What is ScholarRAG / Architecture / Project Structure / Quick Start / 配置项 / API Reference / Evaluation / Tech Stack / Security Notice）
- `doc/project-overview.md`：项目概览
- `doc/project-review-2026-09-17.md`：项目评审记录
- `doc/learning-progress-2026-08-17.md`、`doc/learning/`：学习进度
- `paper.docling.md`：论文经 docling 转出的 Markdown

## Durable Project Context

- 项目定位：ScholarRAG —— 面向学术论文的 RAG（检索增强生成）系统，包含后端 API 与前端界面。
- 后端技术栈（`backend/requirements.txt`）：FastAPI + Uvicorn + SSE（`sse-starlette`）；LangChain / LangGraph（`langgraph-checkpoint-postgres`）；向量库 `pymilvus`（经 `langchain-milvus`）；嵌入 `sentence-transformers` / `langchain-huggingface`；PDF 解析 `docling`。
- 前端技术栈（`frontend/package.json`）：React 18 + Vite + Tailwind；`react-markdown`、`lucide-react`。
- 状态存储：Postgres 用于 checkpointer 与 session store；Milvus 用于向量检索。
- 评估：检索指标 Recall@k / Precision@k / MRR / MAP；生成指标使用 RAGAS。

## Project Conventions

- 常见操作用 `Makefile` 目标执行，不手敲长命令。
- 后端依赖记录在 `backend/requirements.txt`；前端依赖记录在 `frontend/package.json`。
- 配置与密钥放 `backend/.env`（模板 `backend/.env.example`）；`.env` 已被 `.gitignore` 忽略。
- `.gitignore` 已忽略：Python 构建产物、`data/`、`*.pdf`、`*.db`、`*.csv`、`node_modules/`、`frontend/dist/`、`.vscode/`。
- 前端代码风格由 `frontend/eslint.config.js` 约束（`npm run lint`）。
