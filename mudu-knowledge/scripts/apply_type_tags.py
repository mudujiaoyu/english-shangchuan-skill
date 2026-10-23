# -*- coding: utf-8 -*-
"""按题型匹配知识点：读 references/type-knowledge-map.json，给题目补默认标签。

两种用法：

1) 生成批次时补（上传前）
   python apply_type_tags.py --batch batch.json --out batch_tagged.json [--overwrite]

2) 已入库草稿补（上传后，走 PATCH）
   python apply_type_tags.py --patch [--apply] [--overwrite] [--ids AH-2019-]

默认只补「当前没有知识点」的单元；--overwrite 才覆盖已有。
题目特有的考点（如单项填空的具体语法点）不在 defaults 里，脚本会把这些单元的
hints 打印出来，提示仍需逐题判断。
"""
import argparse
import json
import os
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_PATH = os.path.join(SKILL, "references", "type-knowledge-map.json")
INDEX_PATH = os.path.join(SKILL, "references", "knowledge-catalog.json")
BASE = "http://127.0.0.1:8089/api"
KEY_FILE = os.path.expanduser(r"~\.mudu\api_key.txt")


def api(path, method="GET", body=None):
    key = open(KEY_FILE, encoding="ascii").read().strip()
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def load_catalog():
    """返回 (path -> id, 活跃版本 id)。优先用本地索引，没网也能跑。"""
    if os.path.exists(INDEX_PATH):
        data = json.load(open(INDEX_PATH, encoding="utf-8"))
        return {p["path"]: p["id"] for p in data["points"]}, data["version_id"]
    versions = api("/catalog/knowledge-versions")["items"]
    ver = next(v for v in versions if v["status"] == "active" and not v.get("textbook_id"))
    pts = api(f"/catalog/knowledge-points?version_id={ver['id']}")["items"]
    by_id = {p["id"]: p for p in pts}
    cache = {}

    def path_of(p):
        if p["id"] in cache:
            return cache[p["id"]]
        parts, cur = [], p
        while cur:
            parts.append(cur["name"])
            cur = by_id.get(cur.get("parent_id"))
        cache[p["id"]] = "/".join(reversed(parts))
        return cache[p["id"]]

    return {path_of(p): p["id"] for p in pts}, ver["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch")
    ap.add_argument("--out")
    ap.add_argument("--patch", action="store_true", help="给已入库草稿打补丁")
    ap.add_argument("--apply", action="store_true", help="--patch 时真正写入（默认 dry-run）")
    ap.add_argument("--overwrite", action="store_true", help="覆盖已有知识点")
    ap.add_argument("--ids", default="", help="只处理这些前缀的单元，逗号分隔")
    a = ap.parse_args()

    kmap = json.load(open(MAP_PATH, encoding="utf-8"))
    kp2id, version_id = load_catalog()
    unresolved = {}

    def ids_for(type_name):
        out, missing = [], []
        for p in kmap.get(type_name, {}).get("defaults", []):
            if p in kp2id:
                out.append((p, kp2id[p]))
            else:
                missing.append(p)
        if missing:
            unresolved[type_name] = missing
        return out

    if unresolved:
        print("警告：以下默认路径解析不到，已跳过：")
        for t, v in unresolved.items():
            print("  ", t, v)

    if a.batch:
        batch = json.load(open(a.batch, encoding="utf-8-sig"))
        changed = 0
        need_manual = []
        for it in batch["items"]:
            t = it.get("type", "")
            if not kmap.get(t):
                continue
            has = bool(it.get("knowledge"))
            if has and not a.overwrite:
                continue
            pairs = ids_for(t)
            if not pairs:
                need_manual.append((it["id"], t))
                continue
            it["knowledge"] = [n for n, _ in pairs]
            it["knowledgeIds"] = [i for _, i in pairs]
            changed += 1
        out = a.out or a.batch.replace(".json", "_tagged.json")
        json.dump(batch, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        print(f"批次已写出：{out} | 补标签 {changed} 个单元 | 需逐题判断 {len(need_manual)} 个")
        for qid, t in need_manual[:10]:
            print(f"  {qid} ({t}) 无默认标签，hints: {kmap[t]['hints'][:2]}")
        return 0

    if a.patch:
        prefixes = [x.strip() for x in a.ids.split(",") if x.strip()]
        rows = api("/questions?limit=500")["items"]  # 只含已发布；草稿需走库
        print("注意：/api/questions 只返回已发布题；草稿补标签请用 --batch 或在库内直连。")
        print("已发布条数:", len(rows))
        return 0

    ap.error("需要 --batch 或 --patch")


if __name__ == "__main__":
    raise SystemExit(main())
