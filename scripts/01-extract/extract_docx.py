# -*- coding: utf-8 -*-
"""把 .docx 原卷拆成 正文.txt（含 [TABLE]/[IMG] 标记）+ media/ 图片目录。

用法:
    python extract_docx.py "<原卷.docx>" "<输出目录>"
    python extract_docx.py "<2022~2026合并卷.docx>" "<输出目录>" --split-by-year

输出:
    <输出目录>/正文.txt     按文档顺序，段落原样，表格用 [TABLE i rows=x cols=y] 包住，
                            内嵌图片在所在段落之后单独一行留 `[IMG image5.jpeg]` 位置标记
    <输出目录>/media/       内嵌图片，保留原文件名（image1.png / image10.jpeg ...）
    --split-by-year 时另出：
    <输出目录>/by_year/2026/正文.txt   每年一份（含该年的表格与图片标记）
    <输出目录>/by_year/2026/media/     该年段落里引用到的图片（按文档顺序就是该年的 image1..N）
    <输出目录>/by_year/index.json      {year: {lines, start, end, images[...]}}

为什么要留 [IMG] 标记：
    只给 media/ 目录时，「哪张图属于哪道题」只能靠文件名序号反推，logo/二维码/栏目角标混在一起，
    图片题的起点每年都要肉眼重认（历史事故：2020 阅读 A 整篇是图、2021 选项图从 image4 起）。
    有了位置标记，正文里就能直接看到图落在哪个题号之间。

为什么需要 --split-by-year：
    教辅常把多套卷合订成一份 docx（如「2022~2026安徽中考真题.docx」），全卷 85+ 张图混在一个
    media/ 里。人工按「1.2026年…」截段既慢又容易切错边界；图片更要按年份重新编号归属。
    合并卷的答案册同理——`extract_answers.py --year` 已在做，这里补齐正文侧。

注意:
    - .doc（老二进制）先用 Word COM 转 docx:
        $w = New-Object -ComObject Word.Application
        $d = $w.Documents.Open($src); $d.SaveAs2($dst, 12); $d.Close($false)
      用 SaveAs2，不要用 SaveAs([ref]...)。
    - zip 里 word/media/ 含目录条目，basename 为空，必须过滤，否则 open() 会抛 FileNotFoundError。
    - 同一张图可能被引用多次（页眉、重复插图），标记会重复出现，这是对的——它反映文档真实位置。
"""
import argparse
import json
import os
import re
import shutil
import sys
import zipfile

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

# 卷首标记：`1.2026年安徽省初中学业水平考试`、`2026年安徽省中考英语` 等
# 合并卷的卷首常落在表格单元格里，导出后形如 `/ 1.2026年安徽省初中学业水平考试`，
# 所以允许前置的 `/`、空格、序号，别只匹配「行首就是年份」。
YEAR_HEAD = re.compile(r"^\s*/?\s*\d{0,2}\s*[.．、]?\s*(20\d{2})\s*年\s*.{0,10}(学业水平|中考|毕业学业)")


def para_images(par, document):
    """按出现顺序取段落里引用的图片文件名（走 r:embed -> related_parts）。"""
    names = []
    for blip in par._p.iter(qn("a:blip")):
        rid = blip.get(qn("r:embed"))
        if not rid:
            continue
        part = document.part.related_parts.get(rid)
        if part is None:
            continue
        names.append(os.path.basename(str(part.partname)))
    return names


def build_lines(document):
    """按文档顺序产出正文行；返回 (lines, table_count, img_marks)。"""
    lines, ti, img_marks = [], 0, 0
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            par = Paragraph(child, document)
            t = par.text
            if t.strip():
                lines.append(t)
            for name in para_images(par, document):
                lines.append(f"[IMG {name}]")
                img_marks += 1
        elif child.tag.endswith("}tbl"):
            tb = Table(child, document)
            lines.append(f"[TABLE {ti} rows={len(tb.rows)} cols={len(tb.columns)}]")
            for r in tb.rows:
                lines.append(" | ".join(c.text.replace("\n", " / ").strip() for c in r.cells))
                for c in r.cells:
                    for par in c.paragraphs:
                        for name in para_images(par, document):
                            lines.append(f"[IMG {name}]")
                            img_marks += 1
            lines.append("[/TABLE]")
            ti += 1
    return lines, ti, img_marks


def split_by_year(lines):
    """按卷首标记切段，返回 [(year, start, end)]；只有一处或没有标记时返回空。"""
    marks = []
    for i, line in enumerate(lines):
        m = YEAR_HEAD.match(line)
        if m:
            marks.append((i, int(m.group(1))))
    if len(marks) < 2:
        return []
    spans = []
    for idx, (start, year) in enumerate(marks):
        end = marks[idx + 1][0] if idx + 1 < len(marks) else len(lines)
        spans.append((year, start, end))
    return spans


def main() -> int:
    ap = argparse.ArgumentParser(description="docx 原卷 → 正文 + 媒体")
    ap.add_argument("src")
    ap.add_argument("outdir")
    ap.add_argument("--split-by-year", action="store_true",
                    help="合并卷：按「20XX年…考试」切成每年一份（含各自的 media 子集）")
    ap.add_argument("--drop-first", type=int, default=0, metavar="N",
                    help="切分时每年丢掉开头 N 行（合并卷常有「答案链接☞答案册P1」这类页眉）")
    a = ap.parse_args()

    if not os.path.exists(a.src):
        print("文件不存在:", a.src)
        return 2
    os.makedirs(a.outdir, exist_ok=True)

    d = docx.Document(a.src)
    lines, n_tables, img_marks = build_lines(d)

    txt_path = os.path.join(a.outdir, "正文.txt")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    media_dir = os.path.join(a.outdir, "media")
    os.makedirs(media_dir, exist_ok=True)
    with zipfile.ZipFile(a.src) as z:
        names = [n for n in z.namelist()
                 if n.startswith("word/media/") and not n.endswith("/")]
        for n in names:
            with open(os.path.join(media_dir, os.path.basename(n)), "wb") as fh:
                fh.write(z.read(n))

    print(f"段落 {len(d.paragraphs)} | 表格 {n_tables} | 内嵌图 {len(d.inline_shapes)} "
          f"| 图片位置标记 {img_marks} | 媒体文件 {len(names)}")
    print(f"正文 -> {txt_path}")
    print(f"图片 -> {media_dir}")
    if len(names) > img_marks:
        print(f"提示: media 比位置标记多 {len(names) - img_marks} 个（页眉/未引用图），逐张确认归属再绑定")

    if a.split_by_year:
        spans = split_by_year(lines)
        if not spans:
            print("✗ 没找到 2 处以上「20XX年…考试」卷首标记，无法按年切分")
            return 1
        index = {}
        for year, start, end in spans:
            seg = lines[start + a.drop_first:end]
            # 卷首常是「[TABLE][/TABLE] 只包一行标题」：丢掉标题行后会剩下孤立的 [/TABLE]，
            # 这里把开头的残片一并去掉，免得每年第一行都是垃圾标记
            while seg and (seg[0].strip() in ("[/TABLE]",) or not seg[0].strip()):
                seg.pop(0)
            if not seg:
                continue
            year_dir = os.path.join(a.outdir, "by_year", str(year))
            os.makedirs(year_dir, exist_ok=True)
            with open(os.path.join(year_dir, "正文.txt"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(seg))
            # 只把该年段落引用到的图拷过去：合并卷的 imageN 是全文连续编号，
            # 直接复制整个 media/ 会让每年的 image1 变成别的年份的图
            used = []
            for line in seg:
                m = re.match(r"^\[IMG (.+?)\]$", line.strip())
                if m and m.group(1) not in used:
                    used.append(m.group(1))
            ymedia = os.path.join(year_dir, "media")
            os.makedirs(ymedia, exist_ok=True)
            missing = []
            for name in used:
                src_path = os.path.join(media_dir, name)
                if os.path.exists(src_path):
                    shutil.copy2(src_path, os.path.join(ymedia, name))
                else:
                    missing.append(name)
            index[str(year)] = {"start": start, "end": end, "lines": len(seg),
                                "images": used, "missing": missing}
            warn = f"（缺 {len(missing)} 张）" if missing else ""
            print(f"  {year}: 第 {start}–{end} 行，{len(seg)} 行，图 {len(used)} 张{warn}")
        with open(os.path.join(a.outdir, "by_year", "index.json"), "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=1)
        print(f"按年切分 -> {os.path.join(a.outdir, 'by_year')}（index.json 记录行号与图片归属）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
