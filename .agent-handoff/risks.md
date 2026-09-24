# Risks, Blockers, And Unknowns

## Current Blockers

- none

## Current Risks

- `backend/.env` 存在且含配置/凭据（已被 `.gitignore` 忽略）。**不要读取或外传其内容**，改动配置相关代码时参考 `backend/.env.example`。
- `README.md` 含 "Security Notice → API & Authentication / Credentials & Secrets" 一节。改动 API、认证或凭据相关代码前应先读该节。
- 前后端是两个独立子项目（各自依赖与构建命令）。动手前先确认当前活跃的是 `backend/` 还是 `frontend/`，避免改错端。
- 前后端依赖外部服务（Milvus、Postgres、LLM、VLM）。本地未启动这些服务时，相关测试会失败或无法运行——跳过时必须在 `validation.md` 记明原因，不要谎报通过。
- `data/`、`*.pdf`、`*.db`、`*.csv` 被 gitignore，仓库内不存在这些内容的版本历史；排查数据相关问题时不要把"本地缺失"当成代码缺陷。

## Unknowns / Confirmations Needed

- UNKNOWN: handoff 文件是否提交进 git —— 需要用户确认（当前是未跟踪状态）。
- UNKNOWN: 本机是否已具备 Milvus / Postgres 环境以运行完整测试 —— 需要实际跑一次 `make test` 才能确定。
- UNKNOWN: `backend/test/` 中哪些测试需要外部服务、哪些可离线运行 —— 需要逐个查看测试文件或实跑确认。

## Risk Guidelines

- Keep risks concrete.
- Mark uncertainty as `UNKNOWN`.
- Include the source needed to resolve each unknown when possible.
