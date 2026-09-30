# 学习版 PDF 结构化解析结果实施计划

> 状态：实现与验证完成（2026-09-30）。本文记录学习版结构化数据模型和实现范围。

## 目标

把学习版 Docling 解析结果从“页码到纯文本”的形式，演进为保留 PDF 文档元素及其关系的结构化结果。这样后续可以按需生成纯正文、保留图表与图注供展示或检索，并在进一步学习时连接分块流程。

本阶段只负责定义并产生结构化解析结果，不接上传 API，不做 chunking、embedding、向量入库，也不提取图片裁剪文件。实现时继续使用学习版现有论文验证 Docling 的真实输出。

## 当前实现与问题

- `learning-implementation/backend/app/pdf_parser.py` 中的 `PdfParseResult` 目前只有 `page_count` 和 `pages: list[str]`。
- `parse_pdf()` 遍历 `document.iterate_items()`，按 provenance 页码收集文本，最后压成逐页字符串。因此正文、图片、图注等会混在同一串文本里；图片 Markdown fallback 还可能让图注重复。
- 图内纯数字已按现有 bbox 规则过滤：同页、1–4 位纯数字，且 bbox 落在图片范围或距边缘不超过 4 PDF 点。此规则继续保留，不扩展成全局数字过滤。
- 现有原项目 `PaperNode` 可供参考，但它还承担 RAG 节点和分块前内容生成等职责；学习版本阶段只建模 Docling 解析输出，不直接复制原项目处理逻辑。

## 建议的数据结构

沿用并扩展解析结果模型，避免同时维护两套“逐页文本”和“结构化结果”作为正式输出：

```python
@dataclass(frozen=True)
class ParsedPdf:
    page_count: int
    elements: list[ParsedElement]

@dataclass(frozen=True)
class ParsedElement:
    element_id: str
    element_type: str
    docling_label: str | None
    docling_type: str
    text: str
    page_num: int
    order: int
    bbox: tuple[float, float, float, float] | None
    provenance: list[ParsedProvenance]
    section_path: list[str]
    related_ids: list[str]

@dataclass(frozen=True)
class ParsedProvenance:
    page_num: int
    bbox: tuple[float, float, float, float] | None
```

这是接口草图，不要求逐字照抄。实现前应结合实际 Docling 对象确认字段和可空性。真实论文检查已确认一个 `TextItem` 可以同时包含第 2、3 页的 provenance；因此模型除了方便调用的首个 `page_num`/`bbox`，还应使用 `provenance` 列表保留所有页码及各自 bbox，不能将原生跨页元素拆开或丢失后续页面来源。`docling_type` 用于保存原始 Python 类名，支持未知 Docling label 的排查。

| 字段 | 含义与约定 |
| --- | --- |
| `element_id` | 本次解析结果内的唯一 ID，用来让关系字段引用元素。可由原始遍历序号生成，例如 `element-000042`；它不代表元素的语义，也不承诺跨 Docling 版本永久稳定。 |
| `element_type` | 学习版统一类型，例如 `section_header`、`paragraph`、`list_item`、`table`、`figure`、`caption`、`formula`、`unknown`。 |
| `docling_label` | 保留 Docling 的原始 label（若存在），以便调试和以后调整映射；它与学习版 `element_type` 分开。 |
| `text` | 元素自身的文本。图片没有可靠文本时允许为空；图注文本存放在独立 caption 元素，不拼进图片正文。 |
| `page_num` | Docling provenance 提供的 1 起始页码。没有页码的元素在当前结果中跳过，或在实现时明确采取其他处理，不能默认为第 1 页。 |
| `order` | `document.iterate_items()` 给出元素的原始遍历序号。过滤元素后不重排剩余序号；它记录 Docling 的顺序，不宣称是重新校正后的绝对正确阅读顺序。 |
| `bbox` | 从 Docling provenance 保留 `(l, t, r, b)`；没有 bbox 时为 `None`。本阶段不依据 bbox 重排阅读顺序。 |
| `provenance` | 保留元素的全部页面来源，每项保存 1 起始页码和该页 bbox；跨页文字仍是一个元素，但可定位到各页。 |
| `section_path` | 当前元素所在的标题层级路径，例如 `['3 Method', '3.2 Training']`。根据 Docling section header 的层级维护标题栈。 |
| `related_ids` | 指向同一解析结果内相关元素的 ID，当前只用于明确的图/图注关联及可识别的正文图表引用。 |

`ParsedPdf` 不必保存重复的逐页正文。需要纯正文时由后续的小函数从 `elements` 派生，避免两份内容不同步。

## 已确认的设计决策

1. **保留元素类型。** 正文、章节标题、图片、图注、表格和公式各自独立，不在解析阶段压成一个正文字符串。
2. **保留图注元素。** 图注仍是一个可单独查看的元素，并通过关系字段与对应图片/表格连接；图片自身不重复包含整段图注文本。
3. **沿用 Docling 顺序。** 原始遍历序号写入 `order`。用户检查论文输出后认为现有顺序大体可靠，因此学习版不照搬原项目按 bbox 重新排序的经验规则。
4. **保留多层章节上下文。** `section_path` 用标题祖先构成路径，供后续块继承上下文。
5. **暂不实现 `parent_id`。** 当前结果是平铺元素列表，章节归属由 `section_path` 表达已够用；额外的父子图会增加维护成本。若将来需要真实树结构再单独设计。
6. **保留已有图内数字过滤。** 过滤掉的元素不会导致剩余元素重新编号，`order` 仍能反映原始遍历位置。
7. **正文纯文本视图跳过图片和图注。** 图片和图注仍保留在结构化结果中，供其他消费者按需使用。

## 尚待实现时确认的细节

- **ListItem 类型：** 推荐映射成独立 `list_item`，因为当前学习目标是看清 Docling 输出；原项目把它映射为 `paragraph` 是面向自身 RAG 处理的简化，不必照搬。首次实现时用样例核对列表是否因此影响正文抽取，再决定是否保留。
- **正文提及 Figure/Table 的关系：** 可通过明确的编号模式（如 `Figure 2`、`Fig. 2`、`Table 1`）关联到相应图表或 caption。只关联能唯一识别的目标；不把任意包含“figure/table”的文字都当作引用。若编号或目标不清楚则不连边。
- **ID 的生成与引用映射：** 先遍历并为候选元素分配 ID，再建立 caption/ref 关系；禁止为登记关系而重复解析或全文搜索图片说明。优先使用 Docling 的原生引用（如 `PictureItem.captions` 指向的 `TextItem`），文本编号匹配是另一种独立关系来源。
- **表格 caption：** 原生关系若可用则复用；没有原生关系时，本阶段可以仅保留独立元素，后续再以实测决定是否增加 bbox 邻近启发式。

## 关系语义

`related_ids` 是“有关联”的通用引用，并不表示包含、章节从属或阅读顺序。第一阶段应只建立可解释的关系：

- 图片/图表 ↔ Docling 原生引用的图注元素。建议双向记录，方便从图片找图注，也能从图注反查图片。
- 正文段落 ↔ 通过明确图表编号识别出的目标。建议双向记录，并确保同一 ID 不重复。

章节从属由 `section_path` 表达，不塞入 `related_ids`。当前不通过 `parent_id` 构造节点树。过滤后留下的 `order` 空档不是关系，也不应压缩掉。

## 阅读正文的派生规则

添加一个纯正文派生函数，例如 `extract_body_text(parsed_pdf)`：

1. 按 `order` 处理元素。
2. 只纳入正文类类型（初始建议 `paragraph`、`list_item`、`section_header`、`formula`；是否纳入公式由调用方或明确参数控制）。
3. 跳过 `figure`、`caption`、`table`，避免图片和图注打断正文或重复进入正文。
4. 保留各元素边界再连接输出；不要因为有图片/图注就擅自合并跨越它们的两个 Docling 正文元素。Docling 原生文本被拆成两段时，本阶段忠实保留这种边界。

“正文”是消费者的视图，不是解析器丢弃其他结构后的唯一结果。

## 实施步骤

### 1. 固化 Docling 映射与测试样本

- [x] 从当前论文前三页的本地 Docling 报告中挑选标题、正文、列表、图片、caption、表格/公式代表项；如果前三页没有某类型，用现有其他 PDF 或合成 Docling fake 补充。
- [x] 明确每种真实 item 的 `type`、`label`、`text`、`prov`、bbox、层级和 caption 引用属性名。
- [x] 将边界测试放进 `learning-implementation/backend/tests/test_pdf_parser.py`，不把本地诊断脚本或论文中间结果加入 Git。

### 2. 先定义模型和类型映射

- [x] 用测试定义 `ParsedPdf`、`ParsedElement` 的构造、空值和序列化/比较行为。
- [x] 新增一个小而明确的 Docling item → `element_type` 映射；未知类型保留为 `unknown` 并记录原始 Docling 类型，不能静默丢弃。
- [x] 确认 `ListItem` 初始映射为独立 `list_item`，以论文结果评估。

### 3. 将 `parse_pdf()` 改为保留结构元素

- [x] 一次遍历 Docling items，记录原始索引作为 `order`，提取页码、bbox、label 和文本，并完整保留多页 provenance。
- [x] 继续应用现有 `is_text_inside_picture()` 数字过滤；忽略元素不进入 `elements`，但不改变其他元素的 `order`。
- [x] 不对 `PictureItem` 调用会把 caption 再导出的 Markdown fallback；caption 作为独立 item 保存，避免重复。
- [x] 维护章节标题栈并为后续元素复制 `section_path`；确认不同 header level 会正确截断较低层标题。
- [x] 用两阶段构建：先创建所有元素及 ID，再解析互相关系，避免前向引用找不到目标。
- [x] 更新模块 docstring、返回类型和调用处；纯正文由结构化元素派生。

### 4. 建立相关元素关系

- [x] 读取 Docling 的 caption 引用（如 `PictureItem.captions`），将 Docling self-ref 映射到本次解析生成的 `element_id`。
- [x] 图片与独立 caption 双向写入 `related_ids`；无 caption 或引用失效时保留图片，不失败。
- [x] 给明确的 Figure/Fig./Table 编号建立正文引用边；处理重复匹配、缺目标和重复边。
- [x] 用测试覆盖关系双向性、同一元素多次提及、引用目标缺失及多图同编号的歧义处理。

### 5. 增加正文派生和结构化回归测试

- [x] 实现并测试正文派生函数，确保图/图注不会进入输出，且元素顺序遵循原始 `order`。
- [x] 验证解析结果保留页数、空白页信息（可由 `page_count` 表示）、同页顺序、bbox、标题路径及图注唯一性。
- [x] 验证图内短数字仍按旧规则过滤，框外年份和包含数字的正常段落仍保留。
- [x] 验证未知 Docling 类型不会导致整份 PDF 解析失败或静默消失。

### 6. 用原论文核对真实结果

- [x] 重新解析 `learning-implementation/1710.11216v3.pdf`，检查第 2 页句子、图 1、图注和刻度的元素顺序及关系。
- [x] 核对第 3 页 “Although the synthetic colon...” 等未被图文打断的段落仍按 Docling 输出保留。
- [x] 检查由正文派生的视图不包含图注，也没有因过滤元素而重排；查看完整元素列表确认 caption 没有重复。
- [x] 将数据结构字段、Docling 顺序与关系语义、运行和验证方法写入 `learning-implementation/rag学习文档.md`。

## 验收标准

- `parse_pdf()` 返回一个有 `page_count` 和按 Docling 原顺序排列的结构化元素集合的结果。
- 可区分标题、正文、列表、图片、图注、表格、公式和未知元素；字段缺失时按约定保留 `None`/空文本或标记未知，不崩溃。
- 每个元素有本次解析内唯一 ID、原始顺序、页码；有数据时保留 bbox 和多层 `section_path`。
- 图注单独存在且不因 PictureItem Markdown fallback 重复；Docling 原生图注引用可转换成 `related_ids`。
- 正文图表引用只在目标明确时建立，不把章节父子关系误用为 `related_ids` 或 `parent_id`。
- 纯正文可从结构化结果派生，排除图片和图注；完整结构仍保留它们。
- 现有图内短数字过滤行为不回退；解析器仍不做 bbox 阅读顺序重排。
- 单元测试通过，真实论文第 2、3 页人工核对通过；相关学习笔记同步更新。

## 验证命令（Windows CMD）

在 `learning-implementation\backend` 目录执行：

```cmd
..\.venv\Scripts\python.exe -m pytest tests\test_pdf_parser.py -q
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m compileall -q app
```

然后使用已有 `docling-inspection` 诊断目录中的脚本或临时命令重新检查真实论文。诊断脚本和结果保持在该本地忽略目录中；本文只记录正式实现所需的模型和验收标准。

## 参考源码

- 学习版当前解析器：`learning-implementation/backend/app/pdf_parser.py`
- 学习版解析测试：`learning-implementation/backend/tests/test_pdf_parser.py`
- 学习版 Docling 报告与 bbox 诊断：`learning-implementation/backend/docling-inspection/`（本地忽略）
- 原项目参考模型：`backend/rag/models.py` 中的 `PaperNode`
- 原项目解析和关系逻辑：`backend/rag/integration.py` 中的元素映射、`_link_captions_to_figures_tables()` 和 `_link_text_references()`

## 明确不在本计划中的工作

- 按 bbox 自行重排 Docling 元素。
- 章节树 `parent_id`、任意元素的通用父子树。
- 图片裁剪/落盘、Docling 图片二进制资产导出。
- PDF 上传流程自动触发解析、数据库解析状态、队列和重试。
- 文本切块、LangChain `Document` 转换、向量化与 Milvus 写入。
