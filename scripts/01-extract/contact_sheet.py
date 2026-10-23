# -*- coding: utf-8 -*-
"""把 media/ 里的图拼成一张缩略图清单，用人眼一次性确认「哪张图是哪道题」。

    python contact_sheet.py 01_source/media/ --out 01_source/contact_sheet.png
    python contact_sheet.py 01_source/media/ --cols 5 --cell 360

为什么要它：
    图片题绑定最容易错在起点（历史事故：把页眉 logo、二维码、「新语法」栏目角标当成选项图）。
    一张拼版图 + 文件名 + 原始尺寸，扫一眼就能排掉非选项图，再对照 正文.txt 里的 [IMG] 标记定归属。

输出：默认 `<目录>/../contact_sheet.png`，每格标注 `文件名 [宽x高]`。
"""
import argparse
import os
import re
import sys

from PIL import Image, ImageDraw


def natural_key(path):
    name = os.path.basename(path)
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def main():
    ap = argparse.ArgumentParser(description="生成图片缩略图清单")
    ap.add_argument("media_dir")
    ap.add_argument("--out", default="")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--cell", type=int, default=320, help="单格像素（含标题行）")
    ap.add_argument("--pattern", default=".*", help="只收文件名匹配该正则的图（默认全部）")
    a = ap.parse_args()

    if not os.path.isdir(a.media_dir):
        raise SystemExit(f"目录不存在: {a.media_dir}")
    rx = re.compile(a.pattern)
    files = [os.path.join(a.media_dir, f) for f in os.listdir(a.media_dir)
             if rx.search(f) and f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))]
    if not files:
        raise SystemExit(f"{a.media_dir} 里没有图片")
    files.sort(key=natural_key)

    cell, cols = a.cell, max(1, a.cols)
    rows = (len(files) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 20)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, path in enumerate(files):
        im = Image.open(path)
        w, h = im.size
        thumb = im.convert("RGB")
        thumb.thumbnail((cell - 8, cell - 8))
        x, y = (i % cols) * cell, (i // cols) * (cell + 20)
        sheet.paste(thumb, (x + 4, y + 20))
        draw.text((x + 4, y + 4), f"{os.path.basename(path)} [{w}x{h}]", fill="black")

    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.media_dir)), "contact_sheet.png")
    sheet.save(out)
    print(f"{len(files)} 张图 -> {out}（{sheet.width}x{sheet.height}）")
    print("逐张确认：页眉 logo / 二维码 / 栏目角标 / 装饰图 都不算选项图。")
    for path in files:
        im = Image.open(path)
        print(f"  {os.path.basename(path):20s} {im.size[0]:>5d}x{im.size[1]:<5d} {os.path.getsize(path):>8d} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
