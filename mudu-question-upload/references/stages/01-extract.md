# 源卷解析（01-extract）

**输入**：原卷文件（docx 优先；只有 PDF 时才走 PDF 分支）+ 同一份卷的答案/解析。
**输出**：`01_source/`

```
01_source/
  正文.txt          带 [TABLE n] 标记的正文
  media/            内嵌图片，按文档顺序
  structure.json    本卷结构清单（见下）
```

## 1.1 docx 提取

```bash
python scripts/extract_docx.py "原卷.docx" 01_source/
```

- `.doc` 老格式先转：Word COM `SaveAs2($dst, 12)`（不要用 `SaveAs([ref]…)`）。
- 表格必须逐行导出，不能只留文字（信息转换题要用）。
- 图片在 `word/media/`，文件名数字即文档顺序；先过滤目录条目（`endswith("/")`）。

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
- [ ] 图片题的位置、张数确认过（起点不许沿用上一年的范围）
- [ ] `structure.json` 每道题都能落到某个大题
