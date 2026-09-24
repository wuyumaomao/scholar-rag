# 06. React 前端与 SSE：把 Agent 过程显示给用户

## 6.1 前端在整个系统中的边界

前端不负责解析 PDF、运行 Embedding、访问 Milvus 或调用 LLM。它做三件事：

1. 收集用户动作：上传文件、输入问题、选择会话和论文范围。
2. 调用 backend API。
3. 将普通 JSON 和 SSE 事件转换为界面状态。

```text
React state  <->  frontend/src/api.js  <->  /api/*  <->  FastAPI
```

源码入口：

- `frontend/src/main.jsx`
- `frontend/src/App.jsx`
- `frontend/src/api.js`
- `frontend/src/components/Sidebar.jsx`
- `frontend/src/components/ChatMessages.jsx`
- `frontend/src/components/ChatInput.jsx`
- `frontend/src/components/FileUpload.jsx`
- `frontend/src/components/SettingsPanel.jsx`

## 6.2 从 `main.jsx` 到 `App`

`main.jsx` 是 React 的启动点，负责把根组件挂载到 `index.html` 的 root 节点，并引入全局 CSS。真正的页面状态集中在 `App.jsx`：

```javascript
const [sessions, setSessions] = useState([]);
const [files, setFiles] = useState([]);
const [paperId, setPaperId] = useState('');
const [currentId, setCurrentId] = useState(null);
const [messages, setMessages] = useState([]);
const [loading, setLoading] = useState(false);
const [panel, setPanel] = useState(null);
```

可以把 `App` 看作一个小型 UI orchestrator：它不渲染所有细节，而是持有跨组件共享状态，并通过 props 将行为交给子组件。

## 6.3 组件职责

| 组件 | 只负责什么 | 不应该负责什么 |
|---|---|---|
| `Sidebar` | 会话列表、新建、删除、选择 | 读取数据库或解析 checkpoint |
| `ChatMessages` | 显示用户/助手气泡、Markdown、引用折叠 | 发起聊天请求 |
| `ChatInput` | 输入框、自适应高度、Enter 发送 | 管理 SSE 或会话 ID |
| `FileUpload` | 拖放/选择 PDF、显示处理结果 | 直接操作 Milvus |
| `SettingsPanel` | 文件列表、删除文件、清空库 | 决定向量删除细节 |
| `App` | 组合页面、持有状态、响应 API 事件 | 解析 PDF 或生成答案 |

这种分层让你可以替换 UI 而不改 RAG，也可以替换 backend 而不让每个组件都知道数据库结构。

## 6.4 普通 JSON API 封装

`frontend/src/api.js` 用原生 `fetch` 封装：

```javascript
fetchSessions()
fetchHistory(sessionId)
deleteSession(sessionId)
uploadFiles(files)
fetchFiles()
deleteFile(fileId)
clearCollection()
healthCheck()
```

所有地址都基于：

```javascript
const BASE = '/api';
```

这样开发环境由 Vite 代理 `/api`，生产环境由 Nginx 代理 `/api`，组件不需要感知 backend 的真实 host。

当前这些函数大多直接 `return res.json()`，没有统一检查 `res.ok`。这对学习项目简单，但生产化时应统一处理 HTTP 错误、超时和错误 JSON，避免后端 500 被当成普通数据继续渲染。

## 6.5 SSE 是什么以及本项目为什么使用它

普通 `fetch` 请求通常等后端完整返回一个 JSON；问答模型可能需要数秒或更久。SSE（Server-Sent Events）允许服务器在一个 HTTP 响应中持续发送事件，浏览器可以边收边显示。

当前协议不是浏览器原生 `EventSource`，因为原生 EventSource 主要支持 GET，而聊天要发送 POST body。`api.js:streamChat()` 使用：

```javascript
fetch('/api/chat', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({query, session_id: sessionId, paper_id: paperId || null}),
})
```

然后手动读取：

```javascript
const reader = res.body.getReader();
const decoder = new TextDecoder();
```

## 6.6 手写 SSE 解析器逐步做了什么

网络 chunk 不一定刚好按换行分割，一个事件可能跨多个读取结果。因此代码维护 `buf`：

```text
每次 reader.read()
  -> decoder.decode(value)
  -> 拼到 buf
  -> 按 '\n' 分行
  -> 最后一段不完整内容留在 buf
  -> 只处理以 'data:' 开头的完整行
  -> JSON.parse(raw)
  -> onEvent(evt)
```

这就是流式协议解析中的“增量 buffer”模式。不能简单地对每个 `value` 直接 `JSON.parse`，因为 TCP/HTTP 分块边界和业务事件边界没有关系。

## 6.7 前后端事件契约

后端 `chat.py` 发出的事件与前端 `App.jsx` 的 `switch` 一一对应：

| 事件 | 后端何时发 | 前端动作 |
|---|---|---|
| `session_id` | 流开始 | 保存当前会话 ID |
| `status=analyzing` | 图开始运行 | 可显示分析状态 |
| `sub_queries` | `analyze` 节点完成 | 当前 UI 暂未单独展示，可扩展 |
| `status=searching` | 有子问题后 | 可显示检索状态 |
| `answer` | `synthesize` 每个 chunk | 创建/更新未完成 assistant 消息 |
| `citations` | 答案完成后 | 给最后一条 assistant 消息附加引用并标记完成 |
| `done` | checkpoint 和标题更新后 | 结束 loading、刷新会话列表 |
| `error` | 后端异常或 fetch 异常 | 显示错误消息并结束 loading |

### 为什么 answer 可以不断替换最后一条消息

后端每次发送的是累计的 `answer_buf`，例如：

```text
第 1 次："该方法"
第 2 次："该方法通过"
第 3 次："该方法通过分解查询"
```

前端发现最后一条 assistant 消息 `finalized=false`，就用新内容替换它；如果还没有 assistant 消息，则创建一条。这样不会为每个 token 追加一条气泡。

## 6.8 一次发送消息的前端状态流

`App.handleSend(query)` 的步骤：

```text
1. 取消上一次仍在进行的请求（若有）
2. 立即把 user 消息加入 messages
3. setLoading(true)
4. 调用 streamChat(query, currentId, paperId, callback)
5. 收到 session_id -> 更新 currentId
6. 收到 answer -> 更新临时 assistant 消息
7. 收到 citations -> 完成 assistant 消息
8. 收到 done -> setLoading(false)，刷新会话列表
9. 收到 error -> 显示错误并结束 loading
```

`cancelRef` 保存取消函数；下一次发送前调用它，让 `AbortController` 中止旧请求。这避免用户快速连续发送时两个流同时改写同一组消息状态。

## 6.9 会话切换为什么需要两次状态更新

点击侧边栏会话时：

1. 先设置 `currentId`，让 UI 立即高亮。
2. 调用 `fetchHistory(id)`。
3. 将后端消息转为前端统一格式，并补充 `citations` 和 `finalized: true`。

新建会话则只清空当前 UI 状态，不会立即写数据库；真正的 session 记录在下一次 `POST /api/chat` 时由后端创建。这是“懒创建”策略。

## 6.10 文件上传与论文范围选择

上传成功后 `FileUpload` 调用父组件的 `onUploaded`；`App.handleFilesChanged()` 同时刷新文件和会话列表，并重新计算 `paperId`：

```text
没有文件 -> All papers
只有一篇 -> 自动选中该 paper_id
多篇 -> 用户从 select 选择
已选论文被删除 -> 清空 paperId
```

发送请求时：

```javascript
body: JSON.stringify({
  query,
  session_id: sessionId,
  paper_id: paperId || null,
})
```

这条字段会穿过 `chat.py -> graph_input -> AgentState -> Send -> SubAgentState -> Retriever`，最终成为 Milvus 的 `paper_id` filter。它是最近增加的跨层功能，阅读时适合用 `rg "paper_id"` 全链路追踪。

## 6.11 Nginx 与 SSE 的关键配置

生产容器中的 `frontend/nginx.conf`：

```nginx
location /api/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_read_timeout 600s;
    proxy_buffering off;
    proxy_cache off;
}
```

`proxy_buffering off` 很重要：如果 Nginx 将后端数据缓冲到足够多才转发，用户就看不到实时 token。`proxy_read_timeout 600s` 则避免长论文解析或长答案在默认短超时下被断开。

## 6.12 当前前端的工程观察

1. `streamChat()` 没有检查 `res.ok` 或 `res.body` 是否为空，网络错误处理可以更健壮。
2. `uploadFiles(files, onProgress)` 接收了 `onProgress` 参数，但当前实现使用 fetch，没有真正报告上传进度。
3. `sub_queries` 和 `status` 事件已被后端发送，但当前 UI 没有展示详细检索过程；这是可作为练习的可观测性增强点。
4. React key 使用数组索引显示消息，对当前简单 UI 可用；若支持消息编辑、重试或插入事件，最好使用稳定 message ID。
5. 前端 CSS 使用 Tailwind utility class，组件逻辑比样式更值得先读。

## 6.13 本章练习

1. 手写一个最小 SSE 服务，每 500ms 发送一条 `data: {"type":"answer"...}`，再用当前解析器消费。
2. 在 UI 中展示 `status` 和 `sub_queries`，并说明它们来自哪个 LangGraph 节点。
3. 给 `api.js` 增加统一的 `requestJson()`，对非 2xx 响应抛出包含状态码的异常。
4. 追踪一次“只搜索某篇论文”的 `paper_id`，从 `<select>` 一直画到 `_build_expr()`。

## 下一章

最后一章把运行、测试、评测和改进放在一起：哪些检查能证明每个里程碑完成，VLM 配置为什么不等于 VLM 已接通，以及如何按文件顺序继续学习。
