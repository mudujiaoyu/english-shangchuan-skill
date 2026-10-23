# -*- coding: utf-8 -*-
"""PDF → 结构化文本 + 图片切分（题库录题用）。

面向**无文字层**（正文转曲）的印刷版 PDF：渲染 → 分栏 → OCR → 图形/表格切分 → 题号关联。

    python pdf_extract.py --pdf 试卷.pdf --out out/ [--pages 1-3] [--dpi 200] [--ocr-dpi 300]

产出：
    out/pageNN/colNN.txt      按栏文本
    out/pageNN.txt            整页阅读顺序（图形处插 [FIGURE:q3A] 这类占位）
    out/pageNN.items.json     题号 → 文本片段 + 图形文件（便于直接组批次）
    out/media/*.png           切出的选项图/插图/表格
    out/report.json           每页栏数、图/表数量与坐标

依赖：pypdfium2、numpy、opencv-python-headless、Pillow、winsdk（Windows OCR）
"""
import argparse
import asyncio
import json
import os
import re
import sys

import cv2
import numpy as np
import pypdfium2 as pdfium

sys.stdout.reconfigure(encoding="utf-8")

BODY_TOP, BODY_BOTTOM = 0.06, 0.94

# 图形过滤阈值（像素，基于 --dpi）
MIN_W, MIN_H = 55, 70
MIN_AREA = 8000
MAX_ASPECT = 6.0          # 长宽比过大 → 侧边栏/分隔线

CJK = r"\u4e00-\u9fff"


# ---------------- 渲染 ----------------
def render(page, dpi):
    return page.render(scale=dpi / 72.0).to_pil().convert("RGB")


# ---------------- OCR ----------------
async def _ocr_async(pil_img, lang):
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage import FileAccessMode, StorageFile

    engine = OcrEngine.try_create_from_language(Language(lang))
    if engine is None:
        return []
    tmp = os.path.join(os.environ.get("TEMP", "."), "_pdf_ocr_tmp.png")
    pil_img.save(tmp)
    f = await StorageFile.get_file_from_path_async(tmp)
    stream = await f.open_async(FileAccessMode.READ)
    dec = await BitmapDecoder.create_async(stream)
    bmp = await dec.get_software_bitmap_async()
    res = await engine.recognize_async(bmp)
    out = []
    for line in res.lines:
        words = list(line.words)
        if not words:
            continue
        x0 = min(w.bounding_rect.x for w in words)
        y0 = min(w.bounding_rect.y for w in words)
        x1 = max(w.bounding_rect.x + w.bounding_rect.width for w in words)
        y1 = max(w.bounding_rect.y + w.bounding_rect.height for w in words)
        out.append({"text": line.text, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return out


_RAPID = None


def _rapid():
    global _RAPID
    if _RAPID is None:
        from rapidocr_onnxruntime import RapidOCR
        _RAPID = RapidOCR()
    return _RAPID


def ocr_rapid(pil_img):
    arr = np.array(pil_img.convert("RGB"))[:, :, ::-1]
    res, _ = _rapid()(arr)
    out = []
    for box, text, _score in (res or []):
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        out.append({"text": text, "x0": min(xs), "y0": min(ys), "x1": max(xs), "y1": max(ys)})
    return out


def ocr(pil_img, lang="zh-Hans-CN", backend="auto"):
    if backend in ("auto", "rapid"):
        try:
            return ocr_rapid(pil_img)
        except Exception as e:
            if backend == "rapid":
                print(f"  [warn] RapidOCR 不可用: {e}")
                return []
    try:
        return asyncio.run(_ocr_async(pil_img, lang))
    except Exception as e:
        print(f"  [warn] Windows OCR 不可用: {e}")
        return []


# ---------------- 文本清洗 ----------------
SECTION_WORDS = ("短对话理解", "长对话理解", "短文理解", "信息转换", "单项填空", "完形填空",
                 "补全对话", "阅读理解", "单词拼写", "书面表达", "任务型阅读", "语法选择", "词汇运用")
ROMAN = {"1": "Ⅰ", "l": "Ⅰ", "i": "Ⅰ", "11": "Ⅱ", "ll": "Ⅱ", "il": "Ⅱ", "ii": "Ⅱ",
         "111": "Ⅲ", "lll": "Ⅲ", "iii": "Ⅲ", "1v": "Ⅳ", "iv": "Ⅳ", "1V": "Ⅳ",
         "V": "Ⅴ", "v": "Ⅴ"}


def fix_roman(s):
    m = re.match(r"^([0-9lLiIvV]{1,3})\s*[.．、]\s*(\S+)", s)
    if m and m.group(2).startswith(SECTION_WORDS):
        r = ROMAN.get(m.group(1).lower(), None)
        if r:
            return r + "." + s[m.end(1):].lstrip(".．、 ")
    return s


def clean_text(s):
    s = s.replace("\u00a0", " ")
    # 中文字符间的空格去掉
    s = re.sub(rf"(?<=[{CJK}])\s+(?=[{CJK}])", "", s)
    s = re.sub(rf"(?<=[{CJK}])\s+(?=[0-9A-Za-z])", "", s)
    s = re.sub(rf"(?<=[0-9A-Za-z])\s+(?=[{CJK}])", "", s)
    # 常见标点误识
    s = s.replace("﹒", ".").replace("·", ".").replace("‘", "'").replace("’", "'")
    s = s.replace("：", ":") if re.match(r"^[A-Za-z]+:$", s) else s
    s = re.sub(r"\s+", " ", s).strip()
    # 选项字母统一大写：句首 a./b./c./d. → A./B./C./D.
    s = re.sub(r"^([（(]?\s*)([abcd])(\s*[.．、])", lambda m: m.group(1) + m.group(2).upper() + ".", s)
    # 括号统一
    s = s.replace("（ ）", "（ ）").replace("( )", "( )")
    s = fix_roman(s)
    return s


# ---------------- 分栏 ----------------
def _body_band(gray):
    h, w = gray.shape
    ink = (gray < 200).astype(np.uint8)
    y0, y1 = int(h * BODY_TOP), int(h * BODY_BOTTOM)
    return ink[y0:y1]


def columns_from_lines(lines, width, blank_frac=None, min_share=0.06):
    """按文本行左边界做一维聚类定栏（比像素投影稳，避免词间空格被当成栏缝）。"""
    if not lines:
        return None
    xs = np.array(sorted(l["x0"] for l in lines), dtype=float)
    if len(xs) < 8:
        return None
    step = max(3.0, width * 0.002)
    bins = np.arange(0, width + step, step)
    hist, edges = np.histogram(xs, bins=bins)
    win = max(3, int(round(width * 0.006 / step)))
    kernel = np.ones(win) / win
    smooth = np.convolve(hist, kernel, mode="same")
    thr = smooth.max() * 0.25
    peaks = []
    for i in range(1, len(smooth) - 1):
        if smooth[i] >= thr and smooth[i] >= smooth[i - 1] and smooth[i] >= smooth[i + 1]:
            x = edges[i] + step / 2
            if peaks and x - peaks[-1] < width * 0.08:
                continue
            peaks.append(x)
    if len(peaks) < 2:
        return None
    def is_real_gutter(x):
        if blank_frac is None:
            return True
        lo = max(0, int(x) - 8)
        hi = min(len(blank_frac), int(x) + 9)
        return hi > lo and float(blank_frac[lo:hi].max()) >= 0.88

    bounds = [0.0]
    kept_peaks = [peaks[0]]
    for a, b in zip(peaks, peaks[1:]):
        mid = (a + b) / 2
        if is_real_gutter(mid):
            bounds.append(mid)
            kept_peaks.append(b)
        else:
            kept_peaks.append(b)
    if len(bounds) == 1:
        return None
    bounds.append(float(width))
    cols = [(int(bounds[i]), int(bounds[i + 1])) for i in range(len(bounds) - 1)]
    cols = [(a, b) for a, b in cols if (b - a) >= width * min_share]
    return cols if len(cols) >= 2 else None


def find_columns_from_boxes(lines, width, min_col_ratio=0.14, min_gap=None):
    """按文本行左边界（x0）的众数定栏：每栏有大量行左端对齐。"""
    if len(lines) < 10:
        return None
    min_gap = min_gap or max(8, int(width * 0.004))
    xs = np.array([l["x0"] for l in lines], dtype=float)
    step = max(3.0, width * 0.004)
    edges = np.arange(0, width + step, step)
    hist, _ = np.histogram(xs, bins=edges)
    need = max(6, int(len(xs) * 0.05))          # 一栏至少 5% 的行从这里起
    peaks = []
    for i in range(len(hist)):
        if hist[i] >= need:
            x = float(edges[i])
            if peaks and x - peaks[-1][0] < width * 0.10:
                if hist[i] > peaks[-1][1]:
                    peaks[-1] = (x, int(hist[i]))
                continue
            peaks.append((x, int(hist[i])))
    peaks.sort()
    if len(peaks) < 2:
        return None
    bounds = [0]
    for (a, _), (b, _) in zip(peaks, peaks[1:]):
        mid = int((a + b) / 2)
        if mid - bounds[-1] < width * 0.10:
            continue
        bounds.append(mid)
    bounds.append(int(width))
    cols = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    cols = [(a, b) for a, b in cols if (b - a) >= width * 0.03]
    return cols if len(cols) >= 2 else None


PAGE_NO_RE = re.compile(r"^[-–—‐]\s*(\d{2,4})\s*[-–—‐]$")


def columns_from_page_numbers(lines, width):
    """8 开拼版：页脚有 -104- 这类页码，页码所在位置就是页与页的分界。"""
    marks = []
    for l in lines:
        m = PAGE_NO_RE.match(l["text"].strip())
        if m:
            marks.append(((l["x0"] + l["x1"]) / 2, int(m.group(1))))
    if len(marks) < 2:
        return None
    marks.sort()
    bounds = [0]
    for (cx, _num), (nx, _n2) in zip(marks, marks[1:]):
        bounds.append(int((cx + nx) / 2))
    bounds.append(int(width))
    cols = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    cols = [(a, b) for a, b in cols if (b - a) >= width * 0.15]
    return cols if len(cols) >= 2 else None


def merge_thin_columns(cols, lines, width, min_width=0.20, min_line_share=0.12):
    """把「窄且行数很少」的栏并回相邻栏，消除把缩进/表格当栏缝的误切。"""
    if not cols or len(cols) < 2:
        return cols
    cols = [list(c) for c in cols]
    total = max(1, len(lines))

    def count(c):
        a, b = c
        return sum(1 for l in lines if a <= (l["x0"] + l["x1"]) / 2 < b)

    changed = True
    while changed and len(cols) > 1:
        changed = False
        stats = [(count(c), c[1] - c[0]) for c in cols]
        for i, (n, wdt) in enumerate(stats):
            if wdt < width * min_width or n < total * min_line_share:
                if len(cols) == 1:
                    break
                if i == 0:
                    j = 1
                elif i == len(cols) - 1:
                    j = i - 1
                else:
                    j = i - 1 if cols[i - 1][1] - cols[i - 1][0] < cols[i + 1][1] - cols[i + 1][0] else i + 1
                a, b = min(cols[i][0], cols[j][0]), max(cols[i][1], cols[j][1])
                cols = [c for k, c in enumerate(cols) if k not in (i, j)] + [[a, b]]
                cols.sort()
                changed = True
                break
    return [(a, b) for a, b in cols]


def find_columns(gray, min_col_ratio=0.14):
    """兜底（无 OCR 时）：像素留白率 >=0.93 且宽 >=1.2% 页宽。"""
    h, w = gray.shape
    band = _body_band(gray)
    bf = (band == 0).mean(axis=0)
    runs, s_i, min_gap = [], None, max(20, int(w * 0.012))
    for i, v in enumerate(bf):
        if v >= 0.93:
            s_i = i if s_i is None else s_i
        elif s_i is not None:
            if i - s_i >= min_gap:
                runs.append((s_i, i))
            s_i = None
    if s_i is not None and w - s_i >= min_gap:
        runs.append((s_i, w))
    bounds = [0]
    for a, b in runs:
        if a < w * 0.12 or (w - b) < w * 0.12:
            continue
        mid = (a + b) // 2
        if mid - bounds[-1] >= w * min_col_ratio:
            bounds.append(mid)
    bounds.append(w)
    cols = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    return [(a, b) for a, b in cols if (b - a) >= w * 0.03]


# ---------------- 图形/表格 ----------------
def detect_regions(gray, boxes, col_x0, col_x1):
    h, w = gray.shape
    ink = (gray < 200).astype(np.uint8)
    sub = ink[:, col_x0:col_x1].copy()

    for b in boxes:                                    # 屏蔽文字
        x0 = max(0, int(b["x0"]) - 3 - col_x0)
        x1 = min(sub.shape[1], int(b["x1"]) + 4 - col_x0)
        y0 = max(0, int(b["y0"]) - 2)
        y1 = min(h, int(b["y1"]) + 3)
        if x1 > x0 and y1 > y0:
            sub[y0:y1, x0:x1] = 0

    # 表格：长横线 + 长竖线
    hk = max(30, int(sub.shape[1] * 0.35))
    vk = max(30, int(h * 0.08))
    hor = cv2.morphologyEx(sub, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (hk, 1)))
    ver = cv2.morphologyEx(sub, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, vk)))
    rules = cv2.dilate(cv2.bitwise_or(hor, ver), np.ones((5, 5), np.uint8), iterations=2)
    tables = []
    cnts, _ = cv2.findContours(rules, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw > 80 and ch > 50:
            tables.append((x + col_x0, y, cw, ch))

    # 图形：去掉表格区域后做连通域
    fm = sub.copy()
    for x, y, cw, ch in tables:
        fm[y:y + ch + 4, max(0, x - col_x0 - 2):min(fm.shape[1], x - col_x0 + cw + 2)] = 0
    d = cv2.dilate(fm, np.ones((9, 9), np.uint8), iterations=2)
    cnts, _ = cv2.findContours(d, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    figs = []
    for c in cnts:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw < MIN_W or ch < MIN_H or cw * ch < MIN_AREA:
            continue
        if max(cw / max(ch, 1), ch / max(cw, 1)) > MAX_ASPECT:
            continue
        if cw > 0.95 * (col_x1 - col_x0) and ch > 0.5 * h:
            continue
        figs.append((x + col_x0, y, cw, ch))

    return merge_boxes(figs), merge_boxes(tables)


def merge_boxes(boxes, pad=4):
    if not boxes:
        return []
    kept = []
    for b in sorted(boxes, key=lambda b: -b[2] * b[3]):
        x, y, w, h = b
        if any(not (x + w < k[0] - pad or x > k[0] + k[2] + pad or
                    y + h < k[1] - pad or y > k[1] + k[3] + pad) for k in kept):
            continue
        kept.append(b)
    return sorted(kept, key=lambda b: (b[1], b[0]))


# ---------------- 题号关联 ----------------
Q_RE = re.compile(r"^[（()）\[\]【】\s]*(\d{1,2})\s*[.．、]")


def question_for(fig_y, lines):
    """在图上方找最近的题号；找不到返回 None。"""
    best = None
    for ln in lines:
        m = Q_RE.match(ln["text"].strip())
        if m and ln["y0"] < fig_y + 8:
            if best is None or ln["y0"] > best[0]:
                best = (ln["y0"], int(m.group(1)))
    return best[1] if best else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pages", default="")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--ocr-dpi", type=int, default=300)
    ap.add_argument("--no-ocr", action="store_true")
    ap.add_argument("--lang", default="zh-Hans-CN")
    ap.add_argument("--ocr-backend", default="auto", choices=["auto", "rapid", "win"])
    ap.add_argument("--cols-per-page", type=int, default=0,
                    help="每页栏数（0=自动；1/2/3 强制）")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    media = os.path.join(a.out, "media")
    os.makedirs(media, exist_ok=True)

    pdf = pdfium.PdfDocument(a.pdf)
    total = len(pdf)
    idxs = list(range(total)) if not a.pages else [
        i for chunk in a.pages.split(",") for i in (
            range(int(chunk.split("-")[0]) - 1, int(chunk.split("-")[-1]))
            if "-" in chunk else [int(chunk) - 1])]
    idxs = [i for i in idxs if 0 <= i < total]
    print(f"{os.path.basename(a.pdf)}：{total} 页，处理 {len(idxs)} 页")

    report_all = []
    for idx in idxs:
        page = pdf[idx]
        lo = render(page, a.dpi)
        gray = np.array(lo.convert("L"))
        W = gray.shape[1]

        # 先 OCR 一遍（300dpi）拿行框，再据此定栏
        probe_lines = []
        if not a.no_ocr:
            probe = render(page, a.ocr_dpi)
            kk = a.ocr_dpi / a.dpi
            for l in ocr(probe, a.lang, a.ocr_backend):
                probe_lines.append({"text": clean_text(l["text"]),
                                    "x0": l["x0"] / kk, "x1": l["x1"] / kk,
                                    "y0": l["y0"] / kk, "y1": l["y1"] / kk})
        cols = None
        if a.cols_per_page and probe_lines:
            pages = columns_from_page_numbers(probe_lines, W) or [(0, W)]
            cols = []
            n = max(1, a.cols_per_page)
            band = _body_band(gray)
            bf = (band == 0).mean(axis=0)
            for (px0, px1) in pages:
                pw = px1 - px0
                if n == 1:
                    cols.append((px0, px1))
                    continue
                # 页内找 n-1 个最宽的低墨带做切点
                step = pw / n
                cuts = []
                for k in range(1, n):
                    guess = px0 + step * k
                    cut_lo, cut_hi = int(guess - pw * 0.12), int(guess + pw * 0.12)
                    cut_lo, cut_hi = max(px0 + 10, cut_lo), min(px1 - 10, cut_hi)
                    if cut_hi <= cut_lo:
                        cuts.append(int(guess))
                        continue
                    win = bf[cut_lo:cut_hi]
                    cut_at = int(win.argmin()) if len(win) else 0
                    cuts.append(cut_lo + cut_at)
                bounds = [px0] + cuts + [px1]
                for i in range(len(bounds) - 1):
                    cols.append((bounds[i], bounds[i + 1]))
        elif probe_lines:
            pages = columns_from_page_numbers(probe_lines, W)
            if pages:                                  # 拼版：先按页码切页，再页内切栏
                cols = []
                for (px0, px1) in pages:
                    pw = px1 - px0
                    sub = [dict(l, x0=l["x0"] - px0, x1=l["x1"] - px0)
                           for l in probe_lines if px0 <= (l["x0"] + l["x1"]) / 2 < px1]
                    inner = find_columns_from_boxes(sub, pw)
                    if inner:
                        cols += [(px0 + a, px0 + b) for a, b in inner]
                    else:
                        cols.append((px0, px1))
            else:
                cols = find_columns_from_boxes(probe_lines, W)
        cols = cols or find_columns(gray)
        if probe_lines:
            cols = merge_thin_columns(cols, probe_lines, W)
        page_name = f"page{idx + 1:02d}"
        pdir = os.path.join(a.out, page_name)
        os.makedirs(pdir, exist_ok=True)

        lines = []
        if not a.no_ocr:
            hi = render(page, a.ocr_dpi)
            k = a.ocr_dpi / a.dpi
            for ln in ocr(hi, a.lang, a.ocr_backend):
                lines.append({"text": clean_text(ln["text"]),
                              "x0": ln["x0"] / k, "x1": ln["x1"] / k,
                              "y0": ln["y0"] / k, "y1": ln["y1"] / k})

        h_total = gray.shape[0]
        rep = {"page": idx + 1, "columns": [], "figures": [], "tables": [], "items": {}}
        page_parts = []
        W = gray.shape[1]
        lines = [l for l in lines if l["x1"] > W * 0.035 and l["x0"] < W * 0.965]
        for ci, (cx0, cx1) in enumerate(cols):
            ls = [l for l in lines if cx0 <= (l["x0"] + l["x1"]) / 2 < cx1]
            ls.sort(key=lambda x: (round(x["y0"] / 8), x["x0"]))
            figs, tabs = detect_regions(gray, ls, cx0, cx1)

            # 图形按 x 排序后分配选项字母（同一题的 A/B/C）
            figs_by_q = {}
            for (x, y, w, h) in figs:
                q = question_for(y, ls)
                figs_by_q.setdefault(q, []).append((x, y, w, h))
            marks = []
            for q, boxes in figs_by_q.items():
                boxes.sort(key=lambda b: (round(b[1] / (0.02 * h_total)), b[0]))
                letters = "ABCDEFGH"
                row_y = {}
                for b in boxes:
                    row_y.setdefault(round(b[1] / (0.02 * h_total)), b[1])
                for i, (x, y, w, h) in enumerate(boxes):
                    tag = f"q{q}{letters[i]}" if q else f"c{ci + 1}{i + 1}"
                    fn = f"{page_name}_fig_{tag}.png"
                    lo.crop((max(0, x - 8), max(0, y - 8),
                             min(lo.width, x + w + 8), min(lo.height, y + h + 8))).save(
                        os.path.join(media, fn))
                    rep["figures"].append({"file": fn, "question": q, "option": letters[i],
                                           "box": [x, y, w, h], "column": ci + 1})
                    marks.append((row_y[round(y / (0.02 * h_total))], f"[FIGURE:{tag}]"))
                    key = str(q) if q else f"col{ci + 1}"
                    rep["items"].setdefault(key, {"figures": [], "text": ""})
                    rep["items"][key]["figures"].append(fn)

            for ti, (x, y, w, h) in enumerate(tabs):
                tag = f"t{ci + 1}{ti + 1}"
                fn = f"{page_name}_tbl_{tag}.png"
                lo.crop((max(0, x - 6), max(0, y - 6),
                         min(lo.width, x + w + 6), min(lo.height, y + h + 6))).save(os.path.join(media, fn))
                rep["tables"].append({"file": fn, "box": [x, y, w, h], "column": ci + 1})
                marks.append((y, f"[TABLE:{tag}]"))

            body = []
            current_q = None
            for ln in ls:
                body.append((ln["y0"], ln["text"]))
                m = Q_RE.match(ln["text"].strip())
                if m:
                    current_q = int(m.group(1))
                    rep["items"].setdefault(str(current_q), {"figures": [], "text": ""})
                    rep["items"][str(current_q)]["text"] += ln["text"] + "\n"
                elif current_q is not None:
                    rep["items"][str(current_q)]["text"] += ln["text"] + "\n"
            merged = sorted(body + marks, key=lambda x: x[0])
            text = "\n".join(t for _, t in merged)
            with open(os.path.join(pdir, f"col{ci + 1:02d}.txt"), "w", encoding="utf-8") as f:
                f.write(text + "\n")
            page_parts.append(text)
            rep["columns"].append({"index": ci + 1, "x": [cx0, cx1], "lines": len(ls),
                                   "chars": sum(len(l["text"]) for l in ls),
                                   "figures": len(figs), "tables": len(tabs)})

        with open(os.path.join(a.out, f"{page_name}.txt"), "w", encoding="utf-8") as f:
            f.write("\n\n".join(page_parts) + "\n")
        with open(os.path.join(a.out, f"{page_name}.items.json"), "w", encoding="utf-8") as f:
            json.dump(rep["items"], f, ensure_ascii=False, indent=1)
        report_all.append(rep)

        print(f"  第{idx + 1}页：{len(cols)} 栏 | 文本 {sum(c['chars'] for c in rep['columns'])} 字 "
              f"| 图 {len(rep['figures'])} | 表 {len(rep['tables'])} | 题号 {len(rep['items'])}")

    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report_all, f, ensure_ascii=False, indent=1)
    print("完成 ->", a.out)


if __name__ == "__main__":
    main()
