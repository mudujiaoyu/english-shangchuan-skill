# -*- coding: utf-8 -*-
"""知识点索引查询：按关键词在 514 个节点里找路径与 ID。

    python find_kp.py 被动语态
    python find_kp.py 细节 --branch 阅读技能
    python find_kp.py --list-branches

索引来自 references/knowledge-catalog.json（版本 KCV-ENGLISH-KNOWLEDGE-1-0）。
落库时用这里查到的 path 解析 ID，别凭记忆写路径。
"""
import argparse
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
INDEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "references", "knowledge-catalog.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keyword", nargs="?", default="")
    ap.add_argument("--branch", default="", help="只在某个一级分支里找（主题/语音/词汇/语法/语篇体裁/阅读技能/语用）")
    ap.add_argument("--list-branches", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    a = ap.parse_args()

    data = json.load(open(INDEX, encoding="utf-8"))
    pts = data["points"]

    if a.list_branches:
        from collections import Counter
        c = Counter(p["path"].split("/")[0] for p in pts)
        print(f"{data['version_label']}（{data['version_id']}），{data['count']} 个节点")
        for k, v in c.most_common():
            print(f"  {k}: {v}")
        return 0

    if not a.keyword:
        ap.error("给个关键词，或加 --list-branches")

    hits = [p for p in pts
            if a.keyword in p["path"]
            and (not a.branch or p["path"].startswith(a.branch + "/"))]
    if not hits:
        print(f"没找到「{a.keyword}」；试试更短的关键词，或 --list-branches 看分支")
        return 1

    print(f"命中 {len(hits)} 个（显示前 {min(len(hits), a.limit)} 个）：")
    for p in hits[: a.limit]:
        depth = p["path"].count("/")
        print("  " * depth + f"{p['name']}   [{p['id']}]   {p['path']}")
    if len(hits) > a.limit:
        print(f"  … 还有 {len(hits) - a.limit} 个，用 --limit 调大")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
