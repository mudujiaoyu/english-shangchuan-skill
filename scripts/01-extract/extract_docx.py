# -*- coding: utf-8 -*-
"""把 .docx 原卷拆成 正文.txt（含 [TABLE]/[IMG] 标记）+ media/ 图片目录。

用法:
    python extract_docx.py "<原卷.docx>" "<输出目录>"

输出:
    <输出目录>/正文.txt     按文档顺序，段落原样，表格用 [TABLE i rows=x cols=y] 包住，
                            内嵌图片在所在段落之后单独一行留 `[IMG image5.jpeg]` 位置标记
    <输出目录>/media/       内嵌图片，保留原文件名（image1.png / image10.jpeg ...）

为什么要留 [IMG] 标记：
    只给 media/ 目录时，「哪张图属于哪道题」只能靠文件名序号反推，logo/二维码/栏目角标混在一起，
    图片题的起点每年都要肉眼重认（历史事故：2020 阅读 A 整篇是图、2021 选项图从 image4 起）。
    有了位置标记，正文里就能直接看到图落在哪个题号之间。

注意:
    - .doc（老二进制）先用 Word COM 转 docx:
        $w = New-Object -ComObject Word.Application
        $d = $w.Documents.Open($src); $d.SaveAs2($dst, 12); $d.Close($false)
      用 SaveAs2，不要用 SaveAs([ref]...)。
    - zip 里 word/media/ 含目录条目，basename 为空，必须过滤，否则 open() 会抛 FileNotFoundError。
    - 同一张图可能被引用多次（页眉、重复插图），标记会重复出现，这是对的——它反映文档真实位置。
"""
import os
import sys
import zipfile

import docx
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph


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


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)

    d = docx.Document(src)
    lines, ti, img_marks = [], 0, 0
    for child in d.element.body.iterchildren():
        if child.tag.endswith("}p"):
            par = Paragraph(child, d)
            t = par.text
            if t.strip():
                lines.append(t)
            for name in para_images(par, d):
                lines.append(f"[IMG {name}]")
                img_marks += 1
        elif child.tag.endswith("}tbl"):
            tb = Table(child, d)
            lines.append(f"[TABLE {ti} rows={len(tb.rows)} cols={len(tb.columns)}]")
            for r in tb.rows:
                lines.append(" | ".join(c.text.replace("\n", " / ").strip() for c in r.cells))
                for c in r.cells:
                    for par in c.paragraphs:
                        for name in para_images(par, d):
                            lines.append(f"[IMG {name}]")
                            img_marks += 1
            lines.append("[/TABLE]")
            ti += 1

    txt_path = os.path.join(outdir, "正文.txt")
    with open(txt_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    media_dir = os.path.join(outdir, "media")
    os.makedirs(media_dir, exist_ok=True)
    with zipfile.ZipFile(src) as z:
        names = [n for n in z.namelist()
                 if n.startswith("word/media/") and not n.endswith("/")]
        for n in names:
            with open(os.path.join(media_dir, os.path.basename(n)), "wb") as fh:
                fh.write(z.read(n))

    print(f"段落 {len(d.paragraphs)} | 表格 {len(d.tables)} | 内嵌图 {len(d.inline_shapes)} "
          f"| 图片位置标记 {img_marks} | 媒体文件 {len(names)}")
    print(f"正文 -> {txt_path}")
    print(f"图片 -> {media_dir}")
    if len(names) > img_marks:
        print(f"提示: media 比位置标记多 {len(names) - img_marks} 个（页眉/未引用图），逐张确认归属再绑定")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
