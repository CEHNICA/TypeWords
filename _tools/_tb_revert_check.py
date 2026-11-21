#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
体检器退回验证
==============
给体检器每条新检查各塞一个「坏样本」，要求它**精确红在自己那一条上**，
且不牵连别的检查。全部在纯 ASCII 临时目录里跑，不碰工作区产物。

用法：
    python _tools/_tb_revert_check.py
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(ROOT, "_tools", "check_textbook_articles.py")
SRC_ARTICLE_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")
SRC_LIST = os.path.join(ROOT, "public", "list", "article.json")

TMP = os.path.join(tempfile.gettempdir(), "ttb_revert_check")
TMP_ARTICLE = os.path.join(TMP, "article")
TMP_LIST = os.path.join(TMP, "article.json")

# 目标册 + 期望红的那条检查名（名字里含的书名要一致）
TARGET_BOOK = "LWXX_3_1"
TARGET_NAME = "小学三四"

CASES = [
    ("页脚 Unit N 残留", "单元段污染", lambda t: t + "\n\nUnit 3\n", "课文里没有页脚 Unit N 残留"),
    ("U+FFFD 豆腐块", "豆腐块", lambda t: t + "\n\nFine\ufffd\n", "课文里没有 U+FFFD 豆腐块"),
    ("艺术字双层叠印", "叠印", lambda t: t + "\n\nWWoorrddss\n", "课文里没有艺术字双层叠印"),
    ("span 粘连长串", "粘连", lambda t: t + "\n\nabcdefghijklmnopqrst\n", "课文里没有粘连长串"),
    ("弯撇号未归一", "弯撇号", lambda t: t.replace("I'm", "I\u2019m", 1), "课文撇号已归一成 ASCII"),
    ("断词 att ention", "断词", lambda t: t + "\n\nThis att ention matters.\n", "课文里没有断词"),
]


def prepare():
    if os.path.isdir(TMP):
        shutil.rmtree(TMP, ignore_errors=True)
    os.makedirs(TMP_ARTICLE, exist_ok=True)
    for fn in os.listdir(SRC_ARTICLE_DIR):
        if fn.endswith(".json"):
            shutil.copy2(os.path.join(SRC_ARTICLE_DIR, fn), os.path.join(TMP_ARTICLE, fn))
    shutil.copy2(SRC_LIST, TMP_LIST)


def run_checker():
    env = dict(os.environ)
    env["TTB_ARTICLE_DIR"] = TMP_ARTICLE
    env["TTB_LIST_FILE"] = TMP_LIST
    p = subprocess.run(
        [sys.executable, CHECKER], env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    fails = []
    for line in p.stdout.splitlines():
        if line.startswith("[FAIL] "):
            body = line[len("[FAIL] "):].strip()
            fails.append(body.split("  —— ")[0].strip())
    return fails


def sabotage(fn):
    path = os.path.join(TMP_ARTICLE, "%s.json" % TARGET_BOOK)
    with io.open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data[0]["text"] = fn(data[0]["text"])
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2))


def restore():
    path = os.path.join(TMP_ARTICLE, "%s.json" % TARGET_BOOK)
    shutil.copy2(os.path.join(SRC_ARTICLE_DIR, "%s.json" % TARGET_BOOK), path)


def main():
    prepare()
    base = run_checker()
    if base:
        print("[FAIL] 基线不干净，临时目录就有 %d 项失败：" % len(base))
        for b in base[:10]:
            print("       - " + b)
        return 1
    print("[PASS] 基线：临时目录全绿（%d 项检查）" % 0)
    print("       坏样本目录 = %s\n" % TMP)

    bad = 0
    for label, _tag, fn, expect in CASES:
        restore()
        sabotage(fn)
        fails = run_checker()
        restore()
        hit = [f for f in fails if expect in f]
        other = [f for f in fails if expect not in f]
        if len(hit) == 1 and not other:
            print("[PASS] 坏样本「%s」→ 精确红在「%s」" % (label, hit[0]))
        else:
            bad += 1
            print("[FAIL] 坏样本「%s」→ 命中 %d 条（期望 1 条：%s），额外失败 %d 条"
                  % (label, len(hit), expect, len(other)))
            for o in other[:5]:
                print("       多余失败: " + o)

    # 负对照：社交账号 handle 不能被当粘连
    restore()
    sabotage(lambda t: t + "\n\nFollow @thechinesechefblog for more.\n")
    fails = run_checker()
    restore()
    noise = [f for f in fails if "粘连" in f]
    if noise:
        bad += 1
        print("[FAIL] 负对照：@thechinesechefblog 被误判成粘连长串")
    else:
        print("[PASS] 负对照：@thechinesechefblog 不误判成粘连长串")

    print("\n退回验证：%s" % ("全绿" if bad == 0 else "%d 项不合格" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
