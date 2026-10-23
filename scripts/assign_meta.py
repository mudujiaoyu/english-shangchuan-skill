# -*- coding: utf-8 -*-
"""按「可观测特征」给题目算难度与分类，规则全在 references/difficulty-category.json。

依据 developer.md：
  difficulty        易 / 中 / 难（编辑最终确认）
  filterMetadata.difficultyValue   0~1（>=0.8 容易，>=0.5 适中）
  filterMetadata.categories        优选题 / 易错题
文档明确「未知值留空，不要根据题型猜造标注」——特征不足时置 null 并列入待编辑清单。

    python assign_meta.py --batch b.json --report           # 看分布与依据
    python assign_meta.py --batch b.json --out b_meta.json  # 写回批次
    python assign_meta.py --ids AH-2021 --apply             # 补已入库草稿（先读后合并）
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.path.join(SKILL, "references", "difficulty-category.json")
INDEX = os.path.join(SKILL, "references", "knowledge-catalog.json")
KEY_FILE = os.path.expanduser(r"~\.mudu\api_key.txt")
BASE = "http://127.0.0.1:8089/api"
SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*")

_NAME2PATH = {}


def name2path():
    global _NAME2PATH
    if not _NAME2PATH:
        for pt in json.load(open(INDEX, encoding="utf-8"))["points"]:
            _NAME2PATH.setdefault(pt["name"], pt["path"])
    return _NAME2PATH


def hit(prefixes, kpaths):
    m = name2path()
    resolved = [k if "/" in k else m.get(k, k) for k in kpaths]
    for p in prefixes or []:
        for k in resolved:
            if k == p or k.startswith(p + "/"):
                return True
    return False


def features(item):
    text = (item.get("material") or "") + "\n" + (item.get("stem") or "")
    for s in item.get("subquestions") or []:
        text += "\n" + (s.get("stem") or "")
    words = WORD_RE.findall(text)
    n = len(words)
    sentences = [s for s in re.split(r"[.!?。！？]+", text) if len(WORD_RE.findall(s)) >= 3]
    avg_len = round(n / len(sentences), 1) if sentences else 0.0
    long_ratio = round(sum(1 for w in words if len(w) >= 8) / n, 2) if n else 0.0

    # 只认真有文字的选项；"A." / "B." 这类图片题占位符不算同质干扰
    opts = [o for o in (item.get("options") or [])
            if isinstance(o, str) and len(o.strip()) > 3]
    homogeneous = False
    if 3 <= len(opts) <= 5:
        lens = [len(o) for o in opts]
        homogeneous = (max(lens) - min(lens)) <= 2

    kpaths = list(item.get("knowledge") or [])
    for s in item.get("subquestions") or []:
        kpaths += list(s.get("knowledge") or [])
    return {"word_count": n, "avg_sentence_len": avg_len, "long_word_ratio": long_ratio,
            "option_homogeneous": homogeneous, "kpaths": kpaths}


def score_of(rules, qtype, feat):
    cfg = rules["feature_scoring"]
    prompt_base = (cfg.get("prompt_only_types") or {}).get(qtype)
    if prompt_base is not None:
        score = float(prompt_base)
        basis = [f"{qtype} 按题型基准 {prompt_base:.2f}（题目要求不计入阅读量）"]
    else:
        score = float(cfg["start"])
        basis = []

    for r in ([] if prompt_base is not None else cfg["rules"]):
        v = feat.get(r["feature"])
        if v is None:
            continue
        if "gte" in r and "lt" in r:
            ok = r["gte"] <= v < r["lt"]
        elif "lt" in r:
            ok = v < r["lt"]
        elif "gte" in r:
            ok = v >= r["gte"]
        else:
            ok = v == r.get("eq")
        if ok:
            score += float(r["delta"])
            basis.append(r["basis"])

    for r in cfg["knowledge_rules"]:
        if hit(r["when_knowledge_any"], feat["kpaths"]):
            score += float(r["delta"])
            basis.append(r["basis"])

    for comp in cfg.get("composite_rules") or []:
        ok = True
        for cond in comp["all"]:
            if "word_count_gte" in cond and feat["word_count"] < cond["word_count_gte"]:
                ok = False
            if "when_knowledge_any" in cond and not hit(cond["when_knowledge_any"], feat["kpaths"]):
                ok = False
        if ok:
            score += float(comp["delta"])
            basis.append(comp["basis"])

    prior = (cfg.get("type_prior") or {}).get(qtype)
    if prior:
        score += float(prior)
        basis.append(f"题型先验 {prior:+.2f}")

    return round(max(0.30, min(0.95, score)), 2), basis


def label_of(value, bands):
    if value is None:
        return ""
    return "容易" if value >= bands["容易"] else "适中" if value >= bands["适中"] else "困难"


def categories_of(rules, qtype, feat):
    out, basis = [], []
    for name, rule in (rules.get("categories") or {}).items():
        ok = hit(rule.get("when_knowledge_any", []), feat["kpaths"])
        if (not ok and rule.get("when_option_homogeneous") and feat["option_homogeneous"]
                and qtype in (rule.get("when_option_homogeneous_types") or [])):
            ok = True
        if not ok and qtype in (rule.get("when_types") or []):
            ok = True
        if ok:
            out.append(name)
            basis.append(rule.get("basis", name))
    return out, basis


def decorate(rules, item, has_ts=False, duration=None):
    qtype = item.get("type") or item.get("question_type") or ""
    feat = features(item)
    bands = rules["doc_constraints"]["difficulty_value_bands"]

    no_evidence = (qtype in (rules["feature_scoring"].get("no_evidence_types") or [])
                   and not has_ts and duration is None)
    if no_evidence:
        value = None
        basis = [rules["feature_scoring"].get("no_evidence_note", "无文本依据")]
    elif qtype in (rules["feature_scoring"].get("no_evidence_types") or []) and duration is not None:
        value, basis = None, []
        for band in rules["feature_scoring"]["audio_duration_scoring"]["bands"]:
            if duration < band["lt"]:
                value, basis = float(band["value"]), [band["basis"]]
                break
    else:
        value, basis = score_of(rules, qtype, feat)

    cats, cat_basis = categories_of(rules, qtype, feat)

    fm = item.setdefault("filterMetadata", {})
    fm["difficultyValue"] = value
    fm["categories"] = cats
    item["difficulty"] = label_of(value, bands)
    item["_metaBasis"] = {"difficulty": basis, "categories": cat_basis, "features": feat}
    return item


def fetch(prefix):
    import subprocess
    py = f'''
import sqlite3, json
con = sqlite3.connect("file:/home/ubuntu/mudu-quiz/data/mudu.sqlite3?mode=ro", uri=True)
rows = [list(r) for r in con.execute(
  "select q.unit_id,q.question_type,q.stem,q.material,q.options_json,q.difficulty,"
  "q.knowledge_json,q.filter_metadata_json,q.subquestions_json "
  "from questions q where q.unit_id like '{prefix}%'")]
print(json.dumps(rows, ensure_ascii=False))
'''
    out = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                          "ubuntu@101.43.1.57", "python3 -"], input=py, capture_output=True,
                         text=True, encoding="utf-8")
    if out.returncode != 0:
        raise SystemExit("ssh 失败: " + out.stderr[:200])
    return json.loads(out.stdout)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch")
    ap.add_argument("--out")
    ap.add_argument("--ids")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--tapescripts", help="听力稿 JSON：{unit_id: text}，只用于算特征，不写入 material")
    ap.add_argument("--durations", help="音频时长 JSON：{unit_id: seconds}，无听力稿时的负荷代理")
    a = ap.parse_args()
    rules = json.load(open(RULES, encoding="utf-8"))
    tapes = {}
    if a.tapescripts:
        tapes = json.load(open(a.tapescripts, encoding="utf-8"))
    durations = {}
    if a.durations:
        durations = json.load(open(a.durations, encoding="utf-8-sig"))

    if a.batch:
        batch = json.load(open(a.batch, encoding="utf-8-sig"))
        for it in batch["items"]:
            ts = tapes.get(it.get("id"))
            if ts:
                saved, it["material"] = it.get("material"), ts
                decorate(rules, it, has_ts=True)
                it["material"] = saved
            else:
                decorate(rules, it, has_ts=False)
        if a.report:
            from collections import Counter
            c = Counter((i["type"], i["difficulty"] or "待定") for i in batch["items"])
            cats = Counter(cat for i in batch["items"] for cat in i["filterMetadata"]["categories"])
            for (t, d), n in sorted(c.items()):
                print(f"  {t:14s} {d}  ×{n}")
            print("  分类:", dict(cats) or "无")
            pending = [i["id"] for i in batch["items"] if i["filterMetadata"]["difficultyValue"] is None]
            print(f"  待编辑定难度: {len(pending)} 个 {pending[:6]}")
            for i in batch["items"][:3]:
                b = i["_metaBasis"]
                print(f"    例 {i['id']}: {i['difficulty'] or '待定'} | "
                      f"{'；'.join(b['difficulty'][:2])} | {b['features']['word_count']} 词")
        out = a.out or (None if a.report else a.batch.replace(".json", "_meta.json"))
        if out:
            for it in batch["items"]:
                it.pop("_metaBasis", None)
            json.dump(batch, open(out, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
            print("写出:", out)
        return 0

    if a.ids:
        import urllib.error
        import urllib.request
        rows = fetch(a.ids)
        key = open(KEY_FILE, encoding="ascii").read().strip()
        ok, fail, pending = 0, [], []
        for uid, qtype, stem, mat, opts, diff, kj, fm, sj in rows:
            ts = tapes.get(uid)
            dur = durations.get(uid)
            item = {"type": qtype, "stem": stem or "", "material": (ts or mat or ""),
                    "options": json.loads(opts or "[]"), "knowledge": json.loads(kj or "[]"),
                    "filterMetadata": json.loads(fm or "{}"), "subquestions": json.loads(sj or "[]")}
            decorate(rules, item, has_ts=bool(ts), duration=dur)
            if item["filterMetadata"]["difficultyValue"] is None:
                pending.append(uid)
            body = json.dumps({"difficulty": item["difficulty"],
                               "filterMetadata": item["filterMetadata"]},
                              ensure_ascii=False).encode("utf-8")
            if not a.apply:
                print(f"  {uid} {qtype} -> {item['difficulty'] or '待定'} "
                      f"{item['filterMetadata']['difficultyValue']} {item['filterMetadata']['categories']}")
                ok += 1
                continue
            req = urllib.request.Request(f"{BASE}/questions/{uid}", data=body, method="PATCH",
                                         headers={"Authorization": f"Bearer {key}",
                                                  "Content-Type": "application/json; charset=utf-8"})
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    r.read()
                ok += 1
            except urllib.error.HTTPError as e:
                fail.append((uid, e.code, e.read().decode("utf-8", "replace")[:100]))
        print(("APPLY " if a.apply else "DRY-RUN ") + f"{ok} 个 | 失败 {len(fail)} | 待定 {len(pending)}")
        for f in fail[:5]:
            print("  FAIL", f)
        return 0

    ap.error("需要 --batch 或 --ids")


if __name__ == "__main__":
    raise SystemExit(main())
