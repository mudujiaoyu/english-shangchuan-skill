---
name: mudu-question-upload
description: 木牍教育英语题库录入全流程。从原卷（docx/pdf）提取、听力切段、题型与子类映射、答案与知识点打标、难度与分类评估，到查重预检与批次上传。含 26 个固定题型、知识点目录、developer.md 接口约束与各阶段脚本。
metadata:
  category: workflow
  subject: english
  platform: mudu
---

# 木牍英语题库录入

一份原卷 → 六步 → 进题库。每步有独立说明与脚本，全部收在本技能内。

```
① 解析  ② 听力  ③ 题型  ④ 知识点  ⑤ 难度分类  ⑥ 上传
 01_source → 02_audio → 03_types → 04_knowledge → 05_meta → 06_batch
```

| 步 | 做什么 | 说明 | 脚本 |
| --- | --- | --- | --- |
| ① | 原卷 → 正文/表格/图片/结构清单 | `references/stages/01-extract.md` | `scripts/01-extract/` |
| ② | 整卷听力 → 逐单元音频 | `references/stages/02-audio.md` | `scripts/02-audio/` |
| ③ | 26 主类 + 子类（建议存储值） | `references/stages/03-type-map.md` | — |
| ④ | 答案核对 + 七维度知识点 | `references/stages/04-knowledge.md` | `scripts/04-knowledge/` |
| ⑤ | 难度 + 分类 | `references/stages/05-meta.md` | `scripts/05-meta/` |
| ⑥ | 组装/查重/预检/媒体/上传 | `references/stages/06-upload.md` | `scripts/06-upload/` |

## 交接契约

| 步 | 产出 | 关键字段 |
| --- | --- | --- |
| ① | `01_source/正文.txt`、`media/`、`structure.json` | `sections[].type/questions`、`image_questions` |
| ② | `02_audio/li-XX.mp3`、`audio_map.json` | `{unit_id: {file, duration, covers}}` |
| ③ | `03_types/types.json` | `{unit_id: {type, subtypes}}` |
| ④ | `04_knowledge/knowledge.json` | `{unit_id: {answer, explanation, knowledge, subs}}` |
| ⑤ | `05_meta/meta.json` | `{unit_id: {difficulty, difficultyValue, categories}}` |
| ⑥ | `06_batch/batch.json`、`07_upload/receipt.json` | 批次对象 / `{staging_id, units, subs}` |

**上游缺字段就停下来问，不要自行补造。**

## 六步要点

### ① 解析
docx 优先；`.doc` 用 Word COM `SaveAs2($dst, 12)`。表格逐行导出，图片按文档顺序。
PDF 无文字层（`extract_text()` 为空）→ 渲染 + OCR：先认拼版（8 开多为 3 页或 2 页并排，页脚页码是切分锚点），
再定栏数（试卷 1、答案册 2、正文「上表通栏+下两栏」2）。OCR 首选 RapidOCR。详见 `references/pdf-extraction.md`。

### ② 听力
段数 = 听力单元数，不是题数。先 `silencedetect` 分层，再用念出的题号做锚点，`--intro-end` 切掉试音，
逐段回读校验（全中才算过）。转写时间戳不可信。详见 `references/audio-splitting.md`。

### ③ 题型
只能取 26 个主类，子类只能取框架里列出的值；漏 `subtypes` 会导致按子类筛选查不到。
不标准形态按「线索词 → 子类表 → 其他 → 暂停报候选」。详见 `references/type-subtypes.md`。

### ④ 知识点
答案只认原卷；解析没有就留空。七维度一题 1–3 个，同维度只挂一个。
完形挂体裁+主题（禁语法/辨析）；单项挂语法/辨析（禁主题/体裁）；听力禁语法；阅读禁语法/辨析。
**词分类必须下钻到叶子**；**单词拼写按答案词性倒推**。每个阅读小题必须有 `阅读技能/*`。
详见 `references/knowledge-tagging.md`、`references/knowledge-matching-rules.md`。

### ⑤ 难度与分类
`difficulty` 取 易/中/难；`filterMetadata.difficultyValue` 0–1（≥0.8 容易、≥0.5 适中）；
`categories` 只允许 优选题/易错题。**文档禁止按题型猜**：按词数/句长/长词比例/选项同质度/知识点打分，
听力有稿用稿、没稿用音频时长，都没有就留空待人工。详见 `references/difficulty-category.json`。

### ⑥ 上传
组装批次 → 答案比对 → 查重（ID/同年题号/内容指纹）→ 服务端校验器预检 → 部署媒体 → `POST /api/uploads`。
附件 `placement` 只能是 `question`/`option`/`answer`/`explanation`（写 `stem` 会静默 400）。
`PATCH attachments` 与 `filterMetadata` 都是整体替换。确认与发布只能人工。详见 `references/upload-api.md`。

## 常用命令

```bash
S=~/.agents/skills/mudu-question-upload/scripts

python $S/01-extract/extract_docx.py 原卷.docx 01_source/
python $S/01-extract/pdf_extract.py --pdf 试卷.pdf --out 01_source/ --cols-per-page 1
python $S/02-audio/cut_audio.py --audio 听力.mp3 --anchors 40.1,66.6 --intro-end 29.1 --out 02_audio/ --verify
python $S/04-knowledge/find_kp.py 被动语态
python $S/04-knowledge/check_tags.py --ids AH-2022
python $S/05-meta/assign_meta.py --batch b.json --report
python $S/06-upload/check_duplicates.py --batch b.json
python $S/06-upload/preflight_check.py --batch b.json --insert
```

## 汇总校验

```bash
python ~/.agents/skills/mudu-question-upload/scripts/verify_package.py --run
```

检查各阶段文档与脚本是否齐全、脚本能否编译，并跑 `find_kp` / `check_tags` / `assign_meta` / `check_duplicates` 四组 smoke test。

## 身份边界

- **不能**：`GET /api/uploads`、`POST /uploads/{id}/confirm`、`DELETE /api/questions/{id}`、`publish`、
  `withdraw`、建正式知识点节点。
- **能做**：目录读取、`POST /api/uploads`、`PATCH /api/questions/{id}`（仅草稿）、
  `POST /api/catalog/knowledge-proposals`、`POST /compositions/export`。

## 全局约定

- 题型与子类不得新增/改名/合并。
- 知识点必须落在目录叶子，父节点不算。
- 答案以原卷为准，不编造解析。
- 上传前必须过查重与预检两道闸门。
- 按年份切换试卷时，不要沿用上一年的题号范围来定位图片。
