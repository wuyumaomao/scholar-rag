# Risks, Blockers, And Unknowns

## Current Blockers

- none

## Current Risks

- `backend/.env` 存在（已被 `.gitignore` 忽略），其**内容未经核实**。不要读取或外传；改动配置相关代码时参考 `backend/.env.example`。
- `README.md` 含 "Security Notice → API & Authentication / Credentials & Secrets" 一节。改动 API、认证或凭据相关代码前应先读该节。
- 前后端是两个独立子项目（各自依赖与构建命令）。动手前先确认当前活跃的是 `backend/` 还是 `frontend/`，避免改错端。
- 前后端依赖外部服务（Milvus、Postgres、LLM、VLM；依据 `requirements.txt` 与 `README.md` 推断）。本地未启动这些服务时，相关测试无法运行——跳过时必须在 `validation.md` 记明原因，不要谎报通过。
- `data/`、`*.pdf`、`*.db`、`*.csv` 被 gitignore，仓库内没有这些内容的版本历史。排查数据相关问题时不要把"本地缺失"当成代码缺陷。
- 学习版 `DATABASE_URL` 当前写在 `learning-implementation/backend/app/database.py`，仅用于本地学习；不要把真实生产密码提交到仓库。
- 学习版 `store.py` 每次操作创建一个数据库连接，便于学习连接和 SQL，后续进入生产化阶段应改为连接池。

## Unknowns / Confirmations Needed

- UNKNOWN: 原项目完整 `make test` 是否能在当前环境通过 —— 尚未执行，且与学习版 PostgreSQL 验证分开。
- UNKNOWN: `backend/test/` 中哪些测试需要外部服务、哪些可离线运行 —— 需要查看测试文件或实跑确认。
- UNKNOWN: 是否需要为 Claude Code 生成 `.claude/CLAUDE.md` —— 需要用户决定（当前仅 `--platform codex`）。

## Risk Guidelines

- Keep risks concrete.
- Mark uncertainty as `UNKNOWN`.
- Include the source needed to resolve each unknown when possible.
