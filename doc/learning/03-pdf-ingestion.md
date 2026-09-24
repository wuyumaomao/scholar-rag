# 03. PDF 摄取：从上传文件到 Milvus 文档

## 3.1 这一章要解决的问题

用户上传的 PDF 是二进制文件，LLM 和向量数据库不能直接“理解”它。摄取模块的任务是建立稳定的数据转换：

```text
PDF bytes
  -> 原始 PDF 文件
  -> Docling 文档项
  -> PaperNode
  -> LangChain Document + metadata
  -> parent chunks + child chunks
  -> Milvus parents / children collections
```

这一链路输出的不是最终回答，而是以后所有检索和引用都要依赖的知识库。因此应该先单独验证它，再调 Agent。

主要源码：

- `backend/app/routers/files.py`
- `backend/rag/models.py`
- `backend/rag/integration.py`
- `backend/rag/node_generator.py`
- `backend/rag/incremental.py`

## 3.2 第一步：接收并验证上传

入口是：

```python
@router.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
```

前端用 `FormData` 将一个或多个文件放在名为 `files` 的字段中，FastAPI 将其解析为 `UploadFile` 列表。当前实现对每个文件顺序处理：

```text
文件名是否存在且以 .pdf 结尾？
  否 -> 返回 status=error
  是 -> 读取全部字节
       -> 是否超过 MAX_UPLOAD_SIZE_MB？
          是 -> 返回 status=error
          否 -> 计算 SHA-256
```

### 为什么既有 `file_id` 又有 `paper_id`

```python
file_id = str(uuid.uuid4())
paper_id = Path(f.filename).stem
save_path = upload_dir / f"{file_id}.pdf"
```

| 字段 | 含义 | 适合做什么 |
|---|---|---|
| `file_id` | 某一次上传实例的 UUID | 文件表主键、文件磁盘名、删除 API 路径 |
| `paper_id` | 当前由原文件名去扩展名得到 | Milvus metadata、按论文检索过滤、裁图目录 |
| `content_hash` | 原始字节的 SHA-256 | 判断内容是否重复 |

`paper_id` 不是绝对唯一 ID。两份不同目录但同名的论文会产生相同 stem，未来生产化时应使用不可冲突的内部 ID 或将用户可见标题和内部 ID 分离。

### 为什么用内容哈希去重，而不是文件名

`IncrementalUpdater.has_content_hash()` 会查询 child collection 的 `content_hash` metadata。这样同一份论文即使换了文件名，也不会重复解析和入库；同名但内容不同的 PDF 则仍然可以上传。

这个判断依赖 Milvus 可用。若 collection 不存在、查询失败或索引尚未建立，当前函数返回 `None`，上传流程会继续尝试处理文件。

## 3.3 第二步：写入原始文件并处理失败

通过验证后，代码使用 `aiofiles` 异步写入：

```python
async with aiofiles.open(save_path, "wb") as out:
    await out.write(content)
```

之后才开始昂贵的解析和入库。如果后续抛异常，异常处理至少会执行：

```python
save_path.unlink(missing_ok=True)
```

这避免了“数据库没有记录，但 uploads 目录残留 PDF”的一类脏数据。

但是要如实理解当前事务边界：Milvus 的 parents 和 children 是分两次写入的，PostgreSQL 又在最后写入。若中途发生网络或进程故障，仍可能出现部分向量已写入但文件记录不存在的状态。学习版通常可接受，生产环境可用 job 状态表、幂等 ID、补偿删除或异步队列改进。

## 3.4 第三步：`PDFParser` 的输出模型

`backend/rag/models.py` 定义了整个摄取层的核心数据结构：

```python
@dataclass
class PaperNode:
    node_id: str
    paper_id: str
    node_type: NodeType
    text: str
    page_num: int
    order: int
    section_path: list[str]
    bbox: Optional[tuple[float, float, float, float]]
    parent_id: Optional[str]
    related_ids: list[str]
    image_path: Optional[str]
    metadata: dict[str, Any]
```

`NodeType` 目前只允许六种：

```text
section_header | paragraph | table | figure | caption | formula
```

这很关键：PDF 的原始布局对象很杂，后续检索系统不应该直接依赖 Docling 的具体类名。`PaperNode` 是项目自己的稳定中间表示。以后换解析器时，只要仍能生成相同字段，检索层的改动就小得多。

## 3.5 PDF 解析的工作顺序

`PDFParser.parse(pdf_path, paper_id)` 的主要流程：

```text
第一次 parse（OCR 关闭）
  -> 计算总文本字数和页数
  -> 若文本少于 1000 字符，或平均每页少于 200 字符
       -> 第二次 parse（OCR 开启）
  -> 返回 PaperNode 列表
```

为什么先关闭 OCR：普通数字 PDF 本身已有文字层，OCR 更慢且可能引入识别误差。只有文本明显不足、可能是扫描件时才回退到 OCR。

`_parse_with_ocr()` 内部更具体：

```text
Docling DocumentConverter.convert()
  -> doc.iterate_items() 收集原始项
  -> _filter_items() 清除页码、页眉、页脚和空项
  -> _sort_reading_order() 按页和 bbox 重排
  -> _process_item() 生成每一个 PaperNode
  -> 关联图注/表注
  -> 关联正文中的 Figure N / Table N 引用
  -> PyMuPDF 裁出图片
  -> 通过文本 LLM 给章节分类
```

## 3.6 为什么阅读顺序是一个核心问题

论文常有双栏布局。仅按解析器返回顺序拼接文本，可能得到“左栏第一段 -> 右栏第一段 -> 左栏第二段”的错乱上下文。

当前 `_sort_reading_order()` 的做法是：

1. 先按页码分组。
2. 对每个 item 取得 bbox `(left, top, right, bottom)`。
3. 根据内容块平均高度估计同一行的垂直容忍度。
4. 相近的 y 坐标归成一行。
5. 行按从上到下排序，行内按 x 坐标从左到右排序。

```text
Page
  row 1: 左标题 -> 右标题
  row 2: 左段落 -> 右段落
  row 3: 左段落 -> 右段落
```

这是一个启发式算法，未必适合所有多栏、跨页、浮动图表或复杂公式论文，但比直接读取顺序更可控。优化阅读顺序时要准备多种真实论文做回归验证。

## 3.7 节点类型如何生成检索文本

`NodeContentGeneratorFactory` 根据节点类型选择不同生成器。它的目标是将原始内容改写为更适合检索的文本，而不是向用户展示原始排版。

| 节点 | 生成策略 | 为什么 |
|---|---|---|
| `section_header` | `Section: 标题` | 让标题本身可检索 |
| `paragraph` | 加 `Section: 路径` 与 `Paragraph:` | 检索到段落时保留章节语境 |
| `caption` | `Caption: ...` | 图注可独立被搜索 |
| `table` | 图表标题 + 线性化表格 | 避免二维表格结构丢失 |
| `figure` | 图注和相关描述 | 图片本身不等于文字，先依赖图注 |
| `formula` | 加章节路径的公式文本 | 保留公式属于哪个方法部分 |

表格线性化的形式类似：

```text
Row 1: Model=Base, Accuracy=82.1, Params=10M
Row 2: Model=Ours, Accuracy=86.4, Params=12M
```

这样 BM25 和 embedding 都能更容易把“准确率是多少”关联到表格内容。

## 3.8 图注、正文引用和图片裁剪

### 图注关联

`_link_captions_to_figures_tables()` 在同一页寻找带有 `Figure` 或 `Table` 标识且 bbox 距离足够近的 caption，再更新图/表节点的文本。它是一种几何邻近规则，不是完美的版面理解。

### 正文引用关联

`_link_text_references()` 查找段落或公式中的 `Figure 3`、`Table 2` 等模式，将双方 `node_id` 写入 `related_ids`。当前检索流程没有直接利用此关系图，但它为将来扩展“命中段落时顺带取相关图表”留下了数据。

### 图片裁剪

`_extract_figure_images()` 用 PyMuPDF 打开原 PDF，按 figure node 的 bbox 裁出 PNG：

```text
Docling 坐标：原点在左下
PyMuPDF 坐标：原点在左上

fitz_y = page_height - docling_y
```

图片以 2x 矩阵渲染并保存为：

```text
data/figures/{paper_id}/page{页码}_order{顺序}.png
```

这一层为 VLM 图表理解准备了本地图片路径。但“裁出了图片”不等于当前聊天已经调用 VLM；二者是两件事。

## 3.9 章节分类如何帮助后续检索

`_classify_sections()` 会把章节标题交给文本 LLM 的结构化输出，归为：

```text
method | experiment | background | conclusion
```

并把结果写入 header 与其后节点的 `metadata["section_type"]`。后续 Agent 将问题分类为 `experimental_result`、`method`、`background` 或 `general`，Retriever 就可以优先检索相应 section type。

这里需要理解两层分类的区别：

| 分类对象 | 例子 | 用途 |
|---|---|---|
| 文档章节 | “Experiments” -> `experiment` | 给向量检索加 metadata 过滤 |
| 用户问题 | “实验结果如何？” -> `experimental_result` | 决定使用哪种章节过滤 |

若 LLM 章节分类失败，代码捕获异常，节点通常保持默认 `other`。此时系统仍可做无过滤检索，但定向检索能力下降。

## 3.10 `PaperNode` 如何变成 LangChain `Document`

`RAGIntegration.nodes_to_documents()` 取每个非空 node，构建：

```python
Document(
    page_content=node.text,
    metadata={
        "node_id": ...,
        "paper_id": ...,
        "node_type": ...,
        "page_num": ...,
        "section_path": ...,
        "section_type": ...,
        "content_hash": ...,
        "bbox": ...,
        "image_path": ...,
    }
)
```

`page_content` 是用于搜索和给 LLM 的文本；`metadata` 不一定参与 embedding，但用于过滤、引用、父子关联、删除和 VLM 图片定位。可以把它们理解为：

```text
page_content = “这段内容说了什么”
metadata     = “这段内容从哪来、属于谁、怎么管理”
```

## 3.11 父子分块为什么存在

`create_chunks()` 为每个 Document 建立：

- 一个 **parent**：完整的语义节点，`chunk_id` 是 UUID。
- 一个或多个 **child**：用于精确匹配，带 `chunk_parent_id` 指向 parent。

普通长文本按：

```text
chunk_size = 500 字符
chunk_overlap = 50 字符
```

切分；但表格、图片、章节标题和图注不切分：

```python
no_split_types = {"table", "figure", "section_header", "caption"}
```

原因：

```text
child：短，主题集中，易被搜索命中
parent：长，语境完整，适合交给生成模型
```

这是“检索精度”和“生成上下文完整性”的分离。第 04 章会解释检索命中 child 后如何回溯 parent。

## 3.12 写入 Milvus

`store_in_milvus(parents, children)` 分别创建两套 store 并执行 `add_documents()`：

```text
{COLLECTION_NAME}_children
{COLLECTION_NAME}_parents
```

`MilvusStoreFactory.create_store()` 为每套 collection 配置 Dense 向量字段和 Milvus 内置 BM25 sparse 字段。实际 embedding 由 `EmbeddingService` 单例提供。

上传成功后，`files` 表记录：

```text
file_id / filename / paper_id / size_bytes / page_count / chunk_count
```

前端上传面板显示的 `chunk_count` 是 child 数量，不是 PaperNode 数量。

## 3.13 一份 PDF 的数据追踪示例

假设上传 `Transformer.pdf`：

```text
Transformer.pdf
  -> file_id = 0f...a2
  -> paper_id = Transformer
  -> content_hash = 64 位 SHA-256
  -> PaperNode #21
       type = paragraph
       page = 4
       section_path = ["3 Method"]
       text = "Section: 3 Method ..."
  -> Document
       metadata.paper_id = "Transformer"
       metadata.section_type = "method"
  -> parent chunk_id = p-uuid
  -> child chunk_id = p-uuid_child_0, p-uuid_child_1
  -> Milvus papers_children / papers_parents
  -> PostgreSQL files 一行记录
```

之后当用户勾选这篇论文，`paper_id="Transformer"` 会沿聊天状态传到 Retriever，作为 Milvus filter。

## 3.14 如何单独验证摄取层

项目包含一个更适合人工检查的脚本：

```powershell
cd backend
python test/test_pdf_parsing.py path/to/paper.pdf --preview-count 20 --output parse-report.json
```

它会打印节点数量、页数、各类型计数、前若干节点，并可导出 JSON。先用它验证解析质量，再上传进完整系统，定位问题会容易得多。

## 3.15 本章练习

1. 选一篇双栏论文，用解析脚本观察阅读顺序是否合理；找出一个可能被错误排序的地方。
2. 为 `PaperNode` 补充一个你认为有用的 metadata 字段，并说明它会在哪个后续模块被使用。
3. 解释为什么 table 不应简单按 500 字符切分。
4. 假设一个上传在 parent 写入成功、child 写入失败时中断，设计一个可恢复的状态机。
5. 追踪某一条 `image_path` 从 PDF 解析到未来 VLM 调用所经过的字段。

## 下一章

下一章把 attention 从“如何入库”转向“如何找回来”：Dense、BM25、RRF、重排、父块回溯、缓存和引用如何组成一条可调的检索管线。
