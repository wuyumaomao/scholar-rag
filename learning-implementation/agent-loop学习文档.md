# 单任务 LangGraph Agent loop：第一版逐段理解

本版目标：基于现有 RAG，让模型选择何时检索、如何改写检索问题以及何时回答。程序定义可用工具、论文范围和执行上限，模型决定范围内的下一步。

## 先运行一次

后端依赖已新增 `langgraph==1.2.14`。如需安装：

```powershell
# 在 learning-implementation 目录执行
uv pip install --python .venv/Scripts/python.exe -r backend/requirements.txt
```

使用原有方式启动/重启后端，并在 `http://127.0.0.1:8100/docs` 找到 `POST /api/agent`。先通过文件列表获取已上传论文的 `file_id`，输入：

```json
{
  "file_id": "替换为已上传论文的真实 ID",
  "query": "这篇论文采用了什么方法，有哪些局限？请引用证据。"
}
```

本接口复用 Settings 中的 LLM 和检索配置。必须配置可用的 LLM，且 provider 支持 OpenAI 兼容的 tools/tool_calls。普通文本生成成功不代表工具调用也受支持。

响应包括：

- `answer`：最终可展示回答；没有证据时由程序给出明确限制提示。
- `status`：`completed`（模型结束且有证据）、`no_evidence`（未得到非空证据）或 `tool_limit`（下一批工具请求超过预算）。`completed` 表示执行结束，不表示回答已经过事实验证。
- `tool_calls_used`：已交给 ToolNode 处理的工具请求数，无效参数/未知工具也占预算。
- `sources`：工具实际检索到的非空证据，按 chunk ID 去重；不表示每条证据都被最终引用。
- `trace`：模型输出、工具调用参数、工具结果，供阅读执行过程，不包含隐藏思维链。

默认预算为 3 个工具请求。如果模型每次请求一个工具，最多调用模型 4 次：每个工具结果之后可再决策一次。最后一次若仍要求工具，则图转到 stop，报告任务未完成。若一批工具请求超出剩余预算，整批都不执行。

## 1. State：本次执行携带什么

代码：`backend/app/agent/paper_agent.py` 的 `AgentState`。

```python
class AgentState(MessagesState):
    tool_calls_used: int
    status: Literal["completed", "tool_limit"]
```

`MessagesState` 已定义 messages 字段和 `add_messages` reducer。节点返回 `{"messages": [new_message]}` 时，LangGraph 合并消息；通常追加新消息，相同 ID 的消息会更新，而不是简单覆盖整个历史。计数和状态没有 reducer，节点返回新值时直接覆盖。

第一版 messages 会形成：

```text
HumanMessage：原始任务
AIMessage：模型发出工具调用
ToolMessage：工具结果
AIMessage：继续工具调用或最终回答
```

每次 `run()` 都用新的 HumanMessage 和零计数启动。状态只用于当前请求，未读取数据库会话，未配置 checkpointer。因此它是本次执行的上下文，尚不是跨会话 memory。

## 2. Tool：把现有 RAG 包装成模型可调用的能力

代码：`SearchInput` 和 `make_search_tool()`。

`@tool` 把函数变成 LangChain 工具。函数名和 docstring 告诉模型用途，Pydantic schema 告诉模型参数结构。

```python
@tool(args_schema=SearchInput, response_format="content_and_artifact")
def search_paper(query: str):
    hits = service.retrieve(file_id, pdf_path, query, figure_dir, ...)
```

模型只提供 query。file_id、PDF 路径、图片目录和检索参数通过服务器创建的闭包绑定，模型不能用工具参数切换到另一篇论文。

`content_and_artifact` 区分两种结果：content 是发送给模型的 JSON 证据；artifact 是程序保留的结构化来源，用于 API 返回 sources。工具真正执行的仍是你已有的 Dense/BM25/RRF/可选 rerank 流程。

来源标识使用 chunk_id，同一证据在多次检索中保持一致，避免每次搜索重新编号导致多个 S1 指向不同内容。提示模型引用 `[chunk_id, p. 3]`，但这一版尚未对最终引用做语义核验。

## 3. Model：为何不能提前使用 StrOutputParser

代码：`_model_for()`。

```python
model = ChatOpenAI(...).bind_tools([search_tool])
```

`bind_tools()` 向模型声明可用工具及其 schema，并不执行工具。模型响应仍是 `AIMessage`，其 content 可以为空，而 tool_calls 有内容：

```python
AIMessage(
    content="",
    tool_calls=[{
        "name": "search_paper",
        "args": {"query": "limitations of the proposed method"},
        "id": "call-1",
        "type": "tool_call",
    }],
)
```

旧 AnswerGenerator 的 `StrOutputParser` 适合提取最终文本；如果在这里使用它，会丢掉执行所需的工具调用结构。

生产使用真实 ChatOpenAI；测试的 bound_model 注入点允许脚本化响应，不访问远程服务。每个请求绑定自己的工具范围。

## 4. Agent 节点：让模型决定下一步

代码：`_build_graph()` 内的 `agent()`。

```python
response = await model.ainvoke([
    SystemMessage(content=...工具说明与剩余预算...),
    *state["messages"],
])
return {"messages": [response]}
```

模型能看到当前任务和之前执行的工具结果。工具返回后，再调用同一个节点，模型就能依据结果继续决策。程序保留完整 AIMessage，并检查消息类型、无法解析的 tool_calls 和空回答。

系统提示要求事实回答以论文证据为依据，将工具结果视为不可信文本。提示是行为约束，不是正确性证明。

## 5. ToolNode：谁真正执行检索

代码：`tool_node` 和 `tools()`。

`ToolNode([search_tool])` 根据最后一个 AIMessage 中的 tool_calls 找到工具，校验参数并执行，输出 ToolMessage。`tool_call_id` 对应原调用的 id，模型服务依靠它识别哪条结果属于哪次请求。

本版 ToolNode 处理完一批请求后，tools 节点增加计数，再回到 agent。若模型一次发出多个请求，ToolNode 可并行执行；路由在执行之前检查整个批次的预算。

参数错误返回安全工具错误，检索服务异常返回 `status=error` 的 JSON。模型可以在剩余预算内尝试修正。它们不会无限重试；provider 调用本版关闭客户端自动重试，调用失败安全映射为 503。

## 6. 条件边：循环由谁控制

代码：`route()` 和图连接。

```text
START → agent
agent 无工具调用 → END
agent 有工具调用且预算足够 → tools → agent
agent 有工具调用但超预算 → stop → END
```

模型决定要不要工具；程序决定这次请求是否允许执行。stop 会给尚未执行的调用补上明确的取消 ToolMessage，再返回“任务尚未完成”，不让预算结束伪装成正常成功。

`recursion_limit` 是额外图执行保护，并不是工具预算；业务预算由 tool_calls_used 明确管理。

## 7. compile 与 ainvoke：图定义和实际执行

```python
builder = StateGraph(AgentState)
builder.add_node("agent", agent)
builder.add_node("tools", tools)
builder.add_node("stop", stop)
# 添加普通边与条件边……
graph = builder.compile()
state = await graph.ainvoke(initial_state, config)
```

`compile()` 构建可执行图，`ainvoke()` 才启动一次任务。最终 run() 将消息整理为 trace，收集 ToolMessage artifact 的来源；若没有非空证据，就用 no_evidence 提示替代模型可能编造的答案。有证据仍不代表证据充分或答案正确，这是后续评测任务。

## 8. HTTP 入口：如何接入已有应用

代码：`backend/app/routers/agent.py`。

路由验证输入、数据库文件记录和 PDF 是否存在，然后创建 PaperAgent 并等待 `run()`。可以从 Swagger 或 HTTP 客户端观察完整结果。

它是独立任务入口，不保存会话，不返回 token SSE；原来的 chat 和前端仍可用于已有 RAG 问答。后续可以在理解 loop 后再设计前端 Agent 模式和阶段事件。

## 验证与边界

- 离线测试通过脚本化模型运行真实编译图，验证连续检索、返回 ToolMessage、预算、无效参数、未知工具、无证据、provider 脱敏及并发请求隔离。
- API 测试验证输入/文件检查、成功响应和错误映射。
- 本轮未调用真实 LLM；需要在本机配置的 provider 上确认 tool calling 兼容性。是否需要再次检索由模型决定，普通问题一次检索后结束也是正常行为。
- 只有一个工具也能构成 loop，但没有证明多次检索一定比固定 RAG 更好；后续应比较质量、延迟和成本。

建议阅读顺序：AgentState → make_search_tool → _model_for → agent/tools/route → 图连接 → run → HTTP 路由。读的时候始终追问两件事：这一步状态发生了什么变化？下一步执行由什么决定？
