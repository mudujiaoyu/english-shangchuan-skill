# -*- coding: utf-8 -*-
"""按 type-knowledge-map.json 的新标准，重审并修正已入库草稿的知识点。

原则：不是无脑覆盖，而是「纠错 + 补缺 + 保留精确项」：
  1) 删掉该题型禁标的维度（完形挂语法/辨析、单项挂主题…）
  2) 补上该题型的默认标签（缺才补，已有精确标签不删）
  3) 阅读类题组的每个子题必须有一个 阅读技能/* 标签
默认 dry-run，加 --apply 才写。
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(SKILL, "references", "knowledge-catalog.json")
MAP = os.path.join(SKILL, "references", "type-knowledge-map.json")
KEY = open(os.path.expanduser(r"~\.mudu\api_key.txt"), encoding="ascii").read().strip()
BASE = "http://127.0.0.1:8089/api"
REMOTE = "ubuntu@101.43.1.57"
SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")

FORBIDDEN = {
    "完形填空": ("语法/", "词汇/词汇辨析"),
    "单项填空": ("主题/", "语篇体裁/"),
    "听力短对话理解": ("语法/",), "听力长对话理解": ("语法/",), "听力短文理解": ("语法/",),
    "听力信息转换": ("语法/",), "听力判断": ("语法/",), "听力排序": ("语法/",),
    "听力问答": ("语法/",), "听力其他": ("语法/",),
    "阅读理解": ("语法/", "词汇/词汇辨析"),
    "单词拼写": ("语法/",),
}

# 该题型「至少要覆盖」的维度；缺了才用默认标签补，已有同类标签不再叠
REQUIRED_DIMS = {
    "听力短对话理解": ["语篇体裁"], "听力长对话理解": ["语篇体裁"], "听力短文理解": ["语篇体裁"],
    "听力信息转换": ["语篇体裁"], "听力判断": ["语篇体裁"], "听力排序": ["语篇体裁"],
    "听力问答": ["语篇体裁"], "听力其他": ["语音"],
    "完形填空": ["语篇体裁", "主题"],
    "阅读理解": ["语篇体裁", "主题"],
    "补全对话": ["语用"],
    "书面表达": ["语篇体裁"],
    "单词拼写": ["词汇"],
    "任务型阅读": ["阅读技能"],
}
OVERRIDES = {
    # 2020 完形
    "AH-2020-031": ["语篇体裁/记叙文/故事", "主题/人与自我/生活与学习/语言学习"],
    "AH-2020-041": ["语篇体裁/说明文/介绍类短文", "主题/人与社会/科学与技术/科学技术"],
    # 2020 补全对话
    "AH-2020-051": ["语用/情景交际", "语篇体裁/日常口语/日常对话",
                    "主题/人与自我/生活与学习/学校生活"],
    # 2020 阅读
    "AH-2020-056": ["阅读技能/细节理解", "语篇体裁/说明文/介绍类短文",
                    "主题/人与自我/生活与学习/生活态度"],
    "AH-2020-059": ["阅读技能/细节理解", "语篇体裁/记叙文/人物传记",
                    "主题/人与自我/做人与做事/自我认识与提升"],
    "AH-2020-063": ["阅读技能/细节理解", "语篇体裁/记叙文/故事",
                    "主题/人与自我/做人与做事/自我认识与提升"],
    "AH-2020-066": ["阅读技能/细节理解", "语篇体裁/记叙文/人物传记",
                    "主题/人与自然/环境保护/绿色生活与环保行动"],
    "AH-2020-069": ["阅读技能/细节理解", "语篇体裁/说明文/介绍类短文",
                    "主题/人与社会/社会服务与人际沟通/语言与跨文化交流"],
    # 2020 任务型阅读
    "AH-2020-073": ["阅读技能/细节理解", "语篇体裁/记叙文/童话",
                    "主题/人与自然/自然生态/与自然和谐共生"],
    # 2020 书面表达
    "AH-2020-081": ["语篇体裁/应用文", "主题/人与自我/做人与做事/职业启蒙与职业精神"],
    # 2020 听力：补主题（原有语篇体裁保留）
    "AH-2020-001": ["主题/人与社会/社会服务与人际沟通/家庭生活"],
    "AH-2020-002": ["主题/人与自我/生活与学习/日常活动"],
    "AH-2020-003": ["主题/人与自我/生活与学习/日常活动"],
    "AH-2020-004": ["主题/人与社会/社会服务与人际沟通/人际交往"],
    "AH-2020-005": ["主题/人与社会/社会服务与人际沟通/人际交往"],
    "AH-2020-006": ["主题/人与自我/生活与学习/日常活动"],
    "AH-2020-008": ["主题/人与自然/自然生态/气候与天气"],
    "AH-2020-011": ["主题/人与自我/做人与做事/职业启蒙与职业精神"],
    "AH-2020-016": ["主题/人与自然/环境保护/绿色生活与环保行动"],
    # 2020 单词拼写：拼写属词汇，不属语法
    "AH-2020-076": ["词汇"],
    "AH-2020-077": ["词汇"],
    "AH-2020-078": ["词汇"],
    "AH-2020-079": ["词汇"],
    "AH-2020-080": ["词汇"],
}


def load_index():
    data = json.load(open(INDEX, encoding="utf-8"))
    id2path = {p["id"]: p["path"] for p in data["points"]}
    name2paths = {}
    for p in data["points"]:
        name2paths.setdefault(p["name"], []).append(p["path"])
    return id2path, name2paths


def fetch(prefix):
    prefix = prefix.rstrip("%")
    py = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = [list(r) for r in con.execute(
    "select q.unit_id,q.question_type,q.knowledge_json,q.knowledge_ids_json,q.subquestions_json "
    "from questions q where q.unit_id like '{prefix}%'")]
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          REMOTE, "python3 -"], input=py, capture_output=True, text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 读取失败: " + out.stderr[:300])
    return json.loads(out.stdout)


def patch(qid, paths, id2path):
    rev = {v: k for k, v in id2path.items()}
    ids = [rev[p] for p in paths if p in rev]
    names = [p.split("/")[-1] for p in paths if p in rev]
    body = json.dumps({"knowledge": names, "knowledgeIds": ids}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{BASE}/questions/{qid}", data=body, method="PATCH",
                                 headers={"Authorization": f"Bearer {KEY}",
                                          "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:160]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ids", default="AH-2010-,AH-2018-,AH-2019-")
    a = ap.parse_args()

    id2path, name2paths = load_index()
    tmap = json.load(open(MAP, encoding="utf-8"))

    def to_paths(names, ids):
        paths = []
        for i in ids or []:
            if i in id2path:
                paths.append(id2path[i])
        for n in names or []:
            cand = name2paths.get(n, [])
            if len(cand) == 1 and cand[0] not in paths:
                paths.append(cand[0])
        return paths

    total = changed = 0
    details = []
    unfixable = []
    for prefix in [x for x in a.ids.split(",") if x]:
        for uid, qtype, kj, kid, sj in fetch(prefix):
            total += 1
            cur = to_paths(json.loads(kj or "[]"), json.loads(kid or "[]"))
            bad = FORBIDDEN.get(qtype, ())
            new = [p for p in cur if not any(p.startswith(b) for b in bad)]
            removed = [p for p in cur if p not in new]
            added = []
            if uid in OVERRIDES:
                # 逐篇判定过：在「过滤后的现有标签」上补缺失项，不覆盖原有的精确标签
                for p in OVERRIDES[uid]:
                    if p in new:
                        continue
                    # 已有任一阅读技能标签时，不再补通用的「细节理解」占位
                    if p.startswith("阅读技能/") and any(q.startswith("阅读技能/") for q in new):
                        continue
                    new.append(p)
                added = [p for p in new if p not in cur]
            else:
                # 维度兜底：某题型要求覆盖的维度完全缺失时，用该维度的默认标签补一条
                defaults = (tmap.get(qtype) or {}).get("defaults") or []
                for dim in REQUIRED_DIMS.get(qtype, []):
                    if any(p.split("/")[0] == dim for p in new):
                        continue
                    pick = next((d for d in defaults
                                 if d == dim or d.startswith(dim + "/")), None)
                    if pick and pick not in new:
                        new.append(pick)
                        added.append(pick)
                    elif not pick:
                        unfixable.append((uid, qtype, dim))
            if new != cur:
                changed += 1
                details.append((uid, qtype, removed, added))
                if a.apply:
                    code, msg = patch(uid, new, id2path)
                    if code != 200:
                        print("FAIL", uid, code, msg)
    print(("APPLY " if a.apply else "DRY-RUN ") + f"检查 {total} 个单元 | 需修正 {changed}")
    for uid, qtype, rm, ad in details[:15]:
        print(f"  {uid} [{qtype}] -{len(rm)} +{len(ad)}  删:{[p.split('/')[-1] for p in rm][:3]} 补:{[p.split('/')[-1] for p in ad][:3]}")
    if unfixable:
        print(f'  需逐篇判定（默认标签补不了）: {len(unfixable)} 个')
        for uid, qt, dim in unfixable[:8]:
            print(f'    {uid} [{qt}] 缺维度: {dim}')
    if len(details) > 15:
        print(f"  … 其余 {len(details)-15} 个")


if __name__ == "__main__":
    main()
