# -*- coding: utf-8 -*-
"""从答案册（docx 或已导出的 txt）抽出「题号 → 答案」表，落 answers.json。

    python extract_answers.py --docx 答案.docx --year 2025 --out 01_source_ans/answers.json
    python extract_answers.py --txt 答案.txt --year 2020 --out answers.json

为什么不用手抄：
    答案是唯一不能错的东西，手抄一张 80 题的答案表既有抄错风险（2019 第 19、20 题填反），
    又要在每次录题时重来一遍。这个脚本把手抄换成「机器抽表 + check_answers.py 比对」，
    两边都错才会漏（一个来自答案册原文，一个来自批次）。

支持两种形态：
    1) 表格：`题号 | 1~5 | 6~10` / `答案 | CBCAC | BBAAC`，按单元格一一配对后展开区间；
    2) 文本：`1~5 CBCAC`、`21.C　【解析】…`、`16.Silence/silence　17.Smile …`，
       按全角空格切块，每块必须是「题号.+答案」或「区间+字母串」。
    解析（【解析】及其后内容）不取。遇到「听力录音材料」章节即停止，避免把听力稿当答案。

输出结构：
    {"year": 2025, "count": 80,
     "numbers": {"1": "C", "16": "Silence/silence", ...},
     "subjective": [73, 74, 75],
     "conflicts": [[题号, 旧值, 新值]], "skipped": [...], "sources": {...}}
"""
import argparse
import json
import os
import re
import sys

STOP_MARKERS = ("听力录音材料", "录音材料", "参考答案及解析", "【听力材料】")
RANGE_RE = re.compile(r"^\s*(\d{1,3})\s*[~～\-—至]\s*(\d{1,3})\s*[:：]?\s*([A-Ga-g]{2,12})\s*$")
PAIR_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、]\s*(.+?)\s*$")
LETTER_RE = re.compile(r"^[A-Ga-g]$")
CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
TAIL = " \t。.,;；:：!！?？\"'“”‘’"


def clean_value(raw):
    """去掉【解析】及其后内容，返回 (值, 是否主观题)。

    判定顺序：
      1. 单字母 A–G → 客观题答案；
      2. 不含任何中日韩字符/全角标点，且以字母开头 → 主观题答案（保留原句，去尾部标点）；
      3. 其余（含中文说明，如写作要求「1.文体:记叙文。」）→ 丢弃。
    """
    value = re.split(r"【解析】|【分析】|解析[:：]", raw)[0].strip(TAIL + "　")
    # 主观答案常带中文括注：(言之有理即可)（不超过15个词），去掉再判语种
    value = re.sub(r"[（(][^()（）]*[\u4e00-\u9fff][^()（）]*[）)]\s*$", "", value).strip(TAIL + "　")
    if LETTER_RE.match(value):
        return value.upper(), False
    if not value or not re.match(r"^[A-Za-z]", value) or CJK_RE.search(value):
        return None, None
    if len(value) > 120:
        return None, None
    return value.rstrip(TAIL), True


def parse_chunks(line, out, conflicts, skipped):
    """把一行按全角空格/制表符切块，逐块认「题号.答案」。"""
    for chunk in re.split(r"[\u3000\t]+", line):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = RANGE_RE.match(chunk)
        if m:
            lo, hi, letters = int(m.group(1)), int(m.group(2)), m.group(3).upper()
            if hi - lo + 1 == len(letters):
                for i, ch in enumerate(letters):
                    put(out, conflicts, lo + i, ch, False)
            else:
                skipped.append(f"区间长度不符: {chunk}")
            continue
        m = PAIR_RE.match(chunk)
        if not m:
            continue
        num = int(m.group(1))
        if not 1 <= num <= 200:
            continue
        value, subjective = clean_value(m.group(2))
        if value is None:
            continue
        put(out, conflicts, num, value, subjective)


def put(out, conflicts, num, value, subjective):
    if num in out and out[num]["value"] != value:
        conflicts.append([num, out[num]["value"], value])
        return
    out[num] = {"value": value, "subjective": bool(subjective)}


def table_answers(tables, out, conflicts):
    """题号行 + 答案行 按单元格配对。"""
    for rows in tables:
        headers = None
        for row in rows:
            cells = [c.strip() for c in row]
            if not cells:
                continue
            head = cells[0]
            if "题号" in head:
                headers = cells[1:]
                continue
            if headers and "答案" in head:
                for header, cell in zip(headers, cells[1:]):
                    m = re.match(r"^\s*(\d{1,3})\s*[~～\-—]\s*(\d{1,3})\s*$", header)
                    letters = re.sub(r"[\s　]", "", cell).upper()
                    if m and letters and re.fullmatch(r"[A-G]+", letters):
                        lo, hi = int(m.group(1)), int(m.group(2))
                        if hi - lo + 1 == len(letters):
                            for i, ch in enumerate(letters):
                                put(out, conflicts, lo + i, ch, False)
                headers = None


def docx_lines(path):
    import docx
    d = docx.Document(path)
    lines, tables = [], []
    for child in d.element.body.iterchildren():
        if child.tag.endswith("}p"):
            t = "".join(node.text or "" for node in child.iter() if node.tag.endswith("}t"))
            if t.strip():
                lines.append(t)
        elif child.tag.endswith("}tbl"):
            rows = []
            for tr in child.iter():
                if not tr.tag.endswith("}tr"):
                    continue
                cells = []
                for tc in tr:
                    if not tc.tag.endswith("}tc"):
                        continue
                    cells.append("".join(n.text or "" for n in tc.iter() if n.tag.endswith("}t")))
                if cells:
                    rows.append(cells)
            tables.append(rows)
            lines.append(" | ".join("".join(r) for r in rows))
    return lines, tables


def main():
    ap = argparse.ArgumentParser(description="答案册 → 题号答案表")
    ap.add_argument("--docx")
    ap.add_argument("--txt")
    ap.add_argument("--year", type=int, default=0)
    ap.add_argument("--out", default="answers.json")
    a = ap.parse_args()
    if not (a.docx or a.txt):
        ap.error("给 --docx 或 --txt")

    if a.docx:
        lines, tables = docx_lines(a.docx)
    else:
        tables = []
        lines = [l for l in open(a.txt, encoding="utf-8-sig").read().splitlines() if l.strip()]

    out, conflicts, skipped = {}, [], []
    if tables:
        table_answers(tables, out, conflicts)
    for line in lines:
        if any(mark in line for mark in STOP_MARKERS):
            break
        parse_chunks(line, out, conflicts, skipped)

    numbers = {str(k): out[k]["value"] for k in sorted(out)}
    subjective = sorted(k for k, v in out.items() if v["subjective"])
    payload = {
        "year": a.year or None,
        "count": len(numbers),
        "numbers": numbers,
        "subjective": subjective,
        "conflicts": conflicts,
        "skipped": skipped[:20],
        "sources": {"docx": os.path.abspath(a.docx) if a.docx else None,
                    "txt": os.path.abspath(a.txt) if a.txt else None},
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)

    letters = sum(1 for v in numbers.values() if LETTER_RE.match(v))
    print(f"抽出 {len(numbers)} 题（客观 {letters} / 其他 {len(numbers) - letters}）| 冲突 {len(conflicts)} "
          f"| 跳过 {len(skipped)} -> {a.out}")
    if numbers:
        ks = sorted(int(k) for k in numbers)
        print(f"题号范围 {ks[0]}–{ks[-1]}；缺号: "
              f"{[n for n in range(ks[0], ks[-1] + 1) if str(n) not in numbers][:20] or '无'}")
    for c in conflicts[:10]:
        print(f"  CONFLICT 第{c[0]}题: 已记 {c[1]} / 又见 {c[2]}")
    for s in skipped[:5]:
        print(f"  SKIP {s}")
    if not numbers:
        print("没抽到任何答案：检查 --docx/--txt 是否给对，或答案册版式是否需要扩规则")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
