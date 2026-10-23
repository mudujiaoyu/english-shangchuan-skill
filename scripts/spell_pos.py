# -*- coding: utf-8 -*-
"""按答案词性给「单词拼写」细分知识点（不用猜，看答案在句中作什么成分）。

两步：
    python spell_pos.py --list                # 列出所有拼写题与答案，人工定词性
    python spell_pos.py --map pos.json --apply # 按 map 落库

pos.json 形如：
    {"AH-2020-076": "名词辨析", "AH-2020-078": "副词辨析", ...}

落点固定为 `词汇/词汇辨析/<词性>辨析`；已有的语法形式标签（名词的数、动词的基本形式）保留，
需要派生的另加 `词汇/构词法/派生法`。
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(SKILL, "references", "knowledge-catalog.json")
KEY_FILE = os.path.expanduser(r"~\.mudu\api_key.txt")
BASE = "http://127.0.0.1:8089/api"
SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")
REMOTE = "ubuntu@101.43.1.57"


def fetch(prefix="AH-"):
    py = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = [list(r) for r in con.execute(
  "select unit_id, stem, answer, knowledge_ids_json from questions "
  "where question_type='单词拼写' and unit_id like '{prefix}%' order by unit_id")]
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          REMOTE, "python3 -"], input=py, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 失败: " + out.stderr[:200])
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出拼写题与答案")
    ap.add_argument("--map", help="词性映射 JSON")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", default="AH-")
    a = ap.parse_args()

    rows = fetch(a.ids)
    if a.list or not a.map:
        print(f"{len(rows)} 道拼写题：")
        for uid, stem, ans, _ in rows:
            print(f"  {uid}\t答案={ans}\t{stem[:60]}")
        return 0

    pos = json.load(open(a.map, encoding="utf-8"))
    idx = json.load(open(INDEX, encoding="utf-8"))
    p2i = {p["path"]: p["id"] for p in idx["points"]}
    p2n = {p["path"]: p["name"] for p in idx["points"]}
    id2p = {p["id"]: p["path"] for p in idx["points"]}

    ok, fail = 0, []
    for uid, stem, ans, kid in rows:
        kind = pos.get(uid)
        if not kind:
            continue
        target = f"词汇/词汇辨析/{kind}"
        if target not in p2i:
            fail.append((uid, "路径不存在", target))
            continue
        old = [id2p[i] for i in json.loads(kid or "[]") if i in id2p]
        new = [p for p in old if p != "词汇"]
        if target not in new:
            new.append(target)
        if new == old:
            continue
        if not a.apply:
            print(f"  {uid} [{ans}] → {kind}")
            ok += 1
            continue
        body = json.dumps({"knowledge": [p2n[p] for p in new],
                           "knowledgeIds": [p2i[p] for p in new]}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{BASE}/questions/{uid}", data=body, method="PATCH",
                                     headers={"Authorization": f"Bearer {open(KEY_FILE, encoding='ascii').read().strip()}",
                                              "Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
            ok += 1
        except urllib.error.HTTPError as e:
            fail.append((uid, e.code, e.read().decode("utf-8", "replace")[:120]))
    print(("APPLY " if a.apply else "DRY-RUN ") + f"{ok} 个 | 失败 {len(fail)}")
    for f in fail:
        print("  FAIL", f)


if __name__ == "__main__":
    main()
