# ScholarRAG 学习文档设计

## 目标

为 ScholarRAG 建立一套从零开始的中文学习材料。读者不需要先理解当前目录结构，而是沿着系统依赖关系，从最小后端、数据存储、PDF 摄取、检索、单 Agent 问答，逐步走到多 Agent、前端流式交互、Docker 部署和评测。

## 读者与范围

- 读者：了解基础 Python、JavaScript、HTTP 和数据库概念，但第一次系统阅读 Agentic RAG 项目的人。
- 范围：解释当前仓库的真实实现、模块边界、运行时数据流、实现先后关系和可执行练习。
- 不做的事情：不修改业务代码，不把 README 中尚未接通的能力写成已经可用，不替用户建立云端模型服务。

## 教学原则

1. 按依赖关系排序，而不是按文件夹字母顺序排序。
2. 每章同时给出“从零实现顺序”和“当前源码入口”。前者用于学习重建，后者用于阅读现有项目。
3. 每章必须回答四个问题：输入是什么、处理在哪里发生、输出是什么、下一模块为什么能接上。
4. 对当前代码中的限制明确标记，例如 VLM 配置存在但没有在应用生命周期中传入 Agent 图、测试依赖未必安装、工作区包含未提交改动。
5. 每章末尾提供验证方式和练习，形成可回退的学习里程碑。

## 学习路线

```text
问题定义
  -> 最小 FastAPI 后端
  -> PostgreSQL 会话/文件元数据
  -> PDF 结构化解析
  -> PaperNode -> Document -> 父子分块
  -> Milvus 混合索引
  -> 最小检索
  -> RRF + 重排 + 父块回溯 + 缓存 + 引用
  -> 单 Agent 问答
  -> LangGraph 主图/子图/并行子 Agent
  -> SSE 流式输出
  -> React 界面
  -> Docker Compose
  -> 评测、VLM、性能和安全改进
```

## 文件产出

公开学习文档放在 `doc/learning/`：

- `README.md`：导航和建议阅读方式
- `00-roadmap-and-architecture.md`：总览、依赖图和里程碑
- `01-environment-and-startup.md`：本地环境、Docker、配置和启动
- `02-backend-and-api.md`：FastAPI 骨架、生命周期、路由和持久化
- `03-pdf-ingestion.md`：PDF 摄取、结构节点、分块和入库
- `04-retrieval.md`：混合检索、过滤、缓存、重排和引用
- `05-langgraph-agents.md`：状态、主图、子图、并行和反思
- `06-frontend-and-sse.md`：React、SSE 协议和交互状态
- `07-deployment-evaluation.md`：部署、测试、评测、VLM 和改进
- `08-reading-order-and-exercises.md`：逐文件阅读顺序和阶段练习

## 当前实现边界

- 后端使用 `ChatOpenAI` 访问 OpenAI-compatible 文本模型端点。
- PDF 解析使用 Docling，图像裁剪使用 PyMuPDF，向量数据库使用 Milvus，状态和元数据使用 PostgreSQL。
- 当前代码提供 `VisionService` 和 VLM 配置，但 `app/dependencies.py` 尚未创建并注入 VLM 实例；因此文档会把 VLM 作为“设计好的后续能力”讲解，而不是假设已经在聊天链路中生效。
- `MAX_RETRIES` 的配置示例和 `config.py` 默认值存在差异，文档会单独提醒读者以实际 `.env` 和运行日志为准。
- 现有工作区包含用户未提交改动和实验文件；学习文档不清理或覆盖这些文件。

## 验收标准

- 新读者可以只看 `README.md` 和第 00 章理解全局。
- 读完第 01、02 章可以解释服务如何启动、请求如何进入后端。
- 读完第 03、04 章可以画出 PDF 从上传到 Milvus 再到检索结果的完整数据流。
- 读完第 05、06 章可以解释一次聊天请求如何经过 LangGraph 并通过 SSE 到达 React。
- 读完第 07、08 章可以独立启动、定位常见故障，并知道下一步该改什么。
