# -*- coding: utf-8 -*-
"""给听力单元补「设题角度/听力」标签（知识点目录 1.1 新增维度）。

判定按题干设问：
  where                              → 地点推断
  who / whose / whom / relationship  → 人物关系
  why / learn / suggest / infer / mean / think of → 推理判断
  main idea / mainly / title / topic → 主旨大意
  其余（含信息转换空题干、判断、排序）→ 细节理解

    python assign_angle.py --ids AH-2022        # 干跑
    python assign_angle.py --ids AH-2022 --apply
    python assign_angle.py --all --apply        # 全库听力

注意：`听力关键词语选择` 的对照表不含设题角度，脚本会跳过。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")


def _skill_root():
    d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(d, "SKILL.md")):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d


SKILL = _skill_root()
INDEX = os.path.join(SKILL, "references", "knowledge-catalog.json")
KEY = open(os.path.expanduser(r"~\.mudu\api_key.txt"), encoding="ascii").read().strip()
BASE = "http://127.0.0.1:8089/api"
SSH = os.path.expanduser(r"~\.ssh\mudu_gd")

RULES = [
    ("地点推断", re.compile(r"\b(where|which place|what place)\b", re.I)),
    ("人物关系", re.compile(r"\b(who|whose|whom|relationship|relation)\b", re.I)),
    ("推理判断", re.compile(r"\b(why|what can we learn|suggest|infer|mean|think of|attitude)\b", re.I)),
    ("主旨大意", re.compile(r"\b(main idea|mainly|best title|title|topic|purpose)\b", re.I)),
]


def angle_of(text):
    for name, rx in RULES:
        if rx.search(text or ""):
            return name
    return "细节理解"


def fetch(prefix):
    script = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = [list(r) for r in con.execute(
  "select unit_id, question_type, stem, subquestions_json, knowledge_json, knowledge_ids_json "
  "from questions where question_type like '听力%' and unit_id like '{prefix}%'")]
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          "ubuntu@101.43.1.57", "python3 -"], input=script,
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 失败: " + out.stderr[:200])
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--recompute", action="store_true",
                    help="重算：先去掉已有的 设题角度/听力/*，再按子题重打（默认只补缺失）")
    a = ap.parse_args()
    prefix = "" if a.all else a.ids

    idx = json.load(open(INDEX, encoding="utf-8"))["points"]
    path2id = {p["path"]: p["id"] for p in idx}
    angles = {k: f"设题角度/听力/{k}" for k in ("细节理解", "推理判断", "人物关系", "地点推断", "主旨大意")}

    rows = fetch(prefix)
    plan = []
    for uid, qt, stem, sj, kj, kid in rows:
        if qt == "听力关键词语选择":
            continue
        names = json.loads(kj or "[]")
        had = [n for n in names if n in angles]
        if had and not a.recompute:
            continue
        subs = json.loads(sj or "[]")
        texts = [s.get("stem") or "" for s in subs] or [stem or ""]
        # 组级保留所有出现过的角度（按出现次数排序），这样按任一角度都能筛到该组
        picked = [ang for ang, _n in Counter(angle_of(t) for t in texts).most_common()]
        base_names = [n for n in names if n not in angles]
        base_ids = [i for i in json.loads(kid or "[]") if i not in {path2id[angles[k]] for k in angles}]
        plan.append((uid, qt, picked, base_names, base_ids))

    print(f"待处理 {len(plan)} 个单元")
    for uid, qt, angs, _n, _i in plan[:8]:
        print(f"  {uid} [{qt}] -> {' + '.join(angs)}")
    if not a.apply:
        print("\n干跑；加 --apply 执行")
        return 0

    ok = fail = 0
    for uid, qt, angs, names, ids in plan:
        body = json.dumps({"knowledge": names + angs,
                           "knowledgeIds": ids + [path2id[angles[x]] for x in angs]},
                          ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{BASE}/questions/{uid}", data=body, method="PATCH",
                                     headers={"Authorization": f"Bearer {KEY}",
                                              "Content-Type": "application/json; charset=utf-8"})
        try:
            urllib.request.urlopen(req, timeout=30).read()
            ok += 1
        except urllib.error.HTTPError as e:
            fail += 1
            print("  FAIL", uid, e.code, e.read().decode("utf-8", "replace")[:100])
    print(f"APPLY {ok} | 失败 {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
