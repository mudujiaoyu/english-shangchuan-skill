# -*- coding: utf-8 -*-
"""技能包汇总校验：目录、frontmatter、必需文件、脚本编译、交接契约；--run 跑 smoke test。

    python verify_package.py
    python verify_package.py --run
"""
import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
PIPE = os.path.dirname(HERE)
SKILLS = os.path.dirname(PIPE)
STAGES = ["mudu-extract", "mudu-audio", "mudu-type-map",
          "mudu-knowledge", "mudu-meta", "mudu-upload"]
REQUIRED = {
    "mudu-extract": ["SKILL.md", "scripts/extract_docx.py", "scripts/pdf_extract.py",
                     "references/structure.md", "references/pdf-extraction.md"],
    "mudu-audio": ["SKILL.md", "scripts/cut_audio.py", "references/audio-splitting.md"],
    "mudu-type-map": ["SKILL.md", "references/type-subtypes.md"],
    "mudu-knowledge": ["SKILL.md", "scripts/find_kp.py", "scripts/check_tags.py",
                       "scripts/apply_type_tags.py", "scripts/fill_subtags.py",
                       "scripts/spell_pos.py", "scripts/retag_drafts.py",
                       "references/knowledge-catalog.json", "references/knowledge-tagging.md",
                       "references/knowledge-matching-rules.md", "references/type-knowledge-map.json"],
    "mudu-meta": ["SKILL.md", "scripts/assign_meta.py", "references/difficulty-category.json"],
    "mudu-upload": ["SKILL.md", "scripts/check_duplicates.py", "scripts/preflight_check.py",
                    "scripts/patch_attachments.py", "references/upload-api.md"],
    "mudu-pipeline": ["SKILL.md", "references/package-manifest.json"],
}


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
                    bad.append((os.path.relpath(p, d), r.stderr.strip().splitlines()[-1] if r.stderr else ""))
    return bad


def run_smoke():
    results = []
    kn = os.path.join(SKILLS, "mudu-knowledge")
    meta = os.path.join(SKILLS, "mudu-meta")
    up = os.path.join(SKILLS, "mudu-upload")

    def call(script, args, expect="ok"):
        p = os.path.join(kn if "find_kp" in script or "check_tags" in script else
                         meta if "assign_meta" in script else up, "scripts", script)
        r = subprocess.run([sys.executable, p] + args, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        ok = (r.returncode == 0) if expect == "ok" else (r.returncode in (0, 1))
        return ok, r.returncode, (r.stdout or r.stderr or "").strip().splitlines()[:2]

    results.append(("知识点检索 find_kp", *call("find_kp.py", ["句意理解"])))
    results.append(("标签体检 check_tags", *call("check_tags.py", ["--ids", "AH-2022"])))
    dur = r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\_api\durations.json"
    args = ["--ids", "AH-2022"] + (["--durations", dur] if os.path.exists(dur) else [])
    results.append(("难度评估 assign_meta", *call("assign_meta.py", args)))

    batch = r"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\_api\batch_2022.json"
    if os.path.exists(batch):
        results.append(("查重闸门 check_duplicates", *call("check_duplicates.py", ["--batch", batch], "either")))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()

    fails = 0
    print(f"{'技能包':18s} {'SKILL':6s} {'文件':6s} {'脚本':6s} 说明")
    print("-" * 72)
    for name in STAGES + ["mudu-pipeline"]:
        d = os.path.join(SKILLS, name)
        if not os.path.isdir(d):
            print(f"{name:18s} 缺失")
            fails += 1
            continue
        meta = frontmatter(os.path.join(d, "SKILL.md"))
        skill_ok = meta.get("name") == name and bool(meta.get("description"))
        missing = [f for f in REQUIRED[name] if not os.path.exists(os.path.join(d, f))]
        bad = compile_all(d)
        status = []
        if not skill_ok:
            status.append("frontmatter 不符")
        if missing:
            status.append(f"缺 {len(missing)} 文件: {missing[:2]}")
        if bad:
            status.append(f"编译失败 {bad[:1]}")
        if status:
            fails += 1
        print(f"{name:18s} {'✓' if skill_ok else '✗':6s} "
              f"{'✓' if not missing else '✗':6s} {'✓' if not bad else '✗':6s} {'; '.join(status) or 'ok'}")

    man = os.path.join(PIPE, "references", "package-manifest.json")
    if os.path.exists(man):
        m = json.load(open(man, encoding="utf-8"))
        got = [s["skill"] for s in m["stages"]]
        if got != STAGES:
            print("清单与目录不一致:", got)
            fails += 1
        else:
            print("\n交接契约清单: 6 个阶段齐全")
    else:
        print("缺 package-manifest.json")
        fails += 1

    if a.run:
        print("\nSmoke test")
        for name, ok, code, out in run_smoke():
            print(f"  {name:24s} {'通过' if ok else '失败'} (exit {code})")
            for line in out:
                print(f"      {line[:100]}")
            if not ok:
                fails += 1

    print("\n结论:", "全部通过" if fails == 0 else f"{fails} 项待修")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
