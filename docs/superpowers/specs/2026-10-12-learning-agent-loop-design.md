# 单任务 LangGraph Agent loop 第一版

用户已确认显式 StateGraph + 模型节点 + ToolNode + 条件边，并授权助手实现后逐段讲解。

- 新增 `/api/agent`，输入 file_id/query，输出 answer/status/tool_calls_used/sources/trace。不修改现有 chat 合约。
- 每次请求创建独立 MessagesState，保存本次 Human/AI/Tool 消息；不读取跨会话历史，不配置 checkpointer。
- START → agent；无 tool_calls → END；有 tool_calls 且预算允许 → tools → agent；预算不足 → stop → END。
- search_paper 只有 query 参数，固定服务器选定的 file_id/PDF/figure 路径，复用 RetrievalService 和 Settings。工具返回 JSON evidence，同时在 ToolMessage artifact 保存来源；引用使用稳定 chunk_id，避免多次检索 S1 冲突。
- 默认最多 3 个工具请求，计数包含无效/未知工具请求；一批请求超预算则整批不执行，返回 tool_limit。模型调用最多 4 次。工具批次可以由 ToolNode 并行执行，但预算在执行前按整批校验。
- 模型保留 AIMessage/tool_calls，不使用 StrOutputParser。解析异常、无效模型输出和 provider 错误安全映射 503；检索失败返回安全错误结果，不暴露路径/密钥。
- 无非空证据时不接受模型事实答案，返回 no_evidence。引用格式/语义真实性仍需后续评测，不宣称已验证。
- 离线脚本化模型验证多轮工具循环、预算、无效参数、未知工具、空证据、失败脱敏及并发任务隔离；API 验证输入、文件存在性与状态映射。
- 真实 provider 是否支持 tools/tool_calls 需由用户本地配置和后续 smoke 确认，本轮不依赖远程 API。
