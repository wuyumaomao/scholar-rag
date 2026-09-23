# Scholar RAG 学习进度

记录时间：2026-08-15 至 2026-08-17

## 已完成：前端

已阅读 `frontend/src/main.jsx`、`App.jsx`、`api.js` 和全部组件：

- `components/Sidebar.jsx`
- `components/ChatMessages.jsx`
- `components/ChatInput.jsx`
- `components/FileUpload.jsx`
- `components/SettingsPanel.jsx`

### 前端整体链路

```text
main.jsx
-> 挂载 App
-> App 管理页面全局状态
-> 子组件显示数据，并通过回调把用户操作交回 App
-> api.js 与后端 HTTP/SSE 接口通信
-> React 根据状态重新渲染界面
```

### 已理解的 React / JavaScript 概念

- JSX：用接近 HTML 的语法，在 JavaScript 中描述界面。
- `return (...)`：React 组件返回应显示的 JSX 页面结构。
- `useState`：保存会影响界面的状态；调用 `setXxx()` 后 React 根据新状态更新页面。
- `useRef`：保存不应触发重渲染的值或真实 DOM 引用。
  - `cancelRef.current` 保存取消流式请求的函数。
  - `bottomRef.current` 指向聊天区底部元素，用于自动滚动。
- `useEffect`：首次渲染或依赖变化后运行副作用。
- `useCallback`：保持函数引用稳定；本项目中用于 `loadSessions`，避免 Effect 因函数重建而重复触发。
- props：父组件传给子组件的数据或函数，例如 `onSend={handleSend}`。
- 回调函数：将函数交给另一个函数、组件或事件系统，由对方在合适时机调用。
- 箭头函数：`(prev) => ...` 是函数定义；`prev` 是函数参数，由 React 的 `setMessages` 调用回调时传入。
- `map`：将数组中的每一项转换为新的数组项或 JSX，例如 `files.map((f) => ...)`。
- 浏览器事件：`onClick`、`onChange`、`onKeyDown`、`onInput` 等；事件对象 `e` 由 React/浏览器传入。

### App.jsx 的核心状态

```text
sessions   左侧所有会话的概要列表
currentId  当前正在查看/对话的会话 ID
messages   当前会话的完整消息列表
loading    模型是否正在生成
panel      右侧面板：null / upload / settings
```

### handleSend 调用链

```text
用户在 ChatInput 中点击发送或按 Enter
-> ChatInput.handleSubmit()
-> onSend(trimmed)
-> App.handleSend(query)
-> api.streamChat(query, sessionId, 事件回调)
-> fetch POST /api/chat
-> 后端 SSE 持续返回事件
-> api.js 解析为 evt 并调用事件回调
-> handleSend 更新 messages / currentId / loading
-> React 重新渲染 ChatMessages 与 ChatInput
```

`handleSend` 的业务职责：取消旧流、立刻显示用户问题、发送当前问题与会话 ID、接收流式答案、补充 citations、完成后刷新会话列表。

### 流式响应

`api.js` 的 `streamChat()`：

```text
fetch('/api/chat')
-> 取得 response.body.getReader()
-> 循环 reader.read()
-> TextDecoder 将字节转字符串
-> buf 保留不完整 SSE 行
-> 解析 data: { JSON }
-> onEvent(evt) 交回 App.jsx
```

后端事件类型：`session_id`、`answer`、`citations`、`done`、`error`。

`streamChat()` 启动 `fetch` 后不会等待模型回答完成；它立刻返回 `() => ctrl.abort()`，因此 `handleSend` 可以立即执行：

```js
cancelRef.current = cancel
```

下一次发送时：

```js
if (cancelRef.current) cancelRef.current()
```

可中止上一轮请求。

### 组件职责

- `Sidebar`：展示、新建、选择、删除会话。
- `ChatMessages`：遍历 `messages`；`MessageBubble` 依据 `role` 显示用户/助手消息；助手消息以 Markdown 渲染并显示引用。
- `ChatInput`：受控 `textarea`、Enter 发送、Shift+Enter 换行、输入框自动增高。
- `FileUpload`：拖拽/选择 PDF、调用上传 API、展示每个文件处理结果。
- `SettingsPanel`：查看上传文件、删除单个文件、清空向量库。

### 前端构建与部署配置

- `index.css`：通过 `main.jsx` 导入，提供全局样式和 Tailwind 指令。
- `postcss.config.js`：启用 `tailwindcss` 和 `autoprefixer`。
- `tailwind.config.js`：指定扫描 `index.html` 与 `src/**/*.{js,jsx}`，按使用到的 class 生成 CSS。
- `vite.config.js`：启用 React 插件；开发时代理 `/api` 到 `http://localhost:8000`。
- `eslint.config.js`：JavaScript、React、React Hooks 和 React Refresh 的静态检查规则；`npm run lint` 执行。
- `package.json`：声明依赖与 npm scripts。
- `package-lock.json`：锁定精确依赖树，Docker 中的 `npm ci` 按它安装。
- `dependencies`：应用功能需要的库，如 React、图标、Markdown 渲染。
- `devDependencies`：开发/构建工具，如 Vite、Tailwind、ESLint。

### Docker / Nginx

前端 Dockerfile 是多阶段构建：

```text
Node 阶段：npm ci -> npm run build -> dist
Nginx 阶段：复制 dist 与 nginx.conf -> 提供静态网页
```

`nginx.conf`：

```text
location /      提供静态页面；SPA 路由回退到 index.html
location /api/  反向代理到 Docker 服务 backend:8000
```

浏览器请求 `/api/chat` 的部署链路：

```text
浏览器
-> Nginx（宿主机 localhost:5173）
-> Docker 内部 backend:8000
-> FastAPI
```

`proxy_buffering off` 对 SSE 流式输出很重要，避免 Nginx 缓冲回答。

## 已完成：后端基础与路由

### main.py

已阅读 `backend/app/main.py`。

职责：

```text
配置日志
-> 创建 FastAPI app
-> 加入 CORS 中间件
-> 注册 chat / sessions / files / manage 路由
-> 若 frontend/dist 存在，则可提供静态前端文件
-> 直接运行文件时启动 Uvicorn
```

`app = FastAPI(...)` 是后端总对象，记录路由、中间件、启动关闭逻辑。

Docker 实际运行：

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

这表示 Uvicorn 导入 `app.main` 模块并取得其中的 `app` 对象。Uvicorn 持续监听端口；每个请求到来后，FastAPI 根据路由分派到具体处理函数。Docker 启动模式不会执行 `if __name__ == "__main__"` 块。

### routers

- `routers/chat.py`：`POST /api/chat`；创建或复用会话，执行图工作流，并用 SSE 返回事件。
- `routers/sessions.py`：会话列表、历史消息、删除会话。
  - `app.store` 保存会话基础记录。
  - LangGraph checkpointer 保存历史消息和工作流状态。
- `routers/files.py`：上传、列表、删除 PDF。
  - 上传过程：校验 PDF -> 检查大小 -> SHA-256 内容去重 -> 保存原始 PDF -> 解析 -> 转文档/分块 -> 写 Milvus -> 保存文件元数据。

注意：`FileUpload` 上传成功后传入的 `loadSessions()` 从当前后端实现看是冗余刷新。上传接口不会创建或变更会话；更相关的刷新应是文件列表。

## 当前学习：backend/rag

### 完成：models.py

`PaperNode` 是论文解析后的统一语义节点结构。

核心字段：

```text
node_id / paper_id / node_type
text / page_num / order
section_path / bbox
parent_id / related_ids
image_path / metadata
```

`NodeType` 仅允许：`section_header`、`paragraph`、`table`、`figure`、`caption`、`formula`。

### 完成：node_generator.py

它不切分 PDF；它对既有 `PaperNode` 生成更适合检索的文本。

```text
ParagraphGenerator  段落补充章节路径
FigureGenerator     图片补充图注和附近说明
TableGenerator      表格补充表注及行列线性化文本
FormulaGenerator    公式补充章节路径
Factory             按 node_type 选择对应生成器
```

需要区分：

```text
PDF 语义解析：PDF -> PaperNode，由 PDFParser 完成
RAG 文本分块：Document -> parent / child chunks，由 RAGIntegration 完成
```

### 已理解：integration.py 的 PDFParser

`PDFParser` 的职责：

```text
PDF
-> DoclingDocument
-> 过滤页码、页眉、页脚等噪声
-> 按人类阅读顺序排序
-> 每个 Docling item 转为 PaperNode
-> 关联图表与图注、正文图表引用
-> 裁剪图片
-> 可选地用 LLM 分类章节
```

公开入口：

```python
nodes = parser.parse(pdf_path, paper_id)
```

`parse()` 先不开 OCR；若总文字少于 1000 字符或平均每页少于 200 字符，则以 OCR 模式重试。

关键处理段：

```python
raw_items = [item for item, _ in doc.iterate_items()]
filtered_items = self._filter_items(raw_items, page_height)
sorted_items = self._sort_reading_order(filtered_items)

for item in sorted_items:
    node = self._process_item(
        item, paper_id, order, section_stack, top_level_x
    )
    if node:
        nodes.append(node)
        order += 1
```

- `raw_items`：从 DoclingDocument 取出所有项目；第二个返回值未使用。
- `filtered_items`：去掉页码、页眉、页脚、空内容等。
- `sorted_items`：按页、从上到下、同一行从左到右排序，处理双栏 PDF。
- `_process_item()`：将标题、段落、表格、图片、公式等 Docling 项目映射为 `PaperNode`。

节点创建后还会执行：

```python
self._link_captions_to_figures_tables(nodes)
self._link_text_references(nodes)
self._extract_figure_images(pdf_path, doc, nodes)
self._classify_sections(nodes)
```

分别用于匹配图表说明、建立正文和图表关系、裁剪图像并写 `image_path`、可选 LLM 章节分类。

### Docling 学习记录

Docling 是第三方库，项目依赖声明为：

```text
docling>=2.0.0
```

已单独观察 Docling 将 PDF 转成结构化 Markdown 的效果。

概念边界：

```text
Docling：PDF -> DoclingDocument -> Markdown
本项目 PDFParser：DoclingDocument -> PaperNode
RAGIntegration：PaperNode -> LangChain Document -> chunks -> Milvus
```

Docling 常规流程：PDF backend 读取页面文本/几何信息 -> layout 与结构识别 -> 可选 OCR -> 组装结构化 `DoclingDocument`。

### 当前位置：RAGIntegration

已了解 `RAGIntegration` 的总体职责：

```text
PaperNode
-> nodes_to_documents()
-> LangChain Document
-> create_chunks()
-> parent chunks + child chunks
-> store_in_milvus()
-> Milvus
```

三个核心方法：

```text
nodes_to_documents(nodes, content_hash)
将 PaperNode 转为 Document(page_content, metadata)。
原始 Docling item 会从 metadata 中排除，避免写入不可序列化对象。

create_chunks(docs)
每个 Document 都保留为 parent；普通长文本超过 500 字符时，按 500 字符、50 字符重叠切成多个 child。
table、figure、section_header、caption 不切分，保持完整。
child 用 chunk_parent_id 指向其 parent。

store_in_milvus(parents, children)
通过 EmbeddingService 与 MilvusStoreFactory 写入父块和子块。
child 主要用于精确检索；parent 用于在命中后提供较完整上下文。
```

## 下一步建议

1. 继续精读 `RAGIntegration`：先逐行看 `nodes_to_documents()`，再看 `create_chunks()` 的 parent/child 关系。
2. 阅读 `backend/rag/factory.py`：嵌入模型、重排器和 Milvus store 如何创建。
3. 阅读 `backend/rag/retrieval.py`：用户问题如何检索 child、取 parent、重排结果。
4. 阅读 `backend/rag/citation.py`：检索结果如何转为前端 citations。
5. 回到 `backend/agent/graph.py`、`nodes.py`：理解 Agent 如何调用检索与生成。
6. 最后回到 `backend/app/routers/chat.py`：将图工作流输出与 SSE 的 `session_id`、`answer`、`citations`、`done` 事件完整串起来。

