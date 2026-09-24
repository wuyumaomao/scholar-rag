# 04. 检索系统：从问题到可引用证据

## 4.1 检索层要解决的问题

PDF 摄取结束后，Milvus 中有很多 child chunk 和 parent chunk。用户提问时，系统不能把所有内容都发给 LLM：成本高、上下文会超限，也会降低答案聚焦度。

检索层要完成：

```text
用户问题
  -> 可选查询改写
  -> Dense + BM25 混合召回
  -> 可选 metadata 过滤
  -> CrossEncoder 重排
  -> child 命中回溯 parent
  -> 去重、截断、缓存
  -> 带 metadata 的 Document 列表
  -> CitationExtractor
```

核心文件：

- `backend/rag/retrieval.py`
- `backend/rag/factory.py`
- `backend/rag/cache.py`
- `backend/rag/citation.py`
- `backend/rag/incremental.py`

## 4.2 两种搜索为什么要并存

### Dense 向量检索

Embedding 模型将问题和文档映射成向量。语义相近的内容，即使不使用同样的词，也可能距离接近。

例子：

```text
问题：模型有哪些创新？
文档：我们提出了三个关键设计：...
```

词面不完全一样，但语义接近，Dense 检索擅长这类情况。

### BM25 稀疏检索

BM25 更关注词项匹配和词频权重，擅长专有名词、公式符号、模型名称、数据集名称和精确指标。

例子：

```text
问题：PredNet 在 KITTI 上的 MSE 是多少？
文档：KITTI ... MSE = 0.024
```

Dense 可能抓住“性能结果”，BM25 则更容易抓住 `PredNet`、`KITTI`、`MSE`。

ScholarRAG 使用的是两者融合，而不是二选一。

## 4.3 从 `Retriever` 的构造开始看

```python
retriever = Retriever(
    embedding_model=Config.EMBEDDING_MODEL,
    reranker_model=Config.RERANKER_MODEL,
    milvus_uri=Config.MILVUS_URI,
    collection_name=Config.COLLECTION_NAME,
    enable_cache=Config.ENABLE_CACHE,
)
```

构造函数做三件事：

1. `EmbeddingService.get_embeddings()`：按模型名缓存 Hugging Face Embedding 实例。
2. `RerankerService.get_reranker()`：按模型名缓存 CrossEncoder 实例。
3. `MilvusStoreFactory.create_store()`：分别构造 children 与 parents 的 Milvus store。

```text
Retriever
  ├── embeddings
  ├── reranker
  ├── _child_store  -> papers_children
  ├── _parent_store -> papers_parents
  └── cache
```

`EmbeddingService` 和 `RerankerService` 的单例缓存是性能选择：避免每次请求重新下载/加载模型。

## 4.4 Milvus store 为什么有 Dense 和 Sparse 字段

`factory.py:MilvusStoreFactory.create_store()` 使用：

```python
bm25 = BM25BuiltInFunction(
    input_field_names="text",
    output_field_names="sparse",
)

Milvus(
    embeddings,
    builtin_function=bm25,
    vector_field=["dense", "sparse"],
    collection_name=f"{collection_name}_{suffix}",
)
```

可以把一条 child 文档理解为：

```text
text
 ├── dense  : 由 Embedding 模型计算的语义向量
 └── sparse : 由 Milvus 内置 BM25 计算的稀疏表示
```

这两个字段属于同一条文档，因此 metadata 过滤、chunk ID、页码、论文 ID 都能同时作用于两种召回。

### `_register_orm_connection()` 是什么

factory 中有一段将 `MilvusClient` 的底层 handler 注册给 PyMilvus ORM 的兼容代码。这是因为 `langchain-milvus` 的部分路径与 PyMilvus ORM 对连接注册的预期不同。它访问了私有属性（例如 `_using`、`_handler`），因此依赖库升级时需要回归测试；不要把它当成通用 Milvus 教程代码照搬到任意项目。

## 4.5 `Retriever.retrieve()` 完整执行顺序

方法签名：

```python
def retrieve(
    query: str,
    k: int = 5,
    use_hyde: bool = False,
    rerank: bool = True,
    expand_parent: bool = True,
    rrf_k: int = 60,
    fetch_k: int = 20,
    node_type_filter: Optional[list[str]] = None,
    section_type_filter: Optional[list[str]] = None,
    paper_id: Optional[str] = None,
) -> list[Document]
```

逐步展开：

```text
1. 重置 collection cache，避免 collection 被清空后仍引用旧对象
2. 若 children collection 不存在，直接返回 []
3. 构造 cache scope，尝试语义缓存命中
4. 可选 HyDE 改写问题
5. 构造 Milvus filter expr
6. children 上执行 Dense + BM25 + RRF
7. 对候选做 CrossEncoder 重排
8. 由 child 的 chunk_parent_id 回溯 parent
9. 根据 chunk_id 去重，取前 k 个
10. 写入缓存并返回
```

你应该将 `fetch_k` 和 `k` 区分开：

```text
fetch_k：给重排器看的候选数量
k：最终交给 Agent/LLM 的文档数量
```

当前常量：

```python
RERANK_FETCH_MULTIPLIER = 2
DEDUP_FETCH_MULTIPLIER = 2
```

因此 rerank 开启时，会先混合召回 `fetch_k * 2` 个 child，再重排并保留 `fetch_k`；parent 回溯前再取约 `k * 2` 个候选用于去重。

## 4.6 RRF 是怎样融合 Dense 与 BM25 的

项目在 `_hybrid_search()` 中创建 Milvus 的 `FunctionType.RERANK`：

```python
Function(
    name="rrf_reranker",
    function_type=FunctionType.RERANK,
    input_field_names=["dense", "sparse"],
    params={"k": rrf_k},
)
```

RRF 的思想是只相信排名，不直接比较两条通道的原始分数。常见形式是：

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

假设一个文档在 Dense 中第 2 名、BM25 中第 5 名，它会从两条通道都获得分数；只在一条通道靠前的文档也有机会保留。这样避免了“余弦相似度”和“BM25 分数”量纲不同导致的简单加权问题。

### 空 sparse 查询的回退

部分短问题或符号组合可能让 sparse 查询无效。代码捕获错误信息中 `nq [0] is invalid` 的情况，记录 warning 后改走 `_dense_search()`。这是一个“不要因为 BM25 失败就让整个检索失败”的降级策略。

## 4.7 Metadata 过滤怎样工作

`_build_expr()` 将可选条件拼成 Milvus expression：

```python
paper_id == "Transformer" && (node_type == "table") && (section_type == "experiment")
```

支持三类过滤：

| 参数 | 示例 | 用途 |
|---|---|---|
| `paper_id` | `Transformer` | 只搜用户当前选择的一篇论文 |
| `node_type_filter` | `['table', 'figure']` | 只看表格/图片等特定内容 |
| `section_type_filter` | `['method']` | 只看方法章节 |

`paper_id` 在拼接前转义反斜杠和双引号。`backend/test/test_paper_filter.py` 用带引号的 ID 覆盖了这一点。

### 过滤过窄时会发生什么

Agent 的 `retrieve` 节点根据 query type 加 `section_type_filter`。如果带过滤没有结果，会再调用一次 Retriever，但不带章节过滤：

```text
method 问题
  -> 先搜索 section_type=method
  -> 空结果时搜索所有 section
```

这体现了“定向检索优先，召回为空时宁可放宽”的实用策略。

## 4.8 CrossEncoder 重排与 parent 回溯

### CrossEncoder 为什么放在召回后

`_rerank()` 对 `(query, doc.page_content)` 成对评分：

```python
pairs = [(query, doc.page_content) for doc in docs]
scores = self.reranker.predict(pairs)
```

CrossEncoder 通常比独立 embedding 更准确，因为问题和文档能在同一模型内交叉注意力比较；但它慢，所以只对有限候选做，而不是扫全库。

### 为什么先检索 child，再交付 parent

child 很短，适合回答“哪一段最像问题”；parent 更完整，适合让 LLM 理解上下文。`_expand_to_parents()` 收集 child metadata 中的 `chunk_parent_id`，然后到 parent store 查对应文档。

```text
child 命中："... accuracy reached 86.4% ..."
parent 返回：该段完整实验描述、设置和比较语境
```

当前实现以 `similarity_search("dummy", expr='chunk_id == "..."')` 获取 parent，这是为复用现有 vector store API 的工程写法。若未来优化，可改为按唯一 `chunk_id` 的直接查询，减少不必要的向量搜索语义。

## 4.9 检索缓存不是简单字典

`RetrievalCache` 使用问题 embedding 的余弦相似度，而不是 exact string：

```text
新问题 -> embedding
       -> 与缓存问题 embedding 比较
       -> 最大余弦 >= 0.95 时命中
```

它是 LRU：命中时移到末尾；超过容量时删除最久未使用项。它还用 `RLock` 保护多线程访问，因为 Agent 的多个子查询会通过 executor 并发调用 Retriever。

### 为什么 cache scope 很重要

缓存 key 包含：

```python
repr((paper_id, tuple(node_type_filter or []), tuple(section_type_filter or [])))
```

因此“PredNet 是什么？”在论文 A 和论文 B 中不会互相复用结果；只查表格的请求也不会错误复用普通段落检索结果。

### 当前代码的一个细节

`Config` 定义了 `CACHE_MAX_SIZE`，但 `Retriever` 当前创建缓存时只调用 `RetrievalCache(self.embeddings)`，没有把该配置传入。因此运行中的容量仍由 `RetrievalCache` 默认值 1000 决定。这是一个可以作为练习修复的小配置接线问题。

## 4.10 CitationExtractor 做了什么

检索返回的是 LangChain `Document`。`CitationExtractor` 抽取面向用户展示的少量字段：

```python
{
    "paper_id": meta.get("paper_id", ""),
    "section": meta.get("section_path", ""),
    "page": meta.get("page_num", ""),
    "chunk_id": meta.get("chunk_id", ""),
    "node_type": meta.get("node_type", ""),
}
```

它再格式化成：

```text
Paper: Transformer | Section: 3 Method | Page: 4
```

在 Agent 中，文档正文会被拼为：

```text
原文
[Source: Paper: ... | Section: ... | Page: ...]
```

最终前端获得的 citations 列表也来自这里。

## 4.11 当前 VLM 路径的真实状态

这部分非常值得如实理解，因为它说明“代码有类”与“功能可运行”不同。

当前至少存在三层限制：

1. `app/dependencies.py` 没有创建 `VisionService`。
2. `chat.py:_build_graph()` 没有向 `build_graph()` 传入 `vision_service`。
3. `CitationExtractor.extract_all()` 返回的是简化 citation，不包含原始 `Document.metadata.image_path`；但 `agent/nodes.py` 的 VLM 判断从 citation 的 `metadata.image_path` 读取图片路径，因此当前 `has_figure` 通常为 false。

所以即使把 `VLM_ENABLED=true`，仅当前代码也不会可靠地把检索到的图片送给 VLM。后续改造应明确传递包含 `image_path` 的结构化检索证据，避免在 citation 展示对象上承担内部数据流职责。

## 4.12 参数怎么调才有意义

| 现象 | 可先尝试 | 代价 |
|---|---|---|
| 找不到相关段落 | 增大 `FETCH_K`、检查 embedding 模型、放宽 filter | 更慢，可能带来噪声 |
| 返回文档相关但排序差 | 保持更大候选并启用/调整 reranker | CrossEncoder 延迟增加 |
| 答案缺上下文 | 开启 parent expansion、略增 `TOP_K` | Prompt 变长 |
| 关键词/数值容易漏 | 检查 BM25 是否正常、保持 RRF | 需要 Milvus 支持 sparse 功能 |
| 不同论文串内容 | 确认 `paper_id` 已从前端传到 Retriever | 过滤过窄可能空召回 |
| 重复问题仍慢 | 启用 cache，确认 scope 设计正确 | 相似度阈值太低会误命中 |

不要同时修改所有参数。每次只变一项，使用固定问题集比较 Recall、延迟与人工相关性。

## 4.13 本章练习

1. 用 `test/test_paper_filter.py` 理解 `paper_id` 过滤和缓存隔离的测试意图。
2. 在纸上计算一个两通道、三个文档的 RRF 排名，理解为什么不能直接相加原始分数。
3. 关闭 `rerank` 与 `expand_parent`，比较同一问题的结果，分别说明它们带来的变化。
4. 为 `CACHE_MAX_SIZE` 设计一个失败测试：配置为 2 后插入 3 个问题，应淘汰最早未使用项。
5. 将引用对象与内部“检索证据对象”分开设计，写出后者至少应包含的字段。

## 下一章

下一章进入 Agent：Retriever 已经能返回证据，但复杂问题还需要会话记忆、分类、查询拆分、并行子任务和最终答案合成。
