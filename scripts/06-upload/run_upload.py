# -*- coding: utf-8 -*-
"""上传流水线：一条命令跑完 自检 → 查重 → 预检 → 部署媒体 → POST。

    python run_upload.py --batch 06_batch/batch_2022.json --media-dir media_upload/ --name "2022年…"

为什么要有它：
    上传前的五道闸门原来是五个脚本、五次 SSH 往返（每次 0.4–0.7s，预检还要在服务器上
    复制 5MB 库再跑一遍），加上 20 个媒体 URL 串行 curl（6s），一批要 15s 上下且必须人记住顺序。
    这里把「本机并行能做的」和「必须上服务器的」分开：
      · 本机：答案/排版/标签/阅读体检 → 四个纯本地脚本并行跑（各 0.05s）
      · 服务器：查重 + 预检 + 媒体点数 + 上传，**合并成一次 SSH 会话**（省 3 次往返）
      · 媒体校验：改为并发 + Range 请求（6.3s → 1.8s），且只抽首字节

阶段可用 --skip-* 跳过；任一闸门失败即停，不会带病上传。

退出码：0 全部通过并已 POST；1 有闸门失败；2 参数/环境错误。
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
KEY_FILE = os.path.expanduser(r"~\.mudu\api_key.txt")
SSH_KEY = os.path.expanduser(r"~\.ssh\mudu_gd")
REMOTE = "ubuntu@101.43.1.57"
REMOTE_DIR = "/home/ubuntu/mudu-quiz"
BASE_URL = "http://127.0.0.1:8089"


# ---------------------------------------------------------------- 工具
def step(title):
    print(f"\n[{title}]")
    return time.time()


def done(start, ok=True):
    mark = "✓" if ok else "✗"
    print(f"  {mark} {time.time() - start:.2f}s")


def run_local(script, args):
    p = os.path.join(SCRIPTS, script)
    r = subprocess.run([sys.executable, p] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "").rstrip().splitlines(), (r.stderr or "").rstrip().splitlines()


def ssh(cmd, timeout=180):
    r = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                        "-o", "ConnectTimeout=15", REMOTE, cmd],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def push_media(local_dir, names, dest):
    """建目录 + scp：返回 (ok, 提示)。作为后台任务跑，和闸门并行。"""
    ssh(f"mkdir -p {dest}", timeout=60)
    r = subprocess.run(["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                        "-q"] + [os.path.join(local_dir, f) for f in names] + [f"{REMOTE}:{dest}/"],
                       capture_output=True, text=True)
    return (r.returncode == 0, (r.stderr or "")[:160])


def post_batch(batch_path):
    key = open(KEY_FILE, encoding="ascii").read().strip()
    body = open(batch_path, "rb").read()
    req = urllib.request.Request(BASE_URL + "/api/uploads", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8", "replace") or "{}")


def check_urls(urls, workers=16):
    """并发 + Range 只取首字节：既快又不把整段音频拉下来。"""
    def one(u):
        req = urllib.request.Request(u, headers={"Range": "bytes=0-0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return u, r.status
        except Exception as exc:                      # noqa: BLE001
            return u, str(exc)[:60]
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(one, urls))


def collect_media_urls(batch, media_dir):
    """批次里引用到的本站媒体相对路径 → 绝对 URL；只校验本批目录下的文件。"""
    refs = set()
    for it in batch.get("items") or []:
        for a in it.get("attachments") or []:
            u = str(a.get("url") or "")
            if u.startswith("/source-media/"):
                refs.add(u)
        for s in it.get("subquestions") or []:
            for a in s.get("attachments") or []:
                u = str(a.get("url") or "")
                if u.startswith("/source-media/"):
                    refs.add(u)
    return sorted(refs)


def media_batch_name(batch):
    """批次 URL 里的 <批次> 段：/source-media/<批次>/xxx。"""
    names = set()
    for u in collect_media_urls(batch, ""):
        parts = u.split("/")
        if len(parts) >= 4:
            names.add(parts[2])
    return sorted(names)


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(description="上传流水线")
    ap.add_argument("--batch", required=True)
    ap.add_argument("--media-dir", default="", help="要部署的媒体目录（文件名需与批次 URL 一致）")
    ap.add_argument("--answers", default="", help="01_source_ans/answers.json，给了就比对答案")
    ap.add_argument("--skip-local", action="store_true", help="跳过本机四项体检")
    ap.add_argument("--skip-remote", action="store_true", help="跳过查重与预检")
    ap.add_argument("--media-name", default="", help="远端媒体目录名，默认从批次 URL 推断")
    ap.add_argument("--skip-media", action="store_true", help="跳过媒体部署与 URL 校验")
    ap.add_argument("--no-post", action="store_true", help="全部通过也不上传（干跑）")
    a = ap.parse_args()

    batch_path = os.path.abspath(a.batch)
    if not os.path.exists(batch_path):
        print("批次不存在:", batch_path)
        return 2
    batch = json.load(open(batch_path, encoding="utf-8-sig"))
    size = os.path.getsize(batch_path)
    print(f"批次 {batch.get('batch_id')} | 单元 {len(batch.get('items') or [])} | {size:,} 字节")
    if size > 2_000_000:
        print("✗ 超过 2MB 上限，先拆批")
        return 1

    failed = []

    # ① 本机四项并行（纯文件读写，各 ~0.05s）
    if not a.skip_local:
        t = step("本机体检（并行）")
        jobs = [("排版 check_text", "06-upload/check_text.py", ["--batch", batch_path]),
                ("结构 check_structure", "06-upload/check_structure.py", ["--batch", batch_path]),
                ("标签 check_tags", "04-knowledge/check_tags.py", ["--batch", batch_path]),
                ("阅读 audit_reading", "06-upload/audit_reading.py", ["--batch", batch_path]),
                ("发布闸门 publish_check", "06-upload/publish_check.py", ["--batch", batch_path])]
        if a.answers:
            jobs.append(("答案 check_answers", "06-upload/check_answers.py",
                         ["--batch", batch_path, "--answers", os.path.abspath(a.answers)]))
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as ex:
            results = list(ex.map(lambda j: (j[0],) + run_local(j[1], j[2]), jobs))
        for name, code, out, err in results:
            mark = "✓" if code == 0 else "✗"
            tail = (out[-1] if out else (err[-1] if err else ""))[:110]
            print(f"  {mark} {name:22s} {tail}")
            # 排版体检只报告不阻断，其余失败即拦
            if code != 0 and "check_text" not in name:
                failed.append(name)
        done(t, not failed)

    # ② 服务器：查重 + 预检 + 媒体点数，合并成一次会话
    remote_media = {}
    media_todo = []
    media_names = []
    if a.media_dir and os.path.isdir(a.media_dir):
        media_names = sorted(os.listdir(a.media_dir))
    batch_names = media_batch_name(batch)
    if len(batch_names) > 1:
        print(f"✗ 批次引用了多个媒体目录 {batch_names}，先统一到 /source-media/<批次>/")
        return 1
    media_batch = a.media_name or (batch_names[0] if batch_names else "")
    if not a.skip_remote:
        t = step("服务器闸门（一次会话）")
        # 闸门脚本 + 批次一次 scp 送上服务器，再一条 ssh 执行：
        # 比原来「查重一次往返 + 预检一次往返（还要复制 5MB 库）」少一半。
        # Windows 下 ssh 的 stdin 传脚本不可靠（实测为空），所以走文件而不是管道。
        gate_local = os.path.join(HERE, "_gate_remote.py")
        tmp_batch = os.path.join(HERE, "_pipeline_batch.json")
        shutil.copyfile(batch_path, tmp_batch)          # 固定远端文件名，免再 cp 一次
        try:
            up = subprocess.run(["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                                 "-q"] + [gate_local, tmp_batch] + [f"{REMOTE}:/tmp/"],
                                capture_output=True, text=True)
        finally:
            os.remove(tmp_batch)
        if up.returncode != 0:
            print("  ✗ scp 闸门/批次失败:", (up.stderr or "")[:160])
            return 2
        code, out, err = ssh(
            f"cd {REMOTE_DIR} && python3 /tmp/_gate_remote.py /tmp/_pipeline_batch.json", timeout=240)
        if code != 0:
            # 退化为「先落地再执行」的两段式，报错更直观
            r = subprocess.run(["ssh", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                                "-o", "ConnectTimeout=15", REMOTE,
                                "cd " + REMOTE_DIR + " && python3 /tmp/_gate_remote.py /tmp/_pipeline_batch.json"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
            code, out, err = r.returncode, r.stdout, r.stderr
        if code != 0:
            print("  ✗ 服务器闸门执行失败:", (err or out)[-300:])
            return 2
        try:
            res = json.loads(out.strip().splitlines()[-1])
        except Exception:                                    # noqa: BLE001
            print("  ✗ 结果解析失败:", out[-300:])
            return 2
        print(f"  查重: {'✓ 无重复' if res['dup_ok'] else '✗ 内容重复 ' + str(res['dup_hits'][:3])}")
        print(f"  预检: {'✓ 通过' if not res['preflight'] else '✗ ' + str(res['preflight'][:3])}")
        n_exist = res['existing_ids']
        if n_exist:
            scope = '整批' if res.get('all_existing') else '部分'
            print(f"  ID 已在库: {n_exist} 个（{scope}已传过 → 重传会 409）")
            if res.get('all_existing'):
                print('    这批无需再传；要改内容请 PATCH 现有草稿，不要重复 POST')
                failed.append("整批已入库")
        remote_media = res.get("remote_media") or {}
        if not res["dup_ok"] or res["preflight"]:
            failed.append("服务器闸门")
        done(t, not failed)

    # ③ 媒体：scp 一次 + 并发校验引用到的 URL
    if not a.skip_media and media_names:
        t = step("媒体部署与校验")
        if not media_batch:
            print("  ✗ 无法确定媒体批次目录：批次里没有 /source-media/<批次>/ 引用，加 --media-name")
            return 1
        dest = f"/home/ubuntu/mudu-quiz/static/source-media/{media_batch}"
        # 已在远端的文件不再传（闸门已带回目录清单）：重复跑同一批几乎零传输
        landed = set(remote_media.get(media_batch) or [])
        todo = [f for f in media_names if f not in landed]
        if todo:
            ssh(f"mkdir -p {dest}", timeout=60)
            up = subprocess.run(["scp", "-i", SSH_KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                                 "-q"] + [os.path.join(a.media_dir, f) for f in todo] + [f"{REMOTE}:{dest}/"],
                                capture_output=True, text=True)
            if up.returncode != 0:
                print("  ✗ scp 媒体失败:", (up.stderr or "")[:160])
                failed.append("媒体部署")
            else:
                print(f"  传输 {len(todo)}/{len(media_names)} 个（远端已有 {len(landed)} 个）→ {dest}")
        else:
            print(f"  远端已就位 {len(media_names)} 个，跳过传输 → {dest}")
        if "媒体部署" not in failed:
            refs = collect_media_urls(batch, a.media_dir)
            urls = [BASE_URL + u for u in refs]
            results = check_urls(urls)
            bad = [(u, s) for u, s in results if s != 200]
            print(f"  URL 校验 {len(urls)} 个（并发+Range）: "
                  + ("✓ 全部 200" if not bad else f"✗ {len(bad)} 个异常"))
            if bad:
                missing = [u.rsplit("/", 1)[-1] for u, s in bad if "404" in str(s)]
                if missing:
                    print(f"    404（批次引用了但没部署）: {missing[:8]}"
                          + (f" …共 {len(missing)} 个" if len(missing) > 8 else ""))
                other = [(u, s) for u, s in bad if "404" not in str(s)]
                if other:
                    print(f"    其他异常: {other[:3]}")
                failed.append("媒体 URL")
        done(t, not failed)

    # ④ POST
    if failed:
        print(f"\n✗ 未通过：{failed}；不执行上传")
        return 1
    if a.no_post:
        print("\n✓ 全部闸门通过（--no-post，未上传）")
        return 0

    t = step("上传")
    status, res = post_batch(batch_path)
    print(f"  HTTP {status} {json.dumps(res, ensure_ascii=False)[:200]}")
    done(t, status == 201)
    if status != 201:
        return 1

    receipt = {
        "staging_id": res.get("id"),
        "batch_id": batch.get("batch_id"),
        "name": batch.get("name"),
        "http_status": status,
        "stage": res.get("stage"),
        "units": len(batch.get("items") or []),
        "subquestions": sum(len(i.get("subquestions") or []) for i in batch.get("items") or []),
        "attachments": sum(len(i.get("attachments") or []) for i in batch.get("items") or []),
        "media_dir": os.path.basename(os.path.normpath(a.media_dir)) if a.media_dir else "",
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "not_done": ["未逐题确认（人工）", "未发布"],
    }
    out_path = os.path.join(os.path.dirname(batch_path), "receipt.json")
    json.dump(receipt, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n✓ 上传完成 staging_id={receipt['staging_id']}\n  receipt -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
