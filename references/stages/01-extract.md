# 源卷解析（01-extract）

**输入**：原卷文件（docx 优先；只有 PDF 时才走 PDF 分支）+ 同一份卷的答案/解析。
**输出**：`01_source/`，答案册另出 `01_source_ans/answers.json`

```
01_source/
  正文.txt          带 [TABLE n] / [IMG imageN.xxx] 标记的正文
  media/            内嵌图片，按文档顺序
  structure.json    本卷结构清单（见下）
01_source_ans/
  answers.json      答案册抽出的「题号 → 答案」表（供 ⑥ check_answers 比对）
```

## 1.1 docx 提取

```bash
python scripts/01-extract/extract_docx.py "原卷.docx" 01_source/
python scripts/01-extract/contact_sheet.py 01_source/media/ --out 01_source/contact_sheet.png
python scripts/01-extract/extract_answers.py --docx 答案.docx --year 2025 --out 01_source_ans/answers.json
```

- `.doc` 老格式先转：Word COM `SaveAs2($dst, 12)`（不要用 `SaveAs([ref]…)`）。
- 表格必须逐行导出，不能只留文字（信息转换题要用）。
- **图片在正文里留 `[IMG image5.jpeg]` 位置标记**（图在所在段落之后单独一行）。只给 `media/` 目录时，
  「哪张图属于哪道题」只能靠序号反推，每年都要重认起点；有了标记，正文里就能直接看到图落在哪个题号之间。
  例：阅读 A 的目录整图出现在题干之前，四张选项图紧跟在 `A. B. C. D.` 之后。
- `media/` 数量 > 标记数量是正常的：页眉 logo、未被正文引用的占位图没有标记，脚本会提示差额。
- 用 `contact_sheet.py` 把图拼成缩略图清单，逐张确认「页眉 logo / 二维码 / 栏目角标 / 装饰图」不算选项图。
- 图片在 `word/media/`，文件名数字即文档顺序；先过滤目录条目（`endswith("/")`）。

### 合并卷：一条命令按年切开

教辅常把多套卷合订成一份（如「2022~2026安徽中考真题.docx」，1436 段、96 处图、85 个媒体文件）。
人工按「1.2026年…」截段既慢又容易切错，图片还会串年份（全卷 imageN 是连续编号）：

```bash
python scripts/01-extract/extract_docx.py "2022~2026安徽中考真题.docx" out/ --split-by-year --drop-first 1
# out/by_year/2026/正文.txt   out/by_year/2026/media/   out/by_year/index.json
```

- 按「20XX年…考试」卷首标记切段，`index.json` 记录每年的时间行号、行数、图片清单。
- **图片按年份重新归属**：只把该年段落里 `[IMG]` 引用到的文件拷进 `by_year/<年>/media/`，
  所以每年目录里的图就是该年自己的图，直接拿去做媒体部署。
- `--drop-first 1` 丢掉卷首那行「N.20XX年…考试」（它在表格里）；残留的 `[/TABLE]` 会被自动清掉。
- 卷首标记允许带 `/`、空格、序号前缀（表格单元格导出后常见 `/ 1.2026年…`）。
- 答案册侧对应 `extract_answers.py --year`，两边用同一套年份正则。

2026 实测：5 套卷切分 2 秒，2026 段 289 行 / 20 张图，与人工截段逐行一致。

## 1.2 答案册

```bash
python scripts/01-extract/extract_answers.py --docx 答案.docx --year 2025 --out 01_source_ans/answers.json
python scripts/01-extract/extract_answers.py --txt 答案.txt --year 2020 --out answers.json   # PDF/OCR 走这条
```

认两种形态：`题号 | 1~5 | 6~10` + `答案 | CBCAC | BBAAC` 的表格式，以及 `1~5 CBCAC`、`21.C　【解析】…`、
`16.Silence/silence　17.Smile` 的行内式；`【解析】` 之后不取，遇到「听力录音材料」即停。
产出 `{"numbers": {"1": "C", …}, "subjective": [73, 74, 75], "conflicts": [...]}`。

**多套卷合并的答案册必须给 `--year`**（如「2022~2026安徽中考真题答案.docx」）。脚本会按
「20XX年…考试」标题切出该年份的正文段，**表格也只取落在这段里的**；不切的话 5 套卷的答案会
按题号互相覆盖，实测冲突 187 条、抽出来的答案是错的（2026 第一次就踩到了）。
判据：`conflicts` 应为 0，且脚本会打印「该段内表格 n/8 张」。

**不要手抄答案表**：抄错一次（2019 第 19、20 题填反）就得整批返工；机器抽表 + `check_answers.py` 双来源比对才拦得住。

## 1.2 PDF（无文字层）

先判断：`PdfReader(pdf).pages[0].extract_text()` 为空 → 正文被转成矢量曲线，必须渲染 + OCR。

```bash
python scripts/pdf_extract.py --pdf 试卷.pdf --out 01_source/ --cols-per-page 1
```

- **先认拼版再定栏数**：8 开多为 A4 拼版（3 页或 2 页并排），页脚 `-101-` 是页边界；
  试卷每页 1 栏、答案册每页 2 栏、正文「上表通栏 + 下两栏」用 2。
- 不确定就用 `--cols-per-page` 指定，别让算法猜。
- OCR 首选 RapidOCR（`--ocr-backend rapid`），Windows OCR 只作兜底。
- 产出 `pageNN.items.json`：题号 → 题干 + 选项 + `pageNN_fig_q1A.png` 图片。

### 空格陷阱：下划线被导出成全角空格

部分年份（如 2020 安徽卷）原卷的空用**下划线**呈现，转文本后变成 `U+3000` 全角空格，
在页面上就看不到横线了。导出后必须检查并统一替换：

```python
stem = re.sub("\u3000{2,}", "______", stem)      # 空档
stem = re.sub(r"([A-Za-z])\s*______", r"\1 ______", stem)   # 补空格
```

单词拼写题是「首字母 + 空」：`s　　　　(星星)` → `s______ (星星)`。

`publish_check.py` 会扫全库并提示仍含全角空格的题干。

## 1.3 结构清单 structure.json

按 `references/structure.md` 三步走：**切大题 → 查目录判题型 → 定题组与媒体**。

```json
{
  "paper_id": "anhui-2022-english-zhenti",
  "year": 2022,
  "sections": [
    {"name": "Ⅰ 短对话理解", "type": "听力短对话理解", "questions": [[1,5]], "media": "audio"},
    {"name": "Ⅵ 完形填空", "type": "完形填空", "questions": [[31,40],[41,50]], "media": "none"}
  ],
  "groups": [{"id": "AH-2022-006", "questions": [6,7]}],
  "image_questions": [1, 2]
}
```

**结构从原卷推，不从年份或卷型推。** 真题卷、模拟卷、月考卷、同步练习形态差别很大，没有模板。

## 验收

- [ ] 正文行数与该卷题量对得上（缺题=漏段）
- [ ] 表格全部以 `[TABLE n]` 或 `materialBlocks` 保留
- [ ] 图片题的位置、张数确认过（先看 `[IMG]` 标记落在哪两题之间，再看 `contact_sheet.png`）
- [ ] `answers.json` 题号覆盖完整（`extract_answers.py` 会打印缺号），无 conflicts
- [ ] `structure.json` 每道题都能落到某个大题
