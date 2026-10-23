# -*- coding: utf-8 -*-
"""上传前查重：题库里已有，就不许再传。

查重维度（任一命中即判重）：
    1. 题库 ID 完全相同（AH-2019-001 已存在）
    2. 同来源 + 同年 + 同题号（从 id 解析，防 id 命名变体）
    3. 内容指纹相同（题干归一化后哈希，跨年份也能抓到同一道题被重复录入）

默认走服务器只读库（能同时看到草稿和已发布）；没有 SSH 时可用 --api 退化为
只查已发布题（GET /api/questions?q=），覆盖面会小很多。

用法：
    python check_duplicates.py --batch batch_2019.json \
        --ssh-key %USERPROFILE%\\.ssh\\mudu_gd --remote ubuntu@101.43.1.57

    python check_duplicates.py --batch batch_2019.json --api   # 只查已发布

退出码：0 无重复；1 有重复（禁止上传）；2 参数/连接错误。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

REMOTE_DB = "/home/ubuntu/mudu-quiz/data/mudu.sqlite3"


def norm(text):
    """归一化：去空白与标点、转小写，只保留字母数字与汉字。不截断——截断会让尾部修改漏检。"""
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(text or ""), flags=re.UNICODE).lower()


def fingerprint(item):
    """内容指纹：题干 + 选项 + 材料。

    只取题干会误判——各年听力第 I 大题题干都是「选出一个你所听到的单词或短语」，
    这类通用指令必须靠选项区分。题干过短（<12 字）时不参与内容查重，
    只靠 ID / 同年同题号判断，避免把通用指令当成重复题。
    """
    stem = norm(item.get("stem") or "")
    if len(stem) < 12:
        return None
    opts = "|".join(norm(o) for o in (item.get("options") or []))
    subs = item.get("subquestions") or []
    sub_txt = "|".join(norm(s.get("stem") or "") + norm("".join(s.get("options") or [])) for s in subs)
    base = stem + "||" + opts + "||" + sub_txt + "||" + norm(item.get("material") or "")
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def parse_key(item_id):
    """AH-2019-001 → ('2019', 1)。"""
    m = re.match(r"^[A-Z]+-(\d{4})-(\d+)$", str(item_id))
    return (m.group(1), int(m.group(2))) if m else (None, None)


def load_existing_db(ssh_key, remote):
    py = f'''
import sqlite3, json
con = sqlite3.connect("file:{REMOTE_DB}?mode=ro", uri=True)
rows = []
for r in con.execute("select u.id, u.status, q.stem, q.material, q.subquestions_json, q.options_json from question_units u join questions q on q.id=u.id"):
    rows.append(r)
print(json.dumps(rows, ensure_ascii=False))
'''
    cmd = ["ssh", "-i", os.path.expanduser(ssh_key), "-o", "IdentitiesOnly=yes",
           "-o", "BatchMode=yes", remote, "python3 -"]
    out = subprocess.run(cmd, input=py, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print("SSH 查询失败:", out.stderr[:300])
        sys.exit(2)
    return json.loads(out.stdout)


def load_existing_api(base, key):
    rows, page = [], 1
    while True:
        url = f"{base}/questions?limit=200&page={page}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
        except Exception as exc:
            print("API 查询失败:", exc)
            sys.exit(2)
        items = data.get("items") or []
        for it in items:
            rows.append([it.get("id"), "published", it.get("stem"), it.get("material"),
                         json.dumps(it.get("subquestions") or [], ensure_ascii=False),
                         json.dumps(it.get("options") or [], ensure_ascii=False)])
        if len(items) < 200:
            break
        page += 1
    return rows


def main():
    ap = argparse.ArgumentParser(description="上传前查重")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--ssh-key", default=os.path.join(os.path.expanduser("~"), ".ssh", "mudu_gd"))
    ap.add_argument("--remote", default="ubuntu@101.43.1.57")
    ap.add_argument("--api", action="store_true", help="退化为只查已发布题")
    ap.add_argument("--base", default="http://127.0.0.1:8089/api")
    ap.add_argument("--key-file", default=os.path.join(os.path.expanduser("~"), ".mudu", "api_key.txt"))
    a = ap.parse_args()

    batch = json.load(open(a.batch, encoding="utf-8-sig"))
    items = batch.get("items") or []
    if not items:
        print("批次为空"); return 2

    if a.api:
        key = open(a.key_file, encoding="ascii").read().strip()
        existing = load_existing_api(a.base, key)
        print(f"（API 模式：只能看到已发布题，{len(existing)} 条）")
    else:
        existing = load_existing_db(a.ssh_key, a.remote)
        print(f"（库模式：草稿 + 已发布，{len(existing)} 条）")

    ids, keys, prints = {}, {}, {}
    for eid, status, stem, material, subs_json, opts_json in existing:
        ids[eid] = status
        y, n = parse_key(eid)
        if y:
            keys[(y, n)] = eid
        fp = fingerprint({"stem": stem, "material": material,
                          "options": json.loads(opts_json or "[]"),
                          "subquestions": json.loads(subs_json or "[]")})
        if fp:
            prints.setdefault(fp, eid)

    hits = {"id": [], "key": [], "content": []}
    for it in items:
        i = it.get("id")
        if i in ids:
            hits["id"].append((i, ids[i]))
            continue
        y, n = parse_key(i)
        if y and (y, n) in keys:
            hits["key"].append((i, keys[(y, n)]))
            continue
        fp = fingerprint(it)
        if fp and fp in prints:
            hits["content"].append((i, prints[fp]))

    total = sum(len(v) for v in hits.values())
    if not total:
        print(f"查重通过：{len(items)} 个单元在题库中均无同 ID / 同题号 / 同内容记录。")
        return 0

    print(f"\n发现 {total} 处重复，禁止上传：")
    for label, name in (("id", "ID 已存在"), ("key", "同年同题号"), ("content", "内容相同")):
        rows = hits[label]
        if not rows:
            continue
        print(f"  {name}：{len(rows)} 条")
        for i, eid in rows[:5]:
            print(f"    {i} → {eid}")
        if len(rows) > 5:
            print(f"    … 其余 {len(rows) - 5} 条同类")
    print("\n处理：已存在就不要重复上传；确需修订请对现有草稿 PATCH，不要新传一批。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
