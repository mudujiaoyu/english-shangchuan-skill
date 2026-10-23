# -*- coding: utf-8 -*-
"""把附件合并进已确认草稿（PATCH 是整体覆盖，必须先读现状再合并）。

背景：
    同一批 id 不能二次确认。v1 已确认后想补音频，不能再上传 v2（会 409 question_id_exists），
    只能对草稿 PATCH。而 PATCH 的 attachments 是整体替换，直接提交会把已有图片冲掉。

用法:
    python patch_attachments.py --batch batch.json --current current.json [--dry-run]

    batch.json   本次要写入的批次对象（每个 item 自带目标 attachments）
    current.json 现状：{"AH-2018-006": [ {...}, ... ], ...}
                 只读导出，例如在服务器上：
                 python3 -c "import sqlite3,json;con=sqlite3.connect('file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro',uri=True);print(json.dumps({r[0]:json.loads(r[1] or '[]') for r in con.execute(\"select unit_id,attachments_json from questions where unit_id like 'AH-2018-%'\")},ensure_ascii=False))"

Key 从 %USERPROFILE%\\.mudu\\api_key.txt 读取（可用 --key-file 覆盖），不回显。
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8089/api"


def key_from(path):
    with open(os.path.expanduser(path), encoding="ascii") as fh:
        return fh.read().strip()


def merge(cur, add):
    out = list(cur)
    seen = {a.get("url") for a in out}
    for a in add:
        if a.get("url") not in seen:
            out.append(a)
            seen.add(a.get("url"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--key-file", default=os.path.join(os.path.expanduser("~"), ".mudu", "api_key.txt"))
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    batch = json.load(open(a.batch, encoding="utf-8-sig"))
    current = json.load(open(a.current, encoding="utf-8-sig"))
    key = key_from(a.key_file)

    ok, fail = [], []
    for item in batch["items"]:
        add = item.get("attachments") or []
        if not add:
            continue
        qid = item["id"]
        merged = merge(current.get(qid, []), add)
        if a.dry_run:
            print(f"{qid}  现有 {len(current.get(qid, []))} + 新增 {len(add)} -> {len(merged)}")
            continue
        body = json.dumps({"attachments": merged}, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            f"{a.base}/questions/{qid}", data=body, method="PATCH",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json; charset=utf-8"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                ok.append((qid, resp.status, len(merged)))
        except urllib.error.HTTPError as exc:
            fail.append((qid, exc.code, exc.read().decode("utf-8", "replace")[:160]))

    if a.dry_run:
        return 0
    print(f"PATCH 成功 {len(ok)} / 失败 {len(fail)}")
    for qid, code, n in ok:
        print(f"  {qid}  {code}  附件 {n}")
    for f in fail:
        print("  FAIL", f)
    return 0 if not fail else 1


if __name__ == "__main__":
    raise SystemExit(main())
