# -*- coding: utf-8 -*-
"""阅读类单元体检：选项图 / 材料图 / 文章大意 / 空壳选项 / 空答案。

    python audit_reading.py --ids AH-2023          # 读库（草稿 + 已发布）
    python audit_reading.py --batch 06_batch/b.json # 上传前查批次

为什么要单独一个脚本：
    阅读题的图有两种位置，最容易错在层级：
      · 材料本身是图片（杂志目录、海报、表格）→ 单元 attachments，placement="question"
      · 某道小题的选项是图片（Which picture…）→ **子题** attachments，placement="option" + optionKey
    把选项图挂在单元上，前端渲染子题时读的是 subquestions[].attachments，图根本不会显示；
    这类错误不会报 400，肉眼在后台也只看到空选项（A. B. C. D. 后面什么都没有）。

判定（都是「该有却没有」，不是风格问题）：
    1. 子题 options 全是 A./B./C./D. 空壳，但子题没有 option 附件 → 选项图缺失
    2. 单元 material 为空、没有 question 图、也没有 materialBlocks → 材料缺失
    3. articleSummary 为空（答案册通常有【文章大意】）
    4. 子题 answer 为空（任务型/阅读问答常见）
退出码：0 无问题；1 有问题。
"""
import argparse
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")
REMOTE = "ubuntu@101.43.1.57"
READING_TYPES = ("阅读理解", "任务型阅读", "读写综合")
SHELLS = {"A.", "B.", "C.", "D.", "A", "B", "C", "D", ""}


def is_shell(options):
    return bool(options) and all(str(o).strip() in SHELLS for o in options)


def has_option_img(sub):
    return any(a.get("placement") == "option" and a.get("optionKey")
               for a in (sub.get("attachments") or []))


def has_question_img(item):
    return any(a.get("placement") == "question" and (a.get("kind") or a.get("type")) == "image"
               for a in (item.get("attachments") or []))


def audit(items):
    problems = []
    for it in items:
        uid = it.get("id") or it.get("unit_id")
        qtype = it.get("type") or it.get("question_type") or ""
        if qtype not in READING_TYPES:
            continue
        subs = it.get("subquestions") or []
        for s in subs:
            if is_shell(s.get("options")) and not has_option_img(s):
                problems.append((uid, qtype, "选项图缺失",
                                 f"第{s.get('number')}题选项是空壳 A./B./C./D.，但子题没有 option 附件"))
            if not str(s.get("answer") or "").strip():
                problems.append((uid, qtype, "子题答案为空", f"第{s.get('number')}题"))
        blocks = it.get("materialBlocks") or it.get("material_blocks") or []
        if not str(it.get("material") or "").strip() and not has_question_img(it) and not blocks:
            problems.append((uid, qtype, "材料缺失", "material 空、无 question 图、无 materialBlocks"))
        if not str(it.get("articleSummary") or it.get("article_summary") or "").strip():
            problems.append((uid, qtype, "无文章大意", "答案册若有【文章大意】需回填"))
    return problems


def load_batch(path):
    batch = json.load(open(path, encoding="utf-8-sig"))
    return [it for it in batch.get("items") or []]


def load_db(prefix):
    py = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = []
for r in con.execute("""select q.unit_id, q.question_type, q.article_summary, q.attachments_json,
                               q.subquestions_json, q.material, q.material_blocks_json
                        from questions q join question_units u on u.id=q.unit_id
                        where q.question_type in ('阅读理解','任务型阅读','读写综合')
                          and q.unit_id like '{prefix}%'"""):
    rows.append({{"id": r[0], "type": r[1], "articleSummary": r[2],
                  "attachments": json.loads(r[3] or "[]"),
                  "subquestions": json.loads(r[4] or "[]"),
                  "material": r[5], "materialBlocks": json.loads(r[6] or "[]")}})
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          REMOTE, "python3 -"], input=py, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 失败: " + out.stderr[:200])
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="", help="单元前缀，如 AH-2023")
    ap.add_argument("--batch", default="", help="批次 json（上传前）")
    a = ap.parse_args()
    if not a.ids and not a.batch:
        ap.error("给 --ids 或 --batch")
    items = load_batch(a.batch) if a.batch else load_db(a.ids)

    problems = audit(items)
    print(f"阅读类单元 {len([i for i in items if (i.get('type') or '') in READING_TYPES])} 个，"
          f"问题 {len(problems)} 处")
    from collections import Counter
    for (kind, n) in Counter(p[2] for p in problems).most_common():
        print(f"  {kind}: {n}")
    for uid, qtype, kind, detail in problems:
        print(f"    {uid} [{qtype}] {kind} — {detail}")
    if problems:
        print("\n修法：选项图挂 subquestions[].attachments（placement=option + optionKey）；"
              "材料图挂单元 attachments（placement=question）。")
        return 1
    print("✓ 选项图 / 材料图 / 文章大意 / 子题答案 均无缺口")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
