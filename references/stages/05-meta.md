# 难度与分类（05-meta）

**输入**：`04_knowledge/knowledge.json`（要用到知识点标签）+ 听力稿或音频时长。
**输出**：`05_meta/meta.json`

```json
{"AH-2022-021": {"difficulty": "适中", "difficultyValue": 0.68, "categories": ["易错题"]}}
```

## 5.1 文档规定（developer.md）

| 字段 | 取值 |
| --- | --- |
| `difficulty` | **`容易`／`适中`／`困难`**（与筛选标签一致；不要写 `易/中/难`） |
| `filterMetadata.difficultyValue` | 0–1；`>=0.80` 容易、`>=0.50 且 <0.80` 适中、`<0.50` 困难 |
| `filterMetadata.categories` | 只允许 `优选题`、`易错题` |

**文档明令**：「未知值保留空数组、空字符串或 `difficultyValue: null`，不要根据题型猜造标注。」

## 5.2 做法：按可观测特征打分

- 词数、平均句长、长词比例、选项同质度、知识点（推断/主旨/辨析/从句/非谓语）
- 复合规则：长文（≥320 词）且需推断 → 再降一档
- 题型只做 ±0.05 微调；书面表达/拼写/翻译等「题目要求」不计阅读量，走题型基准
- **听力**：有听力稿用稿子算（`--tapescripts`）；没有就用音频时长分档（`--durations`）
- 两者都没有 → 留空，列「待编辑定难度」

## 5.3 分类判定

- **易错题**：词汇辨析、固定搭配、时态/从句/非谓语；或选项形式高度一致（限单项/语法选择/选词/完成句子）
- **优选题**：阅读推理/主旨/最佳标题/写作手法；书面表达、读写综合、任务型

未命中就留空数组，不要为凑数给每题打标。

## 5.4 命令

```bash
python scripts/assign_meta.py --batch b.json --report                        # 看分布与依据
python scripts/assign_meta.py --ids AH-2022 --tapescripts ts.json --apply    # 补已入库
```

## 验收

- [ ] 每题 `difficulty` ∈ 易/中/难 或明确列入待定
- [ ] `difficultyValue` 在 0–1 且与 `difficulty` 档位一致
- [ ] `categories` 只含 优选题/易错题，或为空
- [ ] 报告里能看到每条的依据（词数、知识点、时长）
