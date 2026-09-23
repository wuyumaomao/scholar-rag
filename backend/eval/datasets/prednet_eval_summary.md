# PredRNet Reproducible QA Evaluation Set

## Paper Record

- Title: Neural Prediction Errors enable Analogical Visual Reasoning in Human Standard Intelligence Tests
- Source PDF: `G:\testpaper\1543_Neural_Prediction_Errors_.pdf`
- `paper_id`: `1543_Neural_Prediction_Errors_`
- PDF readability: confirmed by direct parsing with `pypdf` and rendered-page visual review.
- Total PDF pages: 12
- Main sections: `1. Introduction` (pp. 1-2), `2. Related work` (pp. 2-3), `3. Methods` (pp. 3-5), `4. Experiments` (pp. 5-9), `5. Limitation` (p. 9), and `6. Summary` (p. 9).

## Final Dataset

`prednet_eval.jsonl` contains 10 independently answerable cases. Each case has a paper-scoped `paper_id`, a 0-based `relevant_pages` list for `mmdocir_adapter.is_hit_page()`, matching 1-based `pdf_pages`, verbatim evidence, and a concise Chinese reference answer. The required `question` is preserved and the same text is also stored in `query`, which is the key read directly by the existing retrieval and generation evaluation functions.

Question-type distribution:

| question_type | Count |
| --- | ---: |
| method | 2 |
| experiment | 2 |
| result | 3 |
| table | 1 |
| figure | 1 |
| limitation | 1 |

Difficulty distribution:

| difficulty | Count |
| --- | ---: |
| easy | 1 |
| medium | 6 |
| hard | 3 |

## Case Index

| ID | Question | PDF page | Section | Evidence summary |
| --- | --- | ---: | --- | --- |
| `1543_Neural_Prediction_Errors_-q01` | PredRNet 的三个主要组件是什么？ | 3 | 3. Methods | 方法文字列出图像编码器、堆叠 PRB 和分类器。 |
| `1543_Neural_Prediction_Errors_-q02` | PRB 如何生成预测特征并计算预测误差？ | 4 | 3. Methods | 原文描述 8 x 1 卷积聚合上下文，Eq. (3)-(4) 给出预测和相减误差。 |
| `1543_Neural_Prediction_Errors_-q03` | 实现中为何在编码器后加入三个 PRB？ | 5 | 4.1. Datasets & Implementations | 原文明确 K=3 在验证集上取得最佳总体性能。 |
| `1543_Neural_Prediction_Errors_-q04` | PredRNet 与 STSN 的四数据集平均准确率是多少？ | 6 | 4.2. Main Results | Table 1 的 Avg 行给出 96.7 和 94.8。 |
| `1543_Neural_Prediction_Errors_-q05` | PredRNet 在 Table 1 四个数据集上的准确率是什么？ | 6 | 4.2. Main Results | Table 1 的 PredRNet 列给出四个逐数据集百分比。 |
| `1543_Neural_Prediction_Errors_-q06` | PredRNet 的 PGM 插值、外推和 OOD 平均准确率是多少？ | 7 | 4.2. Main Results | Table 2(a) 的 PredRNet 行给出 Int、Ext、Avg。 |
| `1543_Neural_Prediction_Errors_-q07` | PredRNet 在 CLEVR-Matrices 三种配置上的准确率是什么？ | 7 | 4.2. Main Results | Table 2(b) 的 PredRNet 行给出 Logic、Location、Count。 |
| `1543_Neural_Prediction_Errors_-q08` | K=3 与 K=4 PRB 消融的平均准确率分别是什么？ | 8 | 4.3. Ablation Experiments | Table 3 给出 96.5 与 95.8，并说明 K=4 有轻微下降。 |
| `1543_Neural_Prediction_Errors_-q09` | Figure 4 中误差的训练趋势及是否显式作损失？ | 9 | 4.5. PredRNet Minimizes Prediction Errors | 图注和正文说明误差下降，但未纳入 loss term。 |
| `1543_Neural_Prediction_Errors_-q10` | PredRNet 与人类学习设定的差异是什么？ | 9 | 5. Limitation | 局限性正文对比全监督全基准训练与少量示例的人类学习。 |

## Discarded Candidates

| Candidate topic | Reason discarded |
| --- | --- |
| PGM 和 RAVEN 数据集的总题量 | 虽有描述，但与模型机制、实验设置和结果相比评测价值较低，未纳入首版。 |
| K=4 PRB 性能下降的原因是过拟合 | 正文使用 “may be due to overfitting”，属于作者推测；为避免将推测作为标准答案而丢弃。 |
| Figure 3 中 XOR 与 AND 重叠的含义 | 图文将其解释为两种规则难以区分，但该表述的定量可验证性较弱，优先保留 Figure 4 的明确训练趋势。 |
| Bongard-LOGO 与 Visual Analogy Data 的多子集结果 | 与 PGM OOD、CLEVR 和 PRB 消融结果在泛化能力维度上重复，且首版已达到目标题量。 |

## Intended Evaluation Use

This dataset can be used for retrieval evaluation with Recall@5, Precision@5, MRR, and MAP, using `paper_id` plus 0-based `relevant_pages` with `is_hit_page()`.

It can also be used for generation evaluation with Faithfulness, AnswerRelevancy, and FactualCorrectness, using `question` and `reference_answer`.

## Validation Checklist

- Every JSONL line parses with `json.loads()`.
- All 10 IDs are unique.
- Every case has the same non-empty `paper_id`.
- Every `question`, `reference_answer`, and `evidence` is non-empty.
- For every case, `relevant_pages[i] == pdf_pages[i] - 1`.
- Evidence, answer, page, and section were manually cross-checked against the parsed PDF and rendered pages 3, 6, 8, and 9.
