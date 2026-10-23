# -*- coding: utf-8 -*-
"""答案闸门：把批次里每题的 answer 与答案册抽出的表逐题比对。

    python check_answers.py --batch 06_batch/batch_2025.json --answers 01_source_ans/answers.json
    python check_answers.py --batch b.json --answers answers.json --strict-words   # 主观题也卡

两个来源必须独立：
    答案表来自答案册（extract_answers.py 从原文抽），批次来自组装脚本。
    只有两边独立，抄错答案才会被抓到（2019 第 19、20 题填反就是这么漏的）。

判定：
    客观题（单字母 A–G）：必须完全一致，不一致即失败。
    主观题（单词/句子）：归一化后比对；一方包含另一方即视为「写法不同」只提示，
        加 --strict-words 才判失败；批次答案为空的，一律判失败。
    覆盖：答案表有、批次没有的题号 → 失败（漏题）；批次有、答案表没有 → 提示。

退出码：0 通过；1 有失败项；2 参数/文件错误。
"""
import argparse
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")


def norm_text(value):
    value = str(value or "").strip().lower()
    value = value.replace("’", "'").replace("‘", "'")
    value = re.sub(r"[\u3000\s]+", " ", value)
    value = re.sub(r"^(\d{1,3})\s*[.．、]\s*", "", value)   # 「16.school」这种带题号前缀
    return value.strip(" .。,，;；!！?？\"'“”‘’")


def numbers_of(batch):
    """批次 → {题号: (unit_id, answer)}；组题取子题，独立题取 id 末尾数字。"""
    out, units = {}, []
    for it in batch.get("items") or []:
        uid = it.get("id") or ""
        subs = it.get("subquestions") or []
        if subs:
            for s in subs:
                num = s.get("number")
                if isinstance(num, int):
                    out[num] = (uid, s.get("answer", ""))
            units.append(uid)
            continue
        m = re.search(r"(\d{1,3})$", uid)
        if m and it.get("type") != "书面表达":
            out[int(m.group(1))] = (uid, it.get("answer", ""))
        units.append(uid)
    return out, units


def main():
    ap = argparse.ArgumentParser(description="批次答案与答案册逐题比对")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--answers", required=True)
    ap.add_argument("--strict-words", action="store_true", help="主观题写法不同也算失败")
    a = ap.parse_args()

    if not os.path.exists(a.batch) or not os.path.exists(a.answers):
        print("文件不存在:", a.batch, a.answers)
        return 2
    batch = json.load(open(a.batch, encoding="utf-8-sig"))
    ans = json.load(open(a.answers, encoding="utf-8-sig"))
    expected = {int(k): v for k, v in (ans.get("numbers") or {}).items()}
    if not expected:
        print("答案表为空：先跑 extract_answers.py")
        return 2

    got, units = numbers_of(batch)
    hard, soft, missing, extra = [], [], [], []
    for num in sorted(expected):
        want = str(expected[num]).strip()
        if num not in got:
            missing.append(num)
            continue
        uid, actual = got[num]
        if not str(actual).strip():
            hard.append((num, uid, want, ""))
            continue
        if re.fullmatch(r"[A-Ga-g]", want):
            if str(actual).strip().rstrip(".").upper() != want.upper():
                hard.append((num, uid, want, actual))
            continue
        w, g = norm_text(want), norm_text(actual)
        if w == g:
            continue
        if w and g and (w in g or g in w):
            soft.append((num, uid, want, actual))
        elif a.strict_words:
            hard.append((num, uid, want, actual))
        else:
            soft.append((num, uid, want, actual))
    for num in sorted(set(got) - set(expected)):
        extra.append(num)

    letters = sum(1 for v in expected.values() if re.fullmatch(r"[A-Ga-g]", str(v).strip()))
    print(f"批次 {len(units)} 单元 / {len(got)} 个题号；答案表 {len(expected)} 题（客观 {letters}）")
    print(f"一致 {len(expected) - len(hard) - len(soft) - len(missing)} | 不一致 {len(hard)} "
          f"| 写法不同 {len(soft)} | 答案表有批次无 {len(missing)} | 批次有答案表无 {len(extra)}")
    for num, uid, want, actual in hard:
        print(f"  ✗ 第{num}题 {uid}: 答案册 {want!r} / 批次 {actual!r}")
    for num, uid, want, actual in soft:
        print(f"  ~ 第{num}题 {uid}: 答案册 {want!r} / 批次 {actual!r}")
    if missing:
        print(f"  ✗ 缺题: {missing}")
    if extra:
        print(f"  ? 答案表未收录: {extra}")

    if hard or missing:
        print("\n结论: 失败 —— 先修答案，再上传")
        return 1
    print("\n结论: 通过" + ("（主观题写法差异已提示，不阻断）" if soft else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
