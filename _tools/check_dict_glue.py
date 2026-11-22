#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
尺子：检测词库里的「粘连单词」
==================================
课本 PDF 提取时单词内部的空格丢失，会出现 talkto / takenotes / catchfire 这类
本该是两个词（或带空格短语）的条目。这些条目在词库里永远查不到释义。

判据（全部满足才报）：
  1. 整个词条在离线词典索引 data/word-index.json 里查不到（否则是真词）
  2. 在某个切点能拆成两段，且两段都在离线词典索引里（都是真词）
  3. 词条本身【完全没有释义】（trans 和 synos 都空）—— 粘住的必然症状
  4. 拆出来的两段长度都 >= 4，且都不是缩写

第 3、4 条是后来补的。原来只查了 synos 为空，导致 greece / france / bathtub
这类正常词被判成「可拆成 gree+ce / fr+ance / bath+tub」—— 因为离线词典里收录了
ce / ai / fr / er / un 这些两三字母的缩写，片段太短就到处能对上，全是假阳性。

用法：
  py -3 _tools/check_dict_glue.py
  py -3 _tools/check_dict_glue.py --fix     # 真写盘（拆开 + 重新分配释义）
"""
import os, sys, json, re, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST = os.path.join(ROOT, "public", "list", "word.json")
INDEX = os.path.join(ROOT, "data", "word-index.json")

# 只在这些册子里查（可传 --scope all 查全库）
TARGET_HINT = "六~九年级"


TEXTBOOK_SRC = re.compile(r"^(LWXX|LWCZ)[-_]")

# 常见英文缩写/片段，拆词判据里必须排除（否则 greece 能拆成 gree+ce）
ABBR = set("""
ce ai fr er un in on at to of or an a is it be as by do we he me my no so up us am
mr mrs ms dr prof st jr sr no fig inc ltd co dept est etc eg ie vs
jan feb mar apr jun jul aug sep sept oct nov dec mon tue tues wed thu thur thurs fri sat sun
id ok usa uk eu unesco
""".split())


def is_abbr(seg):
    return seg in ABBR or len(seg) < 4


def load_index():
    """返回 (可信英文词集, 完整索引)

    可信词集 = 词典里所有词 减去 目标课本词书自己收录的词。
    课本来源的词本身可能粘连，不能拿来当「真词」判据，否则循环论证
    （talkto / takenotes 这些粘连词已经进了索引，会自证清白）。
    """
    idx = json.load(open(INDEX, encoding="utf-8"))
    return set(k.lower() for k in idx.keys()), idx


def target_words(targets):
    """目标课本词书收录的全部词（这些词不算可信判据）"""
    out = set()
    for d in targets:
        f = os.path.join(WORD_DIR, d.get("url", ""))
        if not os.path.exists(f):
            continue
        try:
            arr = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for w in arr:
            out.add((w.get("word") or "").strip().lower())
    return out


def split_candidates(word, valid):
    """返回 [(切分后的词组, 前半, 后半), ...]"""
    s = word.lower()
    if " " in s or not s.isalpha():
        return []
    out = []
    for i in range(2, len(s) - 1):
        a, b = s[:i], s[i:]
        if a in valid and b in valid:
            if is_abbr(a) or is_abbr(b):
                continue
            out.append((f"{a} {b}", a, b))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--scope", default="target", choices=["target", "all"])
    args = ap.parse_args()

    valid, idx = load_index()
    lst = json.load(open(LIST, encoding="utf-8"))
    if args.scope == "target":
        targets = [d for d in lst if any("六" in t and "九" in t for t in (d.get("tags") or []))]
    else:
        targets = lst
    # 可信词集 = 词典词 - 目标课本自己收录的词
    own = target_words(targets)
    trusted = {w for w in valid if w not in own}

    hits = []
    for d in targets:
        f = os.path.join(WORD_DIR, d.get("url", ""))
        if not os.path.exists(f):
            continue
        arr = json.load(open(f, encoding="utf-8"))
        for i, w in enumerate(arr):
            word = (w.get("word") or "").strip()
            if not word:
                continue
            lw = word.lower()
            # 词条必须完全没有释义：粘住的必然症状（查不到释义）
            has_tr = any((t.get("cn") or "").strip() for t in (w.get("trans") or []))
            if has_tr or (w.get("synos") or []):
                continue
            cands = split_candidates(word, trusted)
            if not cands:
                continue
            hits.append({"dict": d.get("name"), "file": f, "idx": i,
                         "word": word, "cands": cands})

    # 一个词可能有多个切法，取「前半最长」的那个（更可能是对的）
    for h in hits:
        h["fix"] = max(h["cands"], key=lambda c: len(c[1]))[0]

    print(f"离线词典词数 {len(valid)}")
    print(f"扫描册数 {len(targets)}")
    print(f"疑似粘连词条 {len(hits)}")
    for h in hits[:80]:
        print(f"  {h['dict']} | {h['word']}  ->  {h['fix']}")
    if len(hits) > 80:
        print(f"  ... 另有 {len(hits)-80} 条")

    if args.fix and hits:
        changed = 0
        byfile = {}
        for h in hits:
            byfile.setdefault(h["file"], []).append(h)
        for f, items in byfile.items():
            arr = json.load(open(f, encoding="utf-8"))
            for h in items:
                e = arr[h["idx"]]
                e["word"] = h["fix"]
                # 释义：优先用前半词的释义（更可能是主词）
                a = h["fix"].split(" ")[0]
                ents = idx.get(a) or idx.get(a.lower())
                if ents:
                    e["synos"] = [{"cn": (x.get("cn") or "")} for x in
                                  (ents[0].get("synos") or ents[0].get("trans") or [])[:1]]
            json.dump(arr, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            open(f, "a", encoding="utf-8").write("\n")
            changed += 1
        print(f"已写盘 {changed} 个词书")
    elif hits:
        print("（加 --fix 真写盘）")


if __name__ == "__main__":
    main()

