# PDF 提取与切图

面对于**没有文字层**的印刷版 PDF（正文被转成矢量曲线，`extract_text()` 返回 0 字）。
脚本：`scripts/pdf_extract.py`。

## 判断有没有文字层

```python
from pypdf import PdfReader
r = PdfReader(pdf); print(r.pages[0].extract_text())
```

空 → 走本流程；有字 → 直接用文字层（更快更准）。

## 用法

```bash
python pdf_extract.py --pdf 试卷.pdf --out out/ [--pages 1-3] \
    [--dpi 200] [--ocr-dpi 300] [--cols-per-page N] [--ocr-backend auto|rapid|win]
```

| 参数 | 说明 |
| --- | --- |
| `--cols-per-page` | **每页栏数**。0=自动猜（易错）；1/2/3 直接指定，最稳 |
| `--ocr-backend` | 默认 `auto`：优先 RapidOCR，退回 Windows OCR |
| `--dpi / --ocr-dpi` | 版面用 200，识别用 300（再高没收益） |

产出：

```
out/pageNN/colNN.txt       按栏文本
out/pageNN.txt             整页阅读顺序（[FIGURE:q1A] / [TABLE:t21] 占位）
out/pageNN.items.json      题号 → 题干、选项、图片文件
out/media/pageNN_fig_q1A.png   选项图（题号+选项字母）
out/media/pageNN_tbl_t21.png   表格整块
out/report.json            每页栏数、图/表坐标
```

## 版面：先认「拼版」，再定「栏数」

8 开纸多数是 **A4 拼版**：3 页并排（页脚 −101− −102− −103−）或 2 页并排。
所以正确处理顺序是：

1. **按页码切页**——页脚 `-101-` 这类页码就是页边界，比找空白列可靠；
2. **页内再定栏数**——试卷每页 1 栏，答案册每页 2 栏，正文常见「上方通栏表格 + 下方两栏」。

自动识别只能兜底，**版面复杂的书直接用 `--cols-per-page` 指定**，一次就对。

| 文档 | 拼版 | `--cols-per-page` |
| --- | --- | --- |
| 试卷（学用/教用） | 3 页并排 | 1 |
| 答案册（DA） | 2 页并排，每页 2 栏 | 2 |
| 正文（学用/教用） | 单页，上表通栏 + 下两栏 | 2 |

## OCR 选择

| 引擎 | 速度 | 准确度 | 备注 |
| --- | --- | --- | --- |
| RapidOCR（onnxruntime） | ~18s/页 | 好：`Happy Holiday`、`anything interesting`、`【基础巩固】` 都对 | 首选，离线，模型随包 |
| Windows OCR（winsdk） | 快 | 一般：易错 `H01iday`、`campmg`、括号混用 | 兜底 |

```bash
pip install pypdf pypdfium2 opencv-python-headless rapidocr-onnxruntime winsdk
```

## 图片与表格

- **选项图**：先屏蔽 OCR 文字 → 二值化 → 膨胀 → 连通域 → 按尺寸和长宽比过滤（滤掉装订边竖排、下划线、小碎块）。
- **题号归属**：在图上方找最近的 `（ ）12.` 行；同一行的多张图按 x 排序后依次给 A/B/C。
- **表格**：长横线 + 长竖线做形态学开运算，外接矩形整块裁出（只裁图，不还原单元格）。

## 已知限制

1. **通栏 + 分栏混排**的页，单一栏数切不准；需要 `--cols-per-page` 或人工确认。
2. OCR 仍有系统性错字：`Ⅰ/Ⅱ` → `1/11`、`（ ）` 括号不对称、英文单词被拆空格。已加罗马数字与大题名的修正，其余需人工校对。
3. 表格只出图片，不出单元格文本；若要结构化需二次 OCR + 线框切分。
4. 页眉页脚、装订边（竖排「姓名班级学校」）已过滤，但版式特殊的书可能漏。
5. 图片题若选项图与文字混排在同一行，归属可能错位，需看 `items.json` 复核。

## 与主流程的衔接

PDF 解析产出的是**草稿素材**，仍需按 `SKILL.md` §6 判题型、§7 打知识点、§8 查重预检，再走 `POST /api/uploads`。
同级目录有 Word 版时**优先用 Word**；PDF 用于校对图片题、表格、跨栏断行这些 docx 看不准的地方。
