# -*- coding: utf-8 -*-
"""从答案册 docx 里抽「附:听力录音材料」，按大题切成可写入 material 的段落。

    python extract_script.py --docx 答案.docx --year 2022 --out ts.json
    python extract_script.py --docx 答案.docx --list      # 看有哪些年份

输出：
{
  "2022": {
    "short": ["Text1 全文", "Text2 全文", ...],   # Ⅰ 短对话，逐题
    "long": ["6~7 对话全文", "8~10 对话全文"],     # Ⅱ 长对话，逐段
    "passage": "Ⅲ 短文全文",
    "conversion": "Ⅳ 信息转换全文"
  }
}
"""
import argparse
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
import docx


def load(path):
    return [p.text.strip() for p in docx.Document(path).paragraphs if p.text.strip()]


def find_blocks(paras):
    """返回 [(year, 起始段, 结束段)]，每块以「附:听力录音材料」为界。"""
    years = [(i, re.search(r"(20\d\d)年", x).group(1)) for i, x in enumerate(paras)
             if "初中学业水平考试" in x and re.search(r"(20\d\d)年", x)]
    blocks = []
    for idx, (pos, year) in enumerate(years):
        end = years[idx + 1][0] if idx + 1 < len(years) else len(paras)
        blocks.append((year, pos, end))
    return blocks


def parse_tape(paras, start, end):
    """按 Ⅰ/Ⅱ/Ⅲ/Ⅳ 切段，再各自按题号或「听下面一段」细分。"""
    lines = paras[start + 1:end]
    sections, cur_sec = {}, None
    for line in lines:
        m = re.match(r"^([ⅠⅡⅢⅣ])\s*[.．]?", line)
        if m and len(line) < 20:
            cur_sec = m.group(1)
            sections.setdefault(cur_sec, [])
            continue
        if cur_sec:
            sections[cur_sec].append(line)

    out = {"short": [], "long": [], "passage": "", "conversion": ""}
    # Ⅰ 短对话：按 1. 2. ... 切
    cur = []
    for line in sections.get("Ⅰ", []):
        m = re.match(r"^(\d{1,2})\s*[.．](.*)", line)
        if m and int(m.group(1)) <= 5:
            if cur:
                out["short"].append("\n".join(cur).strip())
            cur = [m.group(2).strip()]
        else:
            cur.append(line)
    if cur:
        out["short"].append("\n".join(cur).strip())
    # 有的年份用 Text 1: 分隔，没切开时再按此切一次
    if len(out["short"]) <= 1 and any(re.match(r"^Text\s*\d", x) for x in sections.get("Ⅰ", [])):
        text = "\n".join(sections.get("Ⅰ", []))
        parts = re.split(r"(?m)^Text\s*\d+\s*[:：]?\s*", text)
        out["short"] = [x.strip() for x in parts if x.strip()]

    # Ⅱ 长对话：按「听下面一段」切
    cur = []
    for line in sections.get("Ⅱ", []):
        if line.startswith("听下面一段"):
            if cur:
                out["long"].append("\n".join(cur).strip())
            cur = []
            continue
        cur.append(line)
    if cur:
        out["long"].append("\n".join(cur).strip())

    out["passage"] = "\n".join(sections.get("Ⅲ", [])).strip()
    out["conversion"] = "\n".join(sections.get("Ⅳ", [])).strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docx", required=True)
    ap.add_argument("--year")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()

    paras = load(a.docx)
    blocks = find_blocks(paras)
    if a.list:
        for y, s, e in blocks:
            print(f"  {y}: 段落 {s}~{e}")
        return 0

    want = [b for b in blocks if not a.year or b[0] == a.year]
    if not want:
        raise SystemExit("没找到该年份的录音材料")

    result = {}
    from collections import Counter
    for year, s, e in want:
        tape_start = next((i for i in range(s, e) if "听力录音材料" in paras[i]), None)
        if tape_start is None:
            continue
        data = parse_tape(paras, tape_start, e)
        # 长对话按「第X~Y题」重新切，避免把短文并进来
        result[year] = data
        print(f"{year}: 短对话 {len(data['short'])} 段 | 长对话 {len(data['long'])} 段 | "
              f"短文 {len(data['passage'])} 字 | 信息转换 {len(data['conversion'])} 字")

    if a.out:
        json.dump(result, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写出:", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
