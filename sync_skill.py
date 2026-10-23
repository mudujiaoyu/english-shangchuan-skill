# -*- coding: utf-8 -*-
"""把技能仓库同步到本机技能目录，并跑自检。

    python sync_skill.py                 # 复制（默认）
    python sync_skill.py --mode link     # 建立目录联接，改仓库即生效
    python sync_skill.py --skip-verify

以仓库为唯一源：改完仓库执行一次，技能目录即为最新。
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
REPO = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DEST = os.path.join(os.path.expanduser("~"), ".agents", "skills", "mudu-question-upload")
SKIP = {".git", "__pycache__"}
SKIP_EXT = {".pyc", ".pyo"}


def find_python():
    cand = (r"C:\Users\Administrator\.dsh\dsh-runtimes\dsh-primary-runtime"
            r"\dependencies\python\python.exe")
    return cand if os.path.exists(cand) else sys.executable


def remove_dest(dest):
    if not os.path.exists(dest) and not os.path.islink(dest):
        return
    if os.path.islink(dest) or os.path.isjunction(dest):
        os.rmdir(dest)          # 只删链接本身
    else:
        shutil.rmtree(dest)


def copy_tree(src, dst):
    n = 0
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in SKIP]
        rel = os.path.relpath(root, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for f in files:
            if os.path.splitext(f)[1] in SKIP_EXT:
                continue
            shutil.copy2(os.path.join(root, f), os.path.join(target, f))
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["copy", "link"], default="copy")
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--skip-verify", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(os.path.join(REPO, "SKILL.md")):
        raise SystemExit("当前目录不是技能仓库根：%s" % REPO)
    dest = os.path.abspath(a.dest)
    print("源:   ", REPO)
    print("目标: ", dest)
    print("模式: ", a.mode)

    remove_dest(dest)
    if a.mode == "link":
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if sys.platform == "win32":
            r = subprocess.run(["cmd", "/c", "mklink", "/J", dest, REPO],
                               capture_output=True, text=True)
            if r.returncode != 0:
                raise SystemExit("建立目录联接失败: " + (r.stderr or r.stdout))
        else:
            os.symlink(REPO, dest, target_is_directory=True)
        print("已建立目录联接（改仓库即生效）")
    else:
        os.makedirs(dest, exist_ok=True)
        n = copy_tree(REPO, dest)
        print(f"已复制 {n} 个文件")

    if not a.skip_verify:
        print("\n自检:")
        py = find_python()
        r = subprocess.run([py, os.path.join(dest, "scripts", "verify_package.py"), "--run"])
        if r.returncode != 0:
            raise SystemExit(f"自检未通过（exit {r.returncode}）")

    print("\n完成。")


if __name__ == "__main__":
    main()
