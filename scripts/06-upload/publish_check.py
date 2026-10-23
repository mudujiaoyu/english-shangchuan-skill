# -*- coding: utf-8 -*-
"""发布闸门自检：列出会被 publish 拦下的单元，并区分「真缺陷」与「该类本就没有子类」。

    python publish_check.py --ids AH-2022
    python publish_check.py --batch b.json

检查项与服务端 `publish_blockers` 一致：
  missing_stem / missing_answer / missing_explanation / missing_question_type / missing_knowledge
外加：
  missing_subtype —— 仅当该主类在 filter-framework.json 里**列了子类**时才算缺陷
  invalid_type / invalid_subtype —— 不在目录内
"""
import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")


def _skill_root():
    d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(d, "SKILL.md")):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d


SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")
REMOTE = "ubuntu@101.43.1.57"
FRAMEWORK_LOCAL = os.path.join(_skill_root(), "references", "filter-framework.json")


def load_framework():
    """优先本地缓存，其次从服务器读。"""
    if os.path.exists(FRAMEWORK_LOCAL):
        return json.load(open(FRAMEWORK_LOCAL, encoding="utf-8"))
    script = ("import json;d=json.load(open('/home/ubuntu/mudu-quiz/static/filter-framework.json',"
              "encoding='utf-8'));print(json.dumps(d,ensure_ascii=False))")
    r = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                        REMOTE, "python3 -c \"" + script + "\""],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode == 0 and r.stdout.strip():
        d = json.loads(r.stdout)
        os.makedirs(os.path.dirname(FRAMEWORK_LOCAL), exist_ok=True)
        json.dump(d, open(FRAMEWORK_LOCAL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return d
    raise SystemExit("取不到 filter-framework.json（本地无缓存且 ssh 失败）")


def fetch(prefix):
    script = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = [list(r) for r in con.execute(
  "select questions.unit_id, stem, answer, explanation, question_type, knowledge_json, filter_metadata_json, "
  "unit_kind, material, subquestions_json, questions.difficulty from questions join question_units "
  "on question_units.id = questions.unit_id where unit_id like '{prefix}%'")]
print(json.dumps(rows, ensure_ascii=False))
'''
    r = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                        REMOTE, "python3 -"], input=script, capture_output=True,
                       text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit("ssh 失败: " + r.stderr[:200])
    return json.loads(r.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="单元 ID 前缀，如 AH-2022")
    ap.add_argument("--batch", help="批次 JSON")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--limit", type=int, default=20, help="明细最多打印几条")
    a = ap.parse_args()

    fw = load_framework()
    with_sub = {t["name"]: (t.get("subtypes") or []) for t in fw["question_types"]}
    types = set(with_sub)

    if a.batch:
        items = json.load(open(a.batch, encoding="utf-8-sig"))["items"]
        units = [(i.get("id"), i.get("stem"), i.get("answer"), i.get("explanation"),
                  i.get("type"), i.get("knowledge"), (i.get("filterMetadata") or {}),
                  i.get("unit_kind") or i.get("unitKind") or "standalone",
                  i.get("material") or "", i.get("subquestions") or [], i.get("difficulty") or "") for i in items]
    elif a.ids:
        units = [(u, s, ans, e, t, json.loads(kj or "[]"), json.loads(fm or "{}"), kind, mat,
                  json.loads(sj or "[]"), diff or "")
                 for u, s, ans, e, t, kj, fm, kind, mat, sj, diff in fetch(a.ids)]
    else:
        ap.error("需要 --ids 或 --batch")

    blockers, rows, no_explanation = {}, [], []
    legacy_difficulty = []
    blank_spaces = []
    for uid, stem, ans, exp, qtype, knowledge, fm, kind, material, subs_q, diff in units:
        b = []
        if not (stem or "").strip():
            b.append("missing_stem")
        if not (ans or "").strip():
            b.append("missing_answer")
        if not (exp or "").strip():
            no_explanation.append(uid)
        if (diff or "").strip() not in ("", "容易", "适中", "困难"):
            legacy_difficulty.append((uid, diff))
        if stem and "\u3000\u3000" in stem:
            blank_spaces.append(uid)
        if not (qtype or "").strip():
            b.append("missing_question_type")
        elif qtype not in types:
            b.append("invalid_type")
        if not knowledge:
            b.append("missing_knowledge")
        # 组题：材料与子题完整性（与服务端 publish_blockers 一致）
        if kind == "group":
            if not (material or "").strip() or not subs_q:
                b.append("incomplete_group_unit")
            else:
                bad_subs = [q for q in subs_q if isinstance(q, dict)
                            and (not (q.get("stem") or "").strip() or not (q.get("answer") or "").strip())]
                if bad_subs:
                    b.append("incomplete_group_subquestions")
        subs = fm.get("subtypes") or []
        if with_sub.get(qtype) and not subs:
            b.append("missing_subtype")
        bad = [s for s in subs if with_sub.get(qtype) and s not in with_sub[qtype]]
        if bad:
            b.append("invalid_subtype:" + ",".join(bad))
        for x in b:
            blockers[x] = blockers.get(x, 0) + 1
        if b:
            rows.append((uid, qtype, b))

    print(f"检查 {len(units)} 个单元")
    print(f"解析为空 {len(no_explanation)} 个（不阻断发布，仅提示）")
    if legacy_difficulty:
        print(f"非标准难度标签 {len(legacy_difficulty)} 个（应统一为 容易/适中/困难）：{legacy_difficulty[:6]}")
    if blank_spaces:
        print(f"题干用全角空格代替下划线 {len(blank_spaces)} 个（建议改成 ______）：{blank_spaces[:6]}")
    if blockers:
        print("阻断项:", json.dumps(blockers, ensure_ascii=False))
        print(f"受影响单元 {len(rows)} 个：")
        for uid, qtype, b in rows[:a.limit]:
            print(f"  {uid:16s} {qtype:12s} {', '.join(b)}")
        if len(rows) > a.limit:
            print(f"  … 其余 {len(rows) - a.limit} 个")
    else:
        print("✓ 无阻断项，可发布")

    if a.json:
        print(json.dumps({"total": len(units), "blockers": blockers,
                          "units": [{"id": u, "type": t, "blockers": b} for u, t, b in rows]},
                         ensure_ascii=False, indent=1))
    return 0 if not blockers else 1


if __name__ == "__main__":
    raise SystemExit(main())
