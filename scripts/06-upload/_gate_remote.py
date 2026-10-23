# -*- coding: utf-8 -*-
"""服务器端闸门（由 run_upload.py 用 scp 送上去、在一次 SSH 会话里跑完）。

做三件事，避免原来「查重一次往返 + 预检一次往返（还要复制 5MB 库）：
  1) 查重：ID 已存在 / 同年同题号 / 内容指纹（读只读连接，不复制库）
  2) 预检：用服务端的 prepare_question_knowledge / normalize_* 回放，
     不复制库、不插库——用 db.execute 的参数化查询解析知识点即可
  3) 统计库内已存在的 ID（同批重传会 409）

输出最后一行 JSON：{"dup_ok":bool,"dup_hits":[...],"preflight":[...],"existing_ids":n}
"""
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, "/home/ubuntu/mudu-quiz")
DB = "file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro"
DEFAULT_BATCH = "/tmp/_pipeline_batch.json"


def norm(text):
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(text or ""), flags=re.UNICODE).lower()


def fingerprint(item):
    stem = norm(item.get("stem") or "")
    if len(stem) < 12:
        return None
    opts = "|".join(norm(o) for o in (item.get("options") or []))
    subs = "|".join(norm(s.get("stem") or "") + norm("".join(s.get("options") or []))
                    for s in item.get("subquestions") or [])
    import hashlib
    base = stem + "||" + opts + "||" + subs + "||" + norm(item.get("material") or "")
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def main():
    # 批次来源优先级：显式路径 > stdin > 流水线落地的默认路径
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg and arg != "-":
        batch = json.load(open(arg, encoding="utf-8"))
    elif not arg and os.path.exists(DEFAULT_BATCH):
        batch = json.load(open(DEFAULT_BATCH, encoding="utf-8"))
    else:
        batch = json.load(sys.stdin)
    items = batch.get("items") or []
    con = sqlite3.connect(DB, uri=True)
    con.row_factory = sqlite3.Row

    existing = {r["id"] for r in con.execute("select id from question_units")}
    prints = {}
    for r in con.execute("select u.id, q.stem, q.options_json, q.subquestions_json, q.material "
                         "from question_units u join questions q on q.id=u.id"):
        fp = fingerprint({"stem": r["stem"], "options": json.loads(r["options_json"] or "[]"),
                          "subquestions": json.loads(r["subquestions_json"] or "[]"),
                          "material": r["material"]})
        if fp:
            prints.setdefault(fp, r["id"])

    dup_hits, existing_ids = [], 0
    for it in items:
        uid = it.get("id") or ""
        if uid in existing:
            existing_ids += 1
            dup_hits.append([uid, "ID 已存在"])
            continue
        fp = fingerprint(it)
        if fp and fp in prints:
            dup_hits.append([uid, f"内容同 {prints[fp]}"])
    dup_ok = not dup_hits

    # 预检：只调服务端校验器，不在库上写
    fails = []
    try:
        import backend as B
        con2 = sqlite3.connect(DB, uri=True)
        con2.row_factory = sqlite3.Row
        acct = con2.execute("select id from accounts where is_admin=1 limit 1").fetchone()
        actor = {"id": acct["id"] if acct else "x", "actor_type": "human", "subject_id": "english",
                 "role": "super_admin", "is_admin": True, "permissions": set(B.PERMISSIONS)}
        for raw in items:
            body = dict(raw)
            try:
                body.update(B.prepare_question_knowledge(con2, body, "english", actor))
                B.normalize_material_blocks(body.get("materialBlocks", []))
                B.normalize_filter_metadata(body.get("filterMetadata", {}))
                B.normalize_attachments(body.get("attachments", []))
                for sub in body.get("subquestions") or []:
                    if isinstance(sub, dict):
                        B.normalize_attachments(sub.get("attachments", []))
            except Exception as exc:                     # noqa: BLE001
                fails.append(f"{raw.get('id')}: {type(exc).__name__} {str(exc)[:100]}")
        if len(items) != len({i.get('id') for i in items}):
            fails.append("批次内 ID 重复")
    except Exception as exc:                             # noqa: BLE001
        fails.append(f"导入 backend 失败: {type(exc).__name__} {str(exc)[:120]}")

    # 顺带把「批次引用的远端媒体是否已就位」带回去，省一次列目录往返
    batch_dirs = sorted({u.split("/")[2] for it in items
                         for a in (it.get("attachments") or []) + [x for s in (it.get("subquestions") or [])
                                                                   for x in (s.get("attachments") or [])]
                         if str(a.get("url") or "").startswith("/source-media/")
                         for u in [str(a["url"])] if len(u.split("/")) >= 4})
    landed = {}
    for d in batch_dirs:
        path = f"/home/ubuntu/mudu-quiz/static/source-media/{d}"
        landed[d] = sorted(os.listdir(path)) if os.path.isdir(path) else []
    print(json.dumps({"dup_ok": dup_ok, "dup_hits": dup_hits[:5],
                      "preflight": fails[:8], "existing_ids": existing_ids,
                      "remote_media": landed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
