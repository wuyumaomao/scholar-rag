# 学习版前端

这是学习版 RAG 的 React + Vite 前端。页面只负责收集用户操作、调用后端 API 和显示结果；PDF 解析、检索、回答生成仍由 FastAPI 后端完成。

## 本地启动

先在一个 CMD 窗口启动学习版后端（端口 8100），再开另一个 CMD 窗口：

```cmd
cd /d G:\scholar-rag\learning-implementation\frontend
npm install
npm run dev
```

浏览器打开 Vite 输出的地址，默认是 `http://127.0.0.1:5174`。Vite 会把浏览器发往 `/api` 的请求转给 `http://127.0.0.1:8100`。

## 请求流程

```text
选择 PDF
  -> POST /api/files/upload（multipart 字段名 file）
  -> 后端保存文件、解析文档、建立 Milvus 索引
  -> GET /api/files 刷新可选论文

输入问题
  -> POST /api/chat/stream（file_id、query、可选 session_id）
  -> 后端检索并通过 SSE 逐段发送 LLM 回答
  -> 前端边接收边显示，完成后读取 session_id
```

`POST /api/chat` 仍保留，适合用 curl 一次查看完整 JSON `{answer, session_id}`。网页使用 `fetch` 读取 SSE，因为聊天请求需要 POST JSON 请求体，浏览器原生 `EventSource` 不能直接携带它。

接口封装在 `src/api.js`，页面状态和事件在 `src/App.jsx`，助手 Markdown 与引用卡片在 `src/SourceMessage.jsx`，样式在 `src/styles.css`。自动化 API 测试使用 Node 内置测试运行器：

```cmd
npm test
npm run build
```

如果 Vite 提示 8100 连接失败，先确认 FastAPI 后端已经启动，并可访问 `http://127.0.0.1:8100/api/health`。

## 点击引用展开来源

聊天 SSE 在回答前发送 `sources` 事件：`data: {"sources": [...]}`；随后仍发送 `token` / `done` / `error`。普通 `/api/chat` 也返回 `sources` 数组。每条来源包含 `source_id`、`file_id`、`filename`、`chunk_id`、`page_nums`、`section_path`、`text`，编号与模型提示词共用同一套规则。

回答中的 `[S1]`、`[S1, p. 3]`、`[S1, S2]` 等有效标记可点击，展开论文名、PDF 物理页码、章节和检索证据文本。代码块、行内代码和现有 Markdown 链接保持原样；未匹配到来源的引用保持普通文本。来源文本按纯文本显示，不执行 HTML。卡片展示实际交给模型的 context，可能包含章节前缀、关联图注或 VLM 描述，不是 PDF 版面的逐字复刻，也不代表引用正确性已验证。

来源快照保存在 PostgreSQL `messages.sources` JSONB 字段中，所以历史会话也能展开。旧消息没有保存来源，显示“暂无可展开的来源”，不重新检索猜测旧引用。已有数据库在启动新版后端前执行一次（幂等，不删除历史）：

```cmd
cd /d G:\scholar-rag\learning-implementation\backend
..\.venv\Scripts\python.exe scripts\migrate_message_sources.py
```

新数据库由 `db/init.sql` 自动创建字段。此功能接入的是普通聊天 `/api/chat/stream`，Agent 前端接入和 PDF 跳页另行实现。
