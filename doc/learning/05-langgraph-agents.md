# 05. LangGraph 多 Agent：从检索到多步问答

## 5.1 为什么先做单 Agent，再做图

如果“问题 -> Retriever -> LLM 答案”还不稳定，增加多个 Agent 只会让调试更难。多 Agent 的价值不在于让系统看起来复杂，而在于把复杂问题拆成可独立处理的子任务，并保留每一步状态。

ScholarRAG 的 LangGraph 部分建立在已经存在的 Retriever 之上：

```text
Retriever 已回答：从论文里找哪几段证据？
LangGraph 要回答：复杂问题怎样拆、怎样并行、怎样结合会话历史、怎样合成？
```

主要源码：

- `backend/agent/states.py`
- `backend/agent/graph.py`
- `backend/agent/nodes.py`
- `backend/agent/prompts.py`
- `backend/app/routers/chat.py`

## 5.2 先看状态，不要先看图

LangGraph 中节点并不直接调用彼此并传一堆局部变量；节点读取和更新统一状态。因此最先要读 `states.py`。

### 主图状态 `AgentState`

| 字段 | 含义 | 谁主要写入 |
|---|---|---|
| `messages` | 多轮消息历史 | checkpoint、总结、聊天结束写回 |
| `query` | 当前用户原始问题 | chat router |
| `paper_id` | 可选论文范围 | 前端 -> chat router |
| `query_type` | 问题类型 | `classify_query` |
| `summary` | 旧会话压缩摘要 | `summarize_conversation` |
| `sub_queries` | 拆出的搜索问题 | `analyze_query` |
| `sub_answers` | 子 Agent 的局部结果 | 每个 `sub_agent` |
| `citations` | 汇总后的引用 | `prepare_synthesis` |
| `synth_messages` | 最终合成用消息 | `prepare_synthesis` |
| `answer` | 最终答案 | `synthesize` |

### 子图状态 `SubAgentState`

每个子问题独立运行一套更小状态：

```text
query / paper_id / query_type
documents / citations
answer
is_sufficient / retry_queries / retries
needs_vlm
```

这就是“主 Agent 管任务分配，子 Agent 管一个问题的证据和答案”的边界。

## 5.3 Reducer 为什么必要

多个子 Agent 会并行完成，它们都会向同一个主图状态写 `sub_answers`。若没有 reducer，最后一个写入者可能覆盖前面的结果。

`states.py` 使用 `Annotated` 指定合并函数：

```python
sub_answers: Annotated[list[SubAnswer], merge_sub_answers]
citations: Annotated[list[dict], merge_citations]
messages: Annotated[list[AnyMessage], add_messages]
```

### `merge_sub_answers`

按子问题文本去重。同一个 query 再次出现时，用新答案替换旧答案；否则追加。它使得重试或图分支不容易留下重复子答案。

### `merge_citations`

按 `chunk_id` 去重。多个子问题可能检索到同一 parent 文档，最终引用列表不应把它列很多次。

### `add_messages`

LangGraph 提供的消息 reducer 支持追加消息，也能识别 `RemoveMessage`。会话总结时，旧消息不是手工重建列表，而是返回若干 `RemoveMessage(id=...)` 从状态中移除。

## 5.4 主图长什么样

`build_graph()` 建立的主图：

```text
START
  -> summarize
  -> classify
  -> analyze
  -> Send(sub_agent) x N
  -> prepare_synthesis
  -> synthesize
  -> END
```

用角色来理解：

| 节点 | 问的问题 | 输出 |
|---|---|---|
| `summarize` | 旧对话是否太长？ | summary，必要时删除旧 messages |
| `classify` | 用户在问实验、方法、背景还是其他？ | `query_type` |
| `analyze` | 该用哪些检索问题寻找证据？ | `sub_queries` |
| `sub_agent` | 某一子问题的答案是什么？ | 一个 `SubAnswer` |
| `prepare_synthesis` | 多个局部答案如何供最终模型使用？ | synth prompt + citations |
| `synthesize` | 怎样回答原始问题？ | 最终 `answer` |

主图的设计意图是把“控制流”和“领域工作”分开：图决定步骤和并行关系，节点函数决定具体执行逻辑。

## 5.5 多轮会话：`summarize`

当前窗口大小：

```python
WINDOW_SIZE = 6
```

`summarize_conversation()` 的逻辑：

```text
messages <= 6：不做任何 LLM 调用
messages > 6：
  取最后 6 条之前的所有消息
  加上已有 summary
  调用 SUMMARIZER
  写回新 summary
  用 RemoveMessage 删除被总结的旧消息
```

它试图避免所有历史无限增长。注意它按“消息条数”而不是“用户/助手轮次”计算；6 条通常约等于 3 轮完整往返，但异常情况可能不同。

`_build_context_header()` 再将 `summary` 与最新 messages 格式化为：

```text
<conversation_summary>...</conversation_summary>
<recent_conversation>...</recent_conversation>
```

这个 header 会附加到查询分析和最终合成 Prompt，使后续问题知道上下文。

## 5.6 查询分类：为什么要分四类

`classify_query()` 用 `llm.with_structured_output(QueryClassification)` 要求模型返回：

```text
experimental_result | method | background | general
```

它的作用不是决定“回答风格”，而是给下游检索选择章节过滤：

| query type | 章节过滤 |
|---|---|
| `experimental_result` | `experiment` |
| `method` | `method` |
| `background` | `background` |
| `general` | 不过滤 |

若结构化调用失败、模型返回未知类型，代码回退为 `general`，保证系统继续检索。

当前 `classify_query()` 还调用了 `agent.tools.set_query_type()`，但实际 `retrieve()` 读取的是状态中的 `query_type`，而不是 `ContextVar`。`tools.py:paper_retrieval` 目前没有在图中被调用，可以视为从早期 tool-calling 方案遗留的死代码；学习时不应把它误认为当前检索主路径。

## 5.7 查询分解：为什么简单问题也可能有多个 query

`analyze_query()` 使用 `QueryAnalysis` 结构化输出，Prompt 要求：

- 简单问题生成 2～3 个同义/改写 query。
- 复杂多跳问题拆成独立子问题。
- 每个 query 自包含，不依赖代词。
- 原始问题放第一位。

代码还会补一道保险：如果模型返回中没有原始问题，则 `insert(0, query)`。

这样一个问题：

```text
DualPath 如何提升吞吐量，它的内存代价是什么？
```

可能成为：

```text
1. DualPath 如何提升 LLM 推理吞吐量，它的内存代价是什么？
2. DualPath 如何提升 LLM 推理吞吐量？
3. DualPath 的内存开销和权衡是什么？
```

这能增加检索覆盖，但也会多发起 LLM 和检索请求。对于非常短的问题，多个同义查询不一定总是更好，需要观察延迟与重复证据。

## 5.8 `Send` 如何实现子 Agent 并行

图在 `analyze` 后使用条件边：

```python
def dispatch(state: AgentState):
    return [Send("sub_agent", {
        "query": q,
        "query_type": state.get("query_type", "general"),
        "paper_id": state.get("paper_id"),
    }) for q in state["sub_queries"]]
```

每个 `Send` 带着一个独立子状态进入同一个 `sub_agent` 节点。它们不是在 Python for 循环中逐个 `await`，而是 LangGraph 可以调度的并行分支。

```text
analyze
  ├─ Send(query A) -> sub-agent A
  ├─ Send(query B) -> sub-agent B
  └─ Send(query C) -> sub-agent C
                       ↓
                    reducer 合并 sub_answers
                       ↓
                prepare_synthesis
```

并行不意味着外部资源没有限制：同时运行的子问题会同时访问 LLM、Embedding、Milvus 和 CrossEncoder，过多拆分可能让延迟、费用或 API 限流变差。

## 5.9 子 Agent 图

每个子 Agent 图由 `_build_sub_agent_graph()` 构造：

```text
MAX_RETRIES <= 0
START -> retrieve -> generate -> END

MAX_RETRIES > 0
START -> retrieve -> generate -> reflect -> retry? -> prepare_retry -> retrieve
                                             └-> done -> END
```

子图输入被显式初始化：

```python
{
    "query": ...,
    "paper_id": ...,
    "query_type": ...,
    "documents": [],
    "answer": "",
    "citations": [],
    "is_sufficient": False,
    "retry_queries": [],
    "retries": 0,
    "needs_vlm": False,
}
```

初始化清楚地声明子 Agent 的输入和输出，避免它意外依赖主图的所有状态。

### `retrieve` 节点

它读取 query type 和 paper ID，按章节过滤调用 `RetrieverTool.invoke()`。若 reflect 产生多个 `retry_queries`，它使用 `asyncio.gather()` 与 `run_in_executor()` 并发检索所有补充 query，再按 `chunk_id` 去重。

之后将每个 Document 转为：

```text
正文
[Source: Paper: ... | Section: ... | Page: ...]
```

这就是给生成模型的证据上下文。

### `generate` 节点

它将 documents 编号为 `[1]`、`[2]`，通过 `GENERATOR` Prompt 调用 LLM：

```text
Context:
[1] ...
[2] ...

Question: ...
```

Prompt 要求只使用 context、每个事实使用 `[i]` 引用、不足时明确说明。这里的子 Agent 生成使用 `llm.ainvoke()`，不会向浏览器流式输出；浏览器看到的流是最后合成节点产生的。

### `reflect` 节点

它让 LLM 判断当前答案是否覆盖核心意图，返回：

```json
{"is_sufficient": false, "retry_queries": ["缺失信息的具体检索问题"]}
```

若不充分，会走 `prepare_retry` 再检索。`prepare_retry` 将 state 的 `query` 改为第一条补充 query；但 `retrieve` 实际上优先使用整个 `retry_queries` 列表，因而会并发搜全部补充 query。

## 5.10 `MAX_RETRIES` 的精确含义和当前细节

实现中有两个层面：

1. `max_retries <= 0`：`reflect` 和 `prepare_retry` **不加入图**。这比“加入图但跳过”更省一次结构化 LLM 调用。
2. `max_retries > 0`：`reflect` 加入图，`should_retry()` 决定是否回环。

当前代码在 `reflect()` 中先执行：

```python
"retries": retries + 1
```

再由：

```python
state.get("retries", 0) < max_retries
```

决定是否 retry。因此当 `MAX_RETRIES=1` 时，第一次 reflect 后 `retries=1`，条件 `1 < 1` 为 false：反思会运行，但不会进入一次额外检索/生成循环。若产品语义希望“1 表示允许一次重试”，这里需要调整比较时机或条件。这是读源码发现的行为，不应只依据配置注释推断。

## 5.11 最终合成与引用重编号

每个子 Agent 的局部 Prompt 从 `[1]` 开始编号。直接拼接会导致多个 `[1]` 指向不同来源，因此 `prepare_synthesis()` 做了两件事：

1. 收集 `Q: 子问题 / A: 子答案`。
2. 用正则把局部答案中的 `[n]` 加上全局 offset。

```text
子答案 A: ... [1] [2]     offset 0 -> [1] [2]
子答案 B: ... [1]          offset 2 -> [3]
```

它同时将 citations 合并为最终列表，并构造 `SYNTHESIZER` Prompt。`synthesize()` 使用：

```python
async for chunk in llm.astream(synth_messages):
```

这才是聊天接口向前端转发的流。

当前重编号依赖模型确实按 `[数字]` 格式生成引用，且局部 citation 数量与引用序号相匹配。极端情况下它可能误改正文中的方括号数字，或无法检测遗漏引用。更稳健的后续方案是让模型输出结构化 evidence IDs，再由程序渲染引用。

## 5.12 Agent 图如何进入 SSE

`chat.py` 调用：

```python
graph.astream(
    graph_input,
    config={"configurable": {"thread_id": session_id}},
    stream_mode=["updates", "messages"],
)
```

其中：

- `updates` 用于发现 `analyze` 节点的 `sub_queries` 与 `prepare_synthesis` 的 citations。
- `messages` 用于捕获 `langgraph_node == "synthesize"` 的流式 LLM 文本。
- `thread_id` 让同一会话从 PostgreSQL checkpointer 恢复/保存状态。

这样 LangGraph 自己不需要知道 HTTP 或 SSE；它只发图状态和消息流，router 负责把它转换成 Web 协议。

## 5.13 当前性能与可维护性观察

1. `chat.py` 每次请求都会 `_build_graph()`；每个 `sub_agent_node` 又会 `_build_sub_agent_graph(...).compile()`。结果正确，但会有额外编译开销。可以按模型、Retriever、重试配置缓存编译后的图。
2. 查询分析会对简单问题也产生多个改写，可能提高召回，也可能造成重复搜索。可加入复杂度判断或上限。
3. 章节过滤后空结果会回退到无过滤检索，兼顾可用性，但日志应记录回退频率来评估章节分类质量。
4. VLM 路径目前未完成端到端接线，详见第 04、07 章。

## 5.14 本章练习

1. 不看源码，画出主图和子图；再对照 `graph.py` 修正每一条边。
2. 为 `merge_sub_answers` 写三个输入例子：追加、同 query 替换、两个并发子 Agent 返回。
3. 将一个复杂问题拆成三个独立 query，检查每个 query 是否不依赖“它”“前者”等代词。
4. 用 `MAX_RETRIES=0`、`1`、`2` 分别推演 `reflect` 节点是否存在、是否会回环。
5. 设计结构化引用 ID 的 JSON 输出，替代基于正则的 `[n]` 重编号。

## 下一章

下一章转到浏览器：React 如何维护会话、文件和消息状态，以及 SSE 事件怎样更新一条正在生成的回答。
