# -*- coding: utf-8 -*-
"""上传前预检：用服务端自己的校验器回放整批，避免确认时才发现 400。

    python preflight_check.py --batch batch_2022.json

做的事（全部在服务器上跑，不改正式库）：
1. 复制一份 sqlite 到 /tmp
2. 对每个单元跑 prepare_question_knowledge / normalize_material_blocks /
   normalize_attachments / normalize_filter_metadata / legacy_textbook_mappings
3. 检查 ID 是否已存在、source_type / unit_kind / difficulty 是否合法
4. 在副本上模拟确认写入（可 --insert），跑完回滚

退出码：0 通过；1 有失败项。
"""
import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")
REMOTE = "ubuntu@101.43.1.57"
REMOTE_DIR = "/home/ubuntu/mudu-quiz"

SCRIPT = r'''
import sys, json, sqlite3, shutil, time
from datetime import datetime, timezone
sys.path.insert(0, "/home/ubuntu/mudu-quiz")
import backend as B

batch_path, do_insert = sys.argv[1], sys.argv[2] == "1"
batch = json.load(open(batch_path, encoding="utf-8"))
items = batch["items"]
shutil.copy("/home/ubuntu/mudu-quiz/data/mudu.sqlite3", "/tmp/preflight.sqlite3")
db = sqlite3.connect("/tmp/preflight.sqlite3"); db.row_factory = sqlite3.Row
acct = db.execute("select id from accounts where is_admin=1 limit 1").fetchone()
actor = {"id": acct["id"] if acct else "x", "actor_type": "human", "subject_id": "english",
         "role": "super_admin", "is_admin": True, "permissions": set(B.PERMISSIONS)}

fails = []
ids = [r.get("id") for r in items if r.get("id")]
dup = db.execute(f"SELECT COUNT(*) FROM question_units WHERE id IN ({','.join('?' for _ in ids)})", ids).fetchone()[0]
if dup: fails.append(f"{dup} 个 ID 已存在")
if len(ids) != len(set(ids)): fails.append("批次内 ID 重复")
bad_src = {r.get("source_type") for r in items} - set(B.SOURCE_TYPES)
if bad_src: fails.append(f"source_type 非法: {bad_src}")
bad_kind = {r.get("unit_kind") for r in items} - {None, "", "standalone", "group"}
if bad_kind: fails.append(f"unit_kind 非法: {bad_kind}")

ok_diff = {None, "", "易", "中", "难", "容易", "适中", "困难"}
bad_diff = {r.get("difficulty") for r in items} - ok_diff
if bad_diff: fails.append(f"difficulty 非法: {bad_diff}")
ok_cat = {"优选题", "易错题"}
bad_cat = {c for r in items for c in (r.get("filterMetadata") or {}).get("categories") or []} - ok_cat
if bad_cat: fails.append(f"categories 非法: {bad_cat}")
for r in items:
    dv = (r.get("filterMetadata") or {}).get("difficultyValue")
    if dv is not None and not (isinstance(dv, (int, float)) and 0 <= dv <= 1):
        fails.append(f"{r.get('id')}: difficultyValue 越界 {dv}")
missing_diff = [r.get("id") for r in items
                if not r.get("difficulty") and (r.get("filterMetadata") or {}).get("difficultyValue") is None]
if missing_diff:
    print("WARN 待编辑定难度:", len(missing_diff), missing_diff[:8])

import urllib.request
fw = json.load(urllib.request.urlopen("http://127.0.0.1:89/filter-framework.json"))
valid_sub = {t["name"]: set(t.get("subtypes") or []) for t in fw["question_types"]}

created = 0
for raw in items:
    qtype = raw.get("type") or ""
    subs = (raw.get("filterMetadata") or {}).get("subtypes") or []
    if qtype not in valid_sub:
        fails.append(f"{raw.get('id')}: 题型不在 26 主类内: {qtype}")
    else:
        bad_sub = [s for s in subs if s not in valid_sub[qtype]]
        if bad_sub:
            fails.append(f"{raw.get('id')}: 子类非法 {bad_sub}（{qtype} 可选: {sorted(valid_sub[qtype])}）")
        elif not subs and valid_sub[qtype]:
            fails.append(f"{raw.get('id')}: {qtype} 缺 subtypes（可选: {sorted(valid_sub[qtype])}）")
    try:
        raw.update(B.prepare_question_knowledge(db, raw, "english", actor))
        blocks = B.normalize_material_blocks(raw.get("materialBlocks", []))
        B.normalize_filter_metadata(raw.get("filterMetadata", {}))
        atts = B.normalize_attachments(raw.get("attachments", []))
        mappings = B.legacy_textbook_mappings(db, raw, "english")
    except Exception as e:
        fails.append(f"{raw.get('id')}: {type(e).__name__} {str(e)[:120]}")
        continue
    if not do_insert:
        created += 1
        continue
    try:
        item_id = raw.get("id")
        t = B.now_iso()
        exp = datetime.fromtimestamp(time.time() + 14 * 86400, timezone.utc).isoformat(timespec="seconds")
        db.execute("INSERT INTO question_units(id,status,title,unit_kind,revision,created_by,updated_by,created_at,updated_at,draft_expires_at,published_at,published_by,subject_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (item_id, "draft", raw.get("title") or raw.get("stem", ""), raw.get("unit_kind"), 1, actor["id"], actor["id"], t, t, exp, None, None, "english"))
        db.execute("INSERT INTO questions(id,unit_id,stem,options_json,answer,explanation,material,material_blocks_json,article_summary,subquestions_json,attachments_json,curriculum,knowledge_json,knowledge_status,question_type,difficulty,source_type,year,institution,school,regional_version,source,location,version,authorization,warnings_json,relations_json,textbook_id,knowledge_version_id,knowledge_ids_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (item_id, item_id, raw.get("stem", ""), json.dumps(raw.get("options", []), ensure_ascii=False),
                    raw.get("answer", ""), raw.get("explanation", ""), raw.get("material", ""),
                    json.dumps(blocks, ensure_ascii=False), raw.get("articleSummary", "") or "",
                    json.dumps(raw.get("subquestions", []), ensure_ascii=False),
                    json.dumps(atts, ensure_ascii=False), "", json.dumps(raw.get("knowledge", []), ensure_ascii=False),
                    "待梳理", raw.get("type", ""), raw.get("difficulty") if raw.get("difficulty") is not None else "",
                    raw.get("source_type", ""), raw.get("year"), "", "", "", raw.get("source", ""),
                    raw.get("location", ""), raw.get("version", ""), raw.get("authorization", "待核实"),
                    "[]", "[]", None, None, json.dumps(raw.get("knowledgeIds") or [], ensure_ascii=False)))
        created += 1
    except Exception as e:
        fails.append(f"{raw.get('id')}: insert {type(e).__name__} {str(e)[:120]}")
db.rollback()
print(json.dumps({"units": len(items), "ok": created, "fails": fails}, ensure_ascii=False))
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", required=True)
    ap.add_argument("--insert", action="store_true", help="在副本上模拟确认写入")
    a = ap.parse_args()

    remote_path = "/tmp/preflight_batch.json"
    subprocess.run(["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-q",
                    a.batch, f"{REMOTE}:{remote_path}"], check=True)
    script_path = "/tmp/preflight_check.py"
    open("preflight_check_remote.py", "w", encoding="utf-8").write(SCRIPT)
    subprocess.run(["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-q",
                    "preflight_check_remote.py", f"{REMOTE}:{script_path}"], check=True)
    os.remove("preflight_check_remote.py")

    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          REMOTE, f"cd {REMOTE_DIR} && python3 {script_path} {remote_path} {1 if a.insert else 0}"],
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        print("预检执行失败:", out.stderr[-500:])
        return 2
    try:
        res = json.loads(out.stdout.strip().splitlines()[-1])
    except Exception:
        print(out.stdout[-800:])
        return 2

    print(f"单元 {res['units']} | 通过 {res['ok']} | 失败 {len(res['fails'])}")
    for f in res["fails"]:
        print("  FAIL", f)
    return 0 if not res["fails"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
