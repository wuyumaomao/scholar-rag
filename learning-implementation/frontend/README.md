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

接口封装在 `src/api.js`，页面状态和事件在 `src/App.jsx`，聊天消息渲染在 `Message` 组件中，样式在 `src/styles.css`。自动化 API 测试使用 Node 内置测试运行器：

```cmd
npm test
npm run build
```

如果 Vite 提示 8100 连接失败，先确认 FastAPI 后端已经启动，并可访问 `http://127.0.0.1:8100/api/health`。
