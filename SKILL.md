---
name: mudu-question-upload
description: 木牍教育英语题库录入全流程。从原卷（docx/pdf）提取、听力切段、题型与子类映射、答案与知识点打标、难度与分类评估，到查重预检与批次上传。含 27 个固定题型、知识点目录、developer.md 接口约束与各阶段脚本。
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
| ③ | 27 主类 + 子类（建议存储值） | `references/stages/03-type-map.md` | — |
| ④ | 答案核对 + 七维度知识点 | `references/stages/04-knowledge.md` | `scripts/04-knowledge/` |
| ⑤ | 难度 + 分类 | `references/stages/05-meta.md` | `scripts/05-meta/` |
| ⑥ | 组装/查重/预检/媒体/上传 | `references/stages/06-upload.md` | `scripts/06-upload/` |

## 交接契约

| 步 | 产出 | 关键字段 |
| --- | --- | --- |
| ① | `01_source/正文.txt`、`media/`、`structure.json`；`01_source_ans/answers.json` | `sections[].type/questions`、`image_questions`；`{题号: 答案}` |
| ② | `02_audio/li-XX.mp3`、`audio_map.json`、`tapescripts.json` | `{unit_id: {file, duration, covers}}`；`{unit_id: 听力稿}` |
| ③ | `03_types/types.json` | `{unit_id: {type, subtypes}}` |
| ④ | `04_knowledge/knowledge.json` | `{unit_id: {answer, explanation, knowledge, subs}}` |
| ⑤ | `05_meta/meta.json` | `{unit_id: {difficulty, difficultyValue, categories}}` |
| ⑥ | `06_batch/batch.json`、`07_upload/receipt.json` | 批次对象 / `{staging_id, units, subs}` |

**上游缺字段就停下来问，不要自行补造。**

## 六步要点

### ① 解析
docx 优先；`.doc` 用 Word COM `SaveAs2($dst, 12)`。表格逐行导出；图片在正文里留 `[IMG image5.jpeg]`
位置标记，再用 `contact_sheet.py` 出缩略图肉眼确认归属（logo/二维码/栏目角标不算选项图）。
PDF 无文字层（`extract_text()` 为空）→ 渲染 + OCR：先认拼版（8 开多为 3 页或 2 页并排，页脚页码是切分锚点），
再定栏数（试卷 1、答案册 2、正文「上表通栏+下两栏」2）。OCR 首选 RapidOCR。详见 `references/pdf-extraction.md`。
答案册另跑 `extract_answers.py` 落 `answers.json`（**多套卷合并的答案册必须给 `--year`**，否则题号互相覆盖），供 ⑥ 的 `check_answers.py` 逐题比对。

### ② 听力
段数 = 听力单元数，不是题数。先 `silencedetect` 分层，再用念出的题号做锚点，`--intro-end` 切掉试音，
逐段回读校验（全中才算过）。转写时间戳不可信；两大题之间夹中文题头时用 `--ends` 给显式终点。
详见 `references/audio-splitting.md`。

### ③ 题型
只能取 27 个主类，子类只能取框架里列出的值；漏 `subtypes` 会导致按子类筛选查不到。
不标准形态按「线索词 → 子类表 → 其他 → 暂停报候选」。详见 `references/type-subtypes.md`。

### ④ 知识点
答案只认原卷；解析有就录、没有留空，不编造。维度按《题型-知识点标签对照表1.0》来（见 `references/type-knowledge-map.md`）：
**只写括号里的多级子标签，维度根节点不写**。主题写**最后一级叶子**（一级主题是父节点，`check_tags.py` 判非叶子，
库内既有安徽卷也都是叶子口径）；体裁/词汇/语法/语音写根以下各级；语用只写叶子；
阅读类设题角度写 `设题角度/阅读/*`、听力类写 `设题角度/听力/*`；填空拼写类另加答案考点（该空考的词汇/语法叶子）。
同维度只挂一个，一题 2–4 个。
详见 `references/knowledge-tagging.md`、`references/knowledge-matching-rules.md`。

### ⑤ 难度与分类
`difficulty` 取 **容易/适中/困难**（服务端筛选标签只有这三个，不要写 `易/中/难`）；
`categories` 只允许 优选题/易错题。**文档禁止按题型猜**：按词数/句长/长词比例/选项同质度/知识点打分，
听力有稿用稿、没稿用音频时长，都没有就留空待人工。详见 `references/difficulty-category.json`。

### ⑥ 上传
组装批次 → 答案比对 → 查重（ID/同年题号/内容指纹）→ 服务端校验器预检 → 部署媒体 → `POST /api/uploads`。
`run_upload.py` 把这条链一次串起来（本机体检并行、服务器闸门合并为一次 SSH、媒体并发校验），
34 单元批次约 4 秒跑完；单步脚本仍可单独使用。
附件 `placement` 只能是 `question`/`option`/`answer`/`explanation`（写 `stem` 会静默 400）。
`PATCH attachments` 与 `filterMetadata` 都是整体替换。确认与发布只能人工。发布前跑 `scripts/06-upload/publish_check.py`：只查 题干/答案/题型/知识点/子题完整性，解析为空不阻断（有就录、没有留空）。详见 `references/upload-api.md`。

## 常用命令

```bash
S=~/.agents/skills/mudu-question-upload/scripts

python $S/01-extract/extract_docx.py 原卷.docx 01_source/
python $S/01-extract/contact_sheet.py 01_source/media/ --out 01_source/contact_sheet.png
python $S/01-extract/extract_answers.py --docx 答案.docx --year 2025 --out 01_source_ans/answers.json
python $S/01-extract/pdf_extract.py --pdf 试卷.pdf --out 01_source/ --cols-per-page 1
python $S/02-audio/extract_script.py --docx 答案.docx --year 2022 --out ts.json
python $S/02-audio/cut_audio.py --audio 听力.mp3 --anchors 40.1,66.6 --intro-end 29.1 --out 02_audio/ \
    --verify --verify-seconds 20
python $S/04-knowledge/find_kp.py 被动语态
python $S/04-knowledge/check_tags.py --ids AH-2022
python $S/04-knowledge/check_tags.py --batch 06_batch/batch.json      # 上传前查
python $S/05-meta/assign_meta.py --batch b.json --report
python $S/06-upload/check_answers.py --batch b.json --answers 01_source_ans/answers.json
python $S/06-upload/check_duplicates.py --batch b.json
python $S/06-upload/preflight_check.py --batch b.json --insert
python $S/06-upload/publish_check.py --ids AH-2022
python $S/06-upload/check_text.py --ids AH-2022
python $S/06-upload/check_text.py --batch 06_batch/batch.json          # 上传前查
python $S/06-upload/run_upload.py --batch b.json --media-dir media_upload/ --answers answers.json
```

## 汇总校验

```bash
python ~/.agents/skills/mudu-question-upload/scripts/verify_package.py --run
```

检查各阶段文档与脚本是否齐全、脚本能否编译，并跑 `find_kp`（含 `--list-branches`）/ `check_tags` /
`assign_meta` / `check_duplicates` / `extract_answers` / `check_answers` / `check_text` 七组 smoke test；
其中 `check_answers` 自带正反两个样例（改错必须被拦下），fixture 不依赖外部文件。

## 改动方向

本技能**以本地目录 `~/.agents/skills/mudu-question-upload` 为源**，仓库（`mudu-skills`）只做同步：

```bash
python ~/.agents/skills/mudu-question-upload/sync_skill.py --from-skill   # 本地 → 仓库
python ~/.agents/skills/mudu-question-upload/sync_skill.py                # 仓库 → 本地（会覆盖本地改动）
```

直接跑默认方向会把本地未同步的改动冲掉（2026-10-23 踩过）。要么先 `--from-skill`，要么用 `--mode link` 把本地建成仓库的目录联接。

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
