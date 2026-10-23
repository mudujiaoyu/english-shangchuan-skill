# -*- coding: utf-8 -*-
"""知识点标签体检：禁标维度、非叶子标签、空标签。

    python check_tags.py                 # 全库体检
    python check_tags.py --ids AH-2020   # 只看某个前缀

判定依据：references/knowledge-matching-rules.md
"""
import argparse
import json
import os
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


SKILL = _skill_root()
INDEX = os.path.join(SKILL, "references", "knowledge-catalog.json")
MAP = os.path.join(SKILL, "references", "type-knowledge-map.json")
SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")
REMOTE = "ubuntu@101.43.1.57"

FORBIDDEN = {
    "完形填空": ("语法/", "词汇/词汇辨析"),
    "单项填空": ("主题/", "语篇体裁/"),
    "听力短对话理解": ("语法/",), "听力长对话理解": ("语法/",), "听力短文理解": ("语法/",),
    "听力信息转换": ("语法/",), "听力判断": ("语法/",), "听力排序": ("语法/",),
    "听力问答": ("语法/",), "听力其他": ("语法/",),
    "阅读理解": ("语法/", "词汇/词汇辨析"),
}

# 语法分支里这些中间节点语义已经够精确，停在它们上面可接受
ALLOWED_INTERNAL = {
    "语法/谓语动词的时态和语态/现在完成时",
    "语法/谓语动词的时态和语态/一般现在时",
    "语法/谓语动词的时态和语态/一般过去时",
    "语法/谓语动词的时态和语态/一般将来时",
    "语法/谓语动词的时态和语态/被动语态",
    "语法/连词/从属连词",
    "语法/连词/并列连词",
    "语法/副词/副词的用法",
    "语法/副词/副词的最高级",
    "语法/名词/名词的数",
    "语法/动词的非谓语形式/动词不定式",
    "语法/情态动词/can",
    "语法/形容词/形容词比较级",
    "语法/代词/不定代词/复合不定代词",
}


def fetch(prefix):
    py = f'''
import sqlite3, json

def _skill_root():
    d = os.path.dirname(os.path.abspath(__file__))
    while not os.path.exists(os.path.join(d, "SKILL.md")):
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return d

con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = [list(r) for r in con.execute(
  "select q.unit_id,q.question_type,q.knowledge_json,q.knowledge_ids_json,q.subquestions_json "
  "from questions q where q.unit_id like '{prefix}%'")]
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          REMOTE, "python3 -"], input=py, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 失败: " + out.stderr[:200])
    return json.loads(out.stdout)


def fetch_batch(path):
    """直接体检待上传的批次文件（确认之前也能查）。"""
    batch = json.load(open(path, encoding="utf-8-sig"))
    rows = []
    for it in batch.get("items") or []:
        rows.append([it.get("id"), it.get("type"),
                     json.dumps(it.get("knowledge") or [], ensure_ascii=False),
                     json.dumps(it.get("knowledge_ids") or [], ensure_ascii=False),
                     json.dumps(it.get("subquestions") or [], ensure_ascii=False)])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--batch", default="", help="直接查批次 json（上传前用）")
    ap.add_argument("--strict", action="store_true",
                    help="越界维度也算失败（默认只报告，因为历史数据按旧规则打过标）")
    a = ap.parse_args()
    prefix = a.ids or ""

    idx = json.load(open(INDEX, encoding="utf-8"))
    id2p = {p["id"]: p["path"] for p in idx["points"]}
    paths = {p["path"] for p in idx["points"]}
    kids = Counter(p.rsplit("/", 1)[0] for p in paths if "/" in p)
    internal = {p for p in paths if kids.get(p)}

    by_type = json.load(open(MAP, encoding="utf-8"))["by_type"]
    # 对照表给出的「可考维度」＝允许范围；不在范围内的标签判为越界
    allowed, scopes = {}, {}
    for qt, cfg in by_type.items():
        branches = set()
        for d in cfg.get("dims", []):
            b = d["branch"]
            if b == "词汇/语法":
                branches.update({"词汇", "语法"})
            else:
                branches.add(b)
        scoped = {}
        for d in cfg.get("dims", []):
            if d.get("scope"):
                scoped[d["branch"]] = d["scope"]
        allowed[qt] = branches
        scopes[qt] = scoped
    # 情景反应的应答语题挂在听力其他下，表里没有对应维度，放行语用
    allowed.setdefault("听力其他", set()).add("语用")
    rows = fetch_batch(a.batch) if a.batch else fetch(prefix)
    empty, forbidden, coarse = [], [], defaultdict(list)
    out_of_scope = []
    for uid, qtype, kj, kid, sj in rows:
        names = json.loads(kj or "[]")
        ids = json.loads(kid or "[]")
        if not ids:
            empty.append((uid, qtype))
            continue
        cur = [id2p.get(i) for i in ids if id2p.get(i)]
        # 该题型按对照表应带的维度，缺哪个
        ok_branches = allowed.get(qtype)
        if ok_branches:
            for p in cur:
                root = p.split("/")[0]
                if root not in ok_branches:
                    out_of_scope.append((uid, qtype, p))
                    continue
                need_scope = (scopes.get(qtype) or {}).get(root)
                if need_scope and not p.startswith(f"{root}/{need_scope}"):
                    out_of_scope.append((uid, qtype, p))
        for p in cur:
            if any(p.startswith(b) for b in FORBIDDEN.get(qtype, ())):
                forbidden.append((uid, qtype, p))
            if p in internal and p not in ALLOWED_INTERNAL:
                coarse[p].append(f"{uid}[{qtype}]")

    where = a.batch or prefix or "全库"
    print(f"扫描 {len(rows)} 个单元（{'批次' if a.batch else '前缀'}：{where}）")
    print(f"空标签 {len(empty)} | 禁标维度 {len(forbidden)} | 越界维度 {len(out_of_scope)} "
          f"| 非叶子标签 {sum(len(v) for v in coarse.values())}")
    if out_of_scope:
        print("\n超出对照表范围（该题型不考这个维度）：")
        for uid, qt, p in out_of_scope[:12]:
            print(f"  {uid}[{qt}]  {p}")
    if forbidden:
        print("\n禁标维度：")
        for uid, qt, p in forbidden[:12]:
            print(f"  {uid}[{qt}]  {p}")
    if coarse:
        print("\n停在父节点（应下钻）：")
        for p, us in sorted(coarse.items(), key=lambda kv: -len(kv[1])):
            print(f"  {p}  （{len(us)} 处，子节点 {kids[p]}）例: {', '.join(us[:3])}")
    if empty:
        print("\n空标签：")
        for uid, qt in empty[:10]:
            print(f"  {uid}[{qt}]")
    hard = bool(empty or coarse or forbidden)
    if a.strict:
        hard = hard or bool(out_of_scope)
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
