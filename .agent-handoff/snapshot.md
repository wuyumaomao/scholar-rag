# Handoff Snapshot

## Current State

- Last updated: 2026-09-24
- Workspace root: `G:\scholar-rag`
- Active branch: `codex/learning-from-zero`
- Current objective: 以代码实践从零重建 ScholarRAG；当前学习实现已从内存会话迁移到 PostgreSQL。
- Current status: ready —— FastAPI 健康检查、聊天、会话 CRUD、消息历史和 PostgreSQL 持久化已完成并验证。
- Immediate next actions:
  - 继续 `doc/learning/03-pdf-ingestion.md`，先在学习版实现最小 PDF 上传与元数据记录。
  - 保持学习版代码在 `learning-implementation/`，原项目 `backend/`、`frontend/` 只作参考。
  - 新会话开始时按 `AGENT_HANDOFF.md` 的 Recovery Reading Order 恢复上下文，并先阅读相关学习版源码。
- Active files:
  - `learning-implementation/docker-compose.yml`：学习版 PostgreSQL，宿主机端口 `55432`。
  - `learning-implementation/db/init.sql`：`sessions`、`messages` 表、外键和索引。
  - `learning-implementation/backend/app/database.py`：`psycopg` 连接。
  - `learning-implementation/backend/app/store.py`：PostgreSQL 会话和消息 CRUD。
  - `learning-implementation/backend/app/routers/chat.py`、`sessions.py`：HTTP 路由。
  - `learning-implementation/rag学习文档.md`：持续维护的学习笔记。
- Blockers: none
- Open questions:
  - PDF 学习阶段使用哪一个最小解析库，需在开始第 03 章时根据现有依赖和学习目标确定。
  - 远程分支推送状态需在网络可用时确认；本地学习提交已存在。

## Version Control

- 最近学习实现提交：`f6628c9 feat: persist learning sessions in postgres`。
- 当前分支 `codex/learning-from-zero`；本地学习提交比 `origin` 超前，之前推送曾因 GitHub 网络不可达失败。
- handoff 文件本次有更新，提交前应检查并单独提交或与当前学习任务一起提交。
- 可以用 `git diff .agent-handoff/` 审计接力状态是否同步。

## Recovery Summary

- 用 `AGENT_HANDOFF.md` 作为索引，按其中的 Recovery Reading Order 读取。
- 仓库结构、入口命令、技术栈见 `.agent-handoff/workspace.md`。
- 本文件只放当前状态，不要把它当成源码的替代品。
