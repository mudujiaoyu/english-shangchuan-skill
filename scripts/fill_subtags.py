# -*- coding: utf-8 -*-
"""给题组里没标签的子题补知识点。

三种来源，按顺序：
1. `--map map.json` 指定的逐空映射（语法选择这类必须逐空判定的题型）
2. 阅读理解：按设问方式判定（best title → 最佳标题 …）
3. 其余题型：继承组级的同维度标签（听力→语篇体裁/主题，完形→体裁/主题/句意理解 …）

    python fill_subtags.py --list            # 看还有多少空子题
    python fill_subtags.py --apply           # 按规则补
    python fill_subtags.py --map gram.json --apply   # 带上逐空映射
"""
import argparse
import json
import os
import re
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
R = "阅读技能/"

READ_RULES = [
    (r"best title|title for", R + "最佳标题"),
    (r"mainly about|main purpose|mainly talking|mainly discuss", R + "主旨大意"),
    (r"underlined word .* refer|refer to", R + "代词指代"),
    (r"underlined word|mean\(s\)? in|word .* mean", R + "猜测词义"),
    (r"come from|from which part|where.*probably from", R + "文章出处"),
    (r"how does the writer start|writer.*start", R + "写作手法"),
    (r"right order|in what order|order of", R + "篇章结构"),
    (r"which picture|picture best", R + "图片理解"),
    (r"infer|we can learn|suggest", R + "推理判断"),
    (r"according to|what can we know|which .* true|how many|when|where|who|why|what", R + "细节理解"),
]

INHERIT = {
    "听力短对话理解": ["语篇体裁", "主题"],
    "听力长对话理解": ["语篇体裁", "主题"],
    "听力短文理解": ["语篇体裁", "主题"],
    "听力信息转换": ["语篇体裁", "主题"],
    "听力判断": ["语篇体裁", "阅读技能"],
    "听力排序": ["语篇体裁", "阅读技能"],
    "听力问答": ["语篇体裁", "阅读技能"],
    "听力其他": ["语音", "词汇"],
    "语音题": ["语音"],
    "完形填空": ["语篇体裁", "主题", "阅读技能"],
    "补全对话": ["语用", "语篇体裁", "主题"],
    "任务型阅读": ["阅读技能"],
}


def classify(stem):
    s = (stem or "").lower()
    for pat, path in READ_RULES:
        if re.search(pat, s):
            return path
    return R + "细节理解"


def fetch(prefix):
    py = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = [list(r) for r in con.execute(
  "select q.unit_id,q.question_type,q.knowledge_ids_json,q.subquestions_json from questions q "
  "where q.unit_id like '{prefix}%' and q.subquestions_json not in ('[]','')")]
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          REMOTE, "python3 -"], input=py, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 失败: " + out.stderr[:200])
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--map")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    rows = fetch(a.ids)
    empty = sum(1 for _, _, _, sj in rows for s in json.loads(sj) if not s.get("knowledge"))
    print(f"题组 {len(rows)} 个，空子题 {empty} 个")
    if a.list:
        for uid, qt, _, sj in rows:
            n = sum(1 for s in json.loads(sj) if not s.get("knowledge"))
            if n:
                print(f"  {uid}[{qt}] {n} 个空")
        return 0

    idx = json.load(open(INDEX, encoding="utf-8"))
    p2i = {p["path"]: p["id"] for p in idx["points"]}
    p2n = {p["path"]: p["name"] for p in idx["points"]}
    id2p = {p["id"]: p["path"] for p in idx["points"]}
    gram = json.load(open(a.map, encoding="utf-8")) if a.map else {}

    ok, fail = 0, []
    for uid, qtype, kid, sj in rows:
        subs = json.loads(sj)
        if all(s.get("knowledge") for s in subs):
            continue
        gp = [id2p[i] for i in json.loads(kid or "[]") if i in id2p]
        inherited = []
        for dim in INHERIT.get(qtype, []):
            inherited += [p for p in gp if p.split("/")[0] == dim and p not in inherited]
        per_sub = gram.get(uid)

        for i, s in enumerate(subs):
            if s.get("knowledge"):
                continue
            if per_sub and i < len(per_sub):
                paths = [per_sub[i]]
            elif qtype == "阅读理解":
                paths = [classify(s.get("stem"))]
            else:
                paths = inherited
            paths = [p for p in paths if p in p2i]
            if not paths:
                continue
            s["knowledge"] = [p2n[p] for p in paths]
            s["knowledgeIds"] = [p2i[p] for p in paths]

        if not a.apply:
            ok += 1
            continue
        body = json.dumps({"subquestions": subs}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{BASE}/questions/{uid}", data=body, method="PATCH",
                                     headers={"Authorization": f"Bearer {open(KEY_FILE, encoding='ascii').read().strip()}",
                                              "Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                r.read()
            ok += 1
        except urllib.error.HTTPError as e:
            fail.append((uid, e.code, e.read().decode("utf-8", "replace")[:120]))

    print(("APPLY " if a.apply else "DRY-RUN ") + f"处理 {ok} 个题组 | 失败 {len(fail)}")
    for f in fail:
        print("  FAIL", f)


if __name__ == "__main__":
    main()
