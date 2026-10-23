# -*- coding: utf-8 -*-
"""题干/选项排版体检：括号、破折号、引号、空格、下划线、标点混用。

    python check_text.py --ids AH            # 只看安徽卷
    python check_text.py                     # 全库
    python check_text.py --ids AH --json

只报告，不阻断（`--strict` 时有问题就返回 1）。
"""
import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")


def _skill_root():
    d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(d, "SKILL.md")):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d


SSH = os.path.expanduser(r"~\.ssh\mudu_gd")

RULES = [
    ("全角空格档", lambda s: "\u3000\u3000" in s),
    ("双空格", lambda s: re.search(r"[A-Za-z]  +[A-Za-z]", s) is not None),
    ("括号不配对", lambda s: s.count("(") != s.count(")") or s.count("（") != s.count("）")),
    ("中英括号混用", lambda s: ("（" in s and ")" in s) or ("(" in s and "）" in s)),
    ("破折号后缺空格", lambda s: any(
        re.search(r"[A-Za-z,.;?]—(?=[A-Za-z])", line) for line in s.splitlines())),
    ("连字符破折号", lambda s: "--" in s and not s.strip().startswith("--")),
    ("中文标点入英文句", lambda s: re.search(r"[A-Za-z][，。；：？！]", s) is not None),
    ("引号不配对", lambda s: s.count('"') % 2 == 1 or s.count("“") != s.count("”")),
    ("重复标点", lambda s: re.search(r"[.。]{2,}|[!?！？]{2,}", s) is not None),
    ("下划线过短", lambda s: re.search(r"(?<!_)_{1,4}(?!_)", s) is not None),
    ("空档只有空格", lambda s: re.search(r"\bto\s{2,}\b", s) is not None),
    ("题干首尾空白/标点", lambda s: s != s.strip() or bool(re.match(r"^[.,;:，。；：]", s.strip()))),
    ("选项标点混用", lambda s: "\uff0e" in s),
]


def fetch(prefix):
    script = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = [list(r) for r in con.execute(
  "select unit_id, question_type, stem, options_json, subquestions_json from questions "
  "where unit_id like '{prefix}%'")]
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          "ubuntu@101.43.1.57", "python3 -"], input=script,
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 失败: " + out.stderr[:200])
    return json.loads(out.stdout)


def fetch_batch(path):
    """直接扫批次 json（确认之前也能查排版）。"""
    batch = json.load(open(path, encoding="utf-8-sig"))
    rows = []
    for it in batch.get("items") or []:
        rows.append([it.get("id"), it.get("type"), it.get("stem") or "",
                     json.dumps(it.get("options") or [], ensure_ascii=False),
                     json.dumps(it.get("subquestions") or [], ensure_ascii=False)])
    return rows


def mask_numbered_blanks(text):
    """`__31__` 是「第 31 空」的标记，不是过短下划线，先统一成 6 个下划线再体检。"""
    return re.sub(r"_{2,}\s*(\d{1,3})\s*_{2,}", "______", text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--batch", default="", help="直接扫批次 json（上传前用）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    rows = fetch_batch(a.batch) if a.batch else fetch(a.ids)
    hits = defaultdict(list)
    texts = 0
    for uid, qt, stem, opts, sj in rows:
        samples = [("题干", stem or "")]
        for o in json.loads(opts or "[]"):
            if isinstance(o, str):
                samples.append(("选项", o))
        for s in json.loads(sj or "[]"):
            samples.append((f"子题{s.get('number')}", s.get("stem") or ""))
            for o in s.get("options") or []:
                if isinstance(o, str):
                    samples.append(("子选项", o))
        for where, text in samples:
            if not text:
                continue
            texts += 1
            probe = mask_numbered_blanks(text)
            for name, fn in RULES:
                if fn(probe):
                    hits[name].append((uid, qt, where, text[:70]))

    # 完形/选词：子题必须 4 个选项、题干非空
    cloze_bad = []
    for uid, qt, stem, opts, sj in rows:
        if qt not in ("完形填空", "选词填空", "短文填空", "教材语篇填空"):
            continue
        for s in json.loads(sj or "[]"):
            o = s.get("options") or []
            if len(o) != 4 or not (s.get("stem") or "").strip():
                cloze_bad.append((uid, s.get("number"), len(o)))
    if cloze_bad:
        hits["完形选项异常"].extend([(u, "", f"子题{n}", f"{len(o)} 个选项") for u, n, o in cloze_bad])

    total = sum(len(v) for v in hits.values())
    print(f"扫描 {len(rows)} 个单元 / {texts} 段文本")
    print(f"命中 {total} 处，分 {len(hits)} 类\n")
    for name, items in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        units = len({i[0] for i in items})
        print(f"{name}：{len(items)} 处 / {units} 个单元")
        for uid, qt, where, text in items[:a.limit]:
            print(f"    {uid} [{qt}] {where}: {text!r}")
    if a.json:
        print(json.dumps({k: [list(x) for x in v] for k, v in hits.items()}, ensure_ascii=False, indent=1))
    return 1 if (a.strict and total) else 0


if __name__ == "__main__":
    raise SystemExit(main())
