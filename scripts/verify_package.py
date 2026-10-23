# -*- coding: utf-8 -*-
"""技能自检：阶段文档、脚本、编译、契约；--run 跑 smoke test。

    python scripts/verify_package.py
    python scripts/verify_package.py --run
"""
import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)

STAGES = [
    ("01-extract", "01-extract", ["extract_docx.py", "pdf_extract.py"]),
    ("02-audio", "02-audio", ["cut_audio.py"]),
    ("03-type-map", None, []),
    ("04-knowledge", "04-knowledge", ["find_kp.py", "check_tags.py", "apply_type_tags.py",
                                      "fill_subtags.py", "spell_pos.py", "retag_drafts.py", "assign_angle.py"]),
    ("05-meta", "05-meta", ["assign_meta.py"]),
    ("06-upload", "06-upload", ["check_duplicates.py", "preflight_check.py", "patch_attachments.py", "publish_check.py"]),
]
REFS = ["structure.md", "pdf-extraction.md", "audio-splitting.md", "type-subtypes.md",
        "knowledge-tagging.md", "knowledge-matching-rules.md", "knowledge-catalog.json",
        "type-knowledge-map.json", "difficulty-category.json", "upload-api.md"]


def frontmatter(path):
    try:
        text = open(path, encoding="utf-8").read()
    except FileNotFoundError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    meta = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def compile_all(d):
    bad = []
    for root, _dirs, files in os.walk(d):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                r = subprocess.run([sys.executable, "-m", "py_compile", p],
                                   capture_output=True, text=True)
                if r.returncode != 0:
                    bad.append(os.path.relpath(p, d))
    return bad


def call(script, args, allow_dup=False):
    p = os.path.join(HERE, script)
    r = subprocess.run([sys.executable, p] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    ok = r.returncode == 0 or (allow_dup and r.returncode == 1)
    out = (r.stdout or r.stderr or "").strip().splitlines()[:2]
    return ok, r.returncode, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    fails = 0

    meta = frontmatter(os.path.join(SKILL, "SKILL.md"))
    name_ok = meta.get("name") == "mudu-question-upload" and bool(meta.get("description"))
    print(f"SKILL.md 元数据: {'✓' if name_ok else '✗'}")
    if not name_ok:
        fails += 1

    print("\n阶段文档")
    for slug, _d, _s in STAGES:
        p = os.path.join(SKILL, "references", "stages", slug + ".md")
        ok = os.path.exists(p)
        size = os.path.getsize(p) if ok else 0
        print(f"  {slug:12s} {'✓' if ok else '✗'} {size:>6d} 字节")
        if not ok:
            fails += 1

    print("\n共享参考")
    for r in REFS:
        p = os.path.join(SKILL, "references", r)
        ok = os.path.exists(p)
        print(f"  {r:28s} {'✓' if ok else '✗'}")
        if not ok:
            fails += 1

    print("\n脚本")
    for slug, d, scripts in STAGES:
        if not d:
            continue
        for s in scripts:
            p = os.path.join(HERE, d, s)
            ok = os.path.exists(p)
            if not ok:
                print(f"  {d}/{s:24s} ✗")
                fails += 1
    bad = compile_all(HERE)
    print(f"  编译: {'✓ 全部通过' if not bad else '✗ ' + str(bad)}")
    if bad:
        fails += 1

    if a.run:
        print("\nSmoke test")
        dur = r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\_api\durations.json"
        batch = r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\_api\batch_2022.json"
        checks = [("知识点检索 find_kp", "04-knowledge/find_kp.py", ["句意理解"], False),
                  ("标签体检 check_tags", "04-knowledge/check_tags.py", ["--ids", "AH-2022"], False),
                  ("难度评估 assign_meta", "05-meta/assign_meta.py",
                   ["--ids", "AH-2022"] + (["--durations", dur] if os.path.exists(dur) else []), False)]
        if os.path.exists(batch):
            checks.append(("查重闸门 check_duplicates", "06-upload/check_duplicates.py",
                           ["--batch", batch], True))
        for label, script, args, allow_dup in checks:
            ok, code, out = call(script, args, allow_dup)
            print(f"  {label:24s} {'通过' if ok else '失败'} (exit {code})")
            for line in out:
                print(f"      {line[:100]}")
            if not ok:
                fails += 1

    print("\n结论:", "全部通过" if fails == 0 else f"{fails} 项待修")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
