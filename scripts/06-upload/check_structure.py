# -*- coding: utf-8 -*-
"""上传前结构体检：unit_kind、子题、选项形态是否自洽。

    python check_structure.py --batch 06_batch/b.json
    python check_structure.py --ids RJ8A

为什么单独一个脚本：
    服务端 PATCH **不能改 unit_kind**（standalone ↔ group 只能建批时确定），
    DELETE 又只允许人工调用。所以「独立题误带子题」「该是题组却建成独立题」
    这类结构错误，一旦入库就只能「人工删除 + 重传」，
    而且 publish_check 只查 group 缺材料，查不出「standalone 带了子题」。
    花 0.05s 在上传前查一遍，比事后请人工删 23 条便宜得多。

判据：
    · standalone 不应有 subquestions（前端按独立题渲染，子题不显示，但数据里占着）
    · group 必须有 material 与 subquestions，且每个子题有 stem + answer
    · group 的子题序号应连续（1..n），不要跳号或重复
    · 图片选项（optionKey）在 standalone 时挂单元、group 时挂子题 —— 层级错了不报错只不显示
退出码：0 通过；1 有问题。
"""
import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")
REMOTE = "ubuntu@101.43.1.57"


def load_batch(path):
    return [it for it in json.load(open(path, encoding="utf-8-sig")).get("items") or []]


def load_db(prefix):
    py = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = []
for r in con.execute("""select q.unit_id, u.unit_kind, q.question_type, q.stem, q.material,
                               q.subquestions_json, q.attachments_json, q.options_json
                        from questions q join question_units u on u.id=q.unit_id
                        where q.unit_id like '{prefix}%'"""):
    rows.append({{"id": r[0], "unit_kind": r[1], "type": r[2], "stem": r[3], "material": r[4],
                  "subquestions": json.loads(r[5] or "[]"),
                  "attachments": json.loads(r[6] or "[]"),
                  "options": json.loads(r[7] or "[]")}})
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          REMOTE, "python3 -"], input=py, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 失败: " + out.stderr[:200])
    return json.loads(out.stdout)


def audit(items):
    bad = []
    for it in items:
        uid = it.get("id")
        kind = it.get("unit_kind") or ""
        subs = it.get("subquestions") or []
        mat = it.get("material") or ""
        if kind == "standalone" and subs:
            bad.append((uid, "独立题带了子题",
                        f"subquestions 有 {len(subs)} 条；服务端 PATCH 不能改 unit_kind，"
                        f"只能人工删除后按 group 重传"))
        if kind == "group":
            if not mat.strip():
                bad.append((uid, "题组缺 material", "组题必须有共用材料"))
            if not subs:
                bad.append((uid, "题组缺子题", "group 必须带 subquestions"))
            nums = [s.get("number") for s in subs if isinstance(s, dict)]
            if nums and nums != list(range(1, len(nums) + 1)):
                bad.append((uid, "子题序号不连续", f"实际 {nums}"))
            for s in subs:
                if isinstance(s, dict):
                    if not str(s.get("stem") or "").strip():
                        bad.append((uid, f"子题{s.get('number')} 缺 stem", ""))
                    if not str(s.get("answer") or "").strip():
                        bad.append((uid, f"子题{s.get('number')} 缺 answer", ""))
        # 图片选项层级
        unit_opt = [a for a in (it.get("attachments") or []) if a.get("placement") == "option"]
        if kind == "group" and unit_opt:
            bad.append((uid, "选项图挂在单元上",
                        "组题的选项图应挂 subquestions[].attachments，挂单元上前端不渲染"))
        if kind == "standalone":
            for s in subs:                      # standalone 若真带子题，顺带查层级
                if isinstance(s, dict):
                    for a in s.get("attachments") or []:
                        if a.get("placement") == "option":
                            bad.append((uid, "选项图挂在子题上", "独立题的选项图应挂单元 attachments"))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="")
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    if not a.batch and not a.ids:
        ap.error("给 --batch 或 --ids")
    items = load_batch(a.batch) if a.batch else load_db(a.ids)

    bad = audit(items)
    print(f"扫描 {len(items)} 个单元，结构问题 {len(bad)} 处")
    for uid, kind, detail in bad:
        print(f"  ✗ {uid}: {kind}" + (f" — {detail}" if detail else ""))
    if bad:
        print("\n提示：unit_kind 与子题结构一旦入库无法 PATCH 修正，"
              "只能人工删除草稿后重传。上传前务必先跑本检查。")
        return 1
    print("✓ unit_kind / 子题 / 材料 / 选项图层级 均自洽")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
