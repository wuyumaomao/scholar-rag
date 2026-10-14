# 学习版论文研究编排

用户已确认 Planner → 动态 Researcher → Writer → Reflect，Researcher 状态以单任务为边界，初始上下文由上层提供，执行期间自行积累。本文记录实施范围。

## 主图与子图

- 主图：START → planner → Send(researcher) → writer → reflect；通过或无法继续进入 finalize → END。审核发现表达/覆盖问题时回 writer；缺失证据时生成新的补充任务并派发 researcher。最多一次修正，之后保留审核问题、明确输出不足。
- Researcher：复用 PaperAgent 的 agent ↔ tools / stop；候选答案结束直接 END，不在每个子任务再次审核。无独立会话恢复，不复用主图 thread_id 的历史。
- 旧 PaperAgent 保留用于学习与单任务测试；/api/agent 接入新的 PaperWorkflow。

## 状态与模型上下文

- 主图保留 Human/最终AI会话消息；本轮保存 question、turn_id、tasks、按task_id合并的research_results、answer、sources、review、revision_count、trace。每轮用 Overwrite 清空带reducer的任务结果与trace，其他本轮字段覆盖初始化。
- Planner 输入主图用户对话，输出1–3个独立任务描述与必要背景，服务端生成task_id；拒绝空白、超量或重复任务。
- Researcher 输入独立任务及背景、固定论文范围和分配预算；内部保留单任务消息，返回结论、原文证据、未解决事项、状态、工具消耗与trace。
- Writer 读取原问题、任务结果及原文来源，审核修正时另读review；Reflect读取原问题、最终候选答案与完整本轮证据，输出pass/revise/research/insufficient以及问题、补充查询。
- 最终只把用户可见答案追加到主图messages。checkpoint保存主图任务结果和trace，不声称保存子图内部每一步；未提供中断恢复入口。

## 预算与结束

- 默认本轮共6次工具请求、每任务最多3次、最多3并行任务。每次派发按剩余预算分配不重叠额度，实际消耗从结果汇总；补充检索只能使用剩余额度。初始研究不能耗用未分配额度。
- 最多一次修正：回Writer或启动一批新补充任务；二次审核未通过则返回insufficient，附明确限制。无证据跳过Writer/Reflect模型请求，确定性no_evidence。partial tool_limit记录在子任务中，最终未通过且无剩余研究预算返回tool_limit，否则insufficient。
- Planner/Writer/Reflect使用普通chat请求、本地Pydantic解析，不强制tool_choice，保持Thinking兼容。Researcher继续bind_tools。模型/解析异常沿用安全503，未完成同会话409。

## API与验证

保留file_id/query/thread_id请求，保留answer/status/sources/trace/tool_calls_used/review响应，增加tasks、research_results、revision_count、llm_calls_used。新编排不可继续旧PaperAgent checkpoint，会提示新建会话。测试使用真实LangGraph加脚本化模型验证Send隔离、并行结果合并、跨轮重置/历史、预算、审核修正和结束、错误与HTTP入口。真实provider由用户重启后验收。

不在本次实施context裁剪、Supervisor、长期记忆、数据库checkpointer或恢复接口。上下文裁剪仍按此前规格后续适配各角色。
