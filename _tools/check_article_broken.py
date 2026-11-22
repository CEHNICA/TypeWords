#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
尺子：检测课文里的「PDF 缺字形」断词
========================================
课本 PDF 的文本层在某些位置少了一个字形，那个位置被写成了空格：
    "T ey might be asked"   ->  "They might be asked"
    "Th e teacher spoke"    ->  "The teacher spoke"
    "of en talk about"      ->  "often talk about"
    "gift s are flowers"    ->  "gifts are flowers"
    "astro- nauts"          ->  "astronauts"（行尾连字符换行）

判据（相邻两个词 A B）：
  1. 合并 AB 是词典里的真词 -> 空格是多余的
  2. AB 插入一个字母后是真词，且 B 不是常用词 -> PDF 少了一个字形
  3. A 以 "-" 结尾（行尾连字符换行）

输出每条命中的「所在整句」，供 LLM 二次确认（避免误判直接改数据）。

用法：
  py -3 _tools/check_article_broken.py
  py -3 _tools/check_article_broken.py --json out.json
"""
import os, sys, json, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLE_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")
INDEX = os.path.join(ROOT, "data", "word-index.json")

BOOKS = ["LWXX_3_1", "LWXX_3_2", "LWXX_4_1", "LWXX_4_2", "LWXX_5_1", "LWXX_5_2",
         "LWCZ_6_1", "LWCZ_6_2", "LWCZ_7_1", "LWCZ_7_2", "LWCZ_8_1", "LWCZ_8_2", "LWCZ_9_1"]

# 高频词：B 命中这些就不当作「被截断的碎片」，避免把 "a lot" 合��� "allot"
COMMON = set("""
a an the and or but if then else of in on at to for with by from as is are was were be been being
it its this that these those he she they we you i him her them us me my your his their our
not no yes do does did doing have has had having will would shall should can could may might must
lot lots kind sorts way ways thing things people time times year years day days man men woman women
child children life world school class student students teacher teachers friend friends mother father
home house housework hobby job work study learn study english chinese chinese maths science
big small large little long short tall high low old young new good bad best better right wrong
here there where when what who why how all some any each every other another same different
""".split())

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]*")


def one_insert_words(s, valid):
    """s 插入一个字母后能变成哪些词典里的词"""
    out = []
    if not s or len(s) > 14:
        return out
    for i in range(len(s) + 1):
        for ch in "abcdefghijklmnopqrstuvwxyz":
            w = s[:i] + ch + s[i:]
            if w in valid:
                out.append(w)
    return out


def main():
    idx = json.load(open(INDEX, encoding="utf-8"))
    valid = set(k.lower() for k in idx.keys())
    wide = "--wide" in sys.argv
    print("模式", "wide(高召回)" if wide else "strict")

    hits = []
    for b in BOOKS:
        f = os.path.join(ARTICLE_DIR, b + ".json")
        if not os.path.exists(f):
            continue
        arr = json.load(open(f, encoding="utf-8"))
        for ai, a in enumerate(arr):
            lines = (a.get("text") or "").split("\n")
            for li, line in enumerate(lines):
                toks = TOKEN_RE.findall(line)
                reasons = []
                for i in range(len(toks) - 1):
                    A, B = toks[i], toks[i + 1]
                    if not (A.isalpha() and B.isalpha()):
                        continue
                    la, lb = A.lower(), B.lower()
                    merged = la + lb
                    if len(merged) < 4:
                        continue
                    # --wide：高召回模式，放过「第二个碎片本身是词」的情况，
                    # 剩下的交给 LLM 裁决（high-precision 模式才用严格过滤）
                    if not wide and lb in valid:
                        continue
                    # 真断词的特征：碎片很短（单词被劈成两半，总有一边很短）
                    if len(la) > 2 and len(lb) > 2:
                        continue
                    if merged in valid:
                        reasons.append((f"{A} {B}", merged))
                        continue
                    if len(lb) <= 3:
                        cand = one_insert_words(merged, valid)
                        good = [w for w in cand
                                if (A[0].isupper() == w[0].isupper()) and w not in COMMON]
                        if good and len(good) == 1:
                            reasons.append((f"{A} {B}", good[0]))
                # 行尾连字符
                m = re.search(r"(\w)-\s+(\w)", line)
                if m:
                    reasons.append((m.group(0), m.group(1) + m.group(2)))
                if reasons:
                    hits.append({"book": b, "art": ai + 1, "line": li + 1,
                                 "text": line, "reasons": reasons})

    print("课文册数", len(BOOKS), "命中行", len(hits))
    seen = set()
    for h in hits:
        key = tuple(h["reasons"])
        if key in seen:
            continue
        seen.add(key)
        print(f"  {h['book']} #{h['art']}: {h['reasons'][0][0]!r} -> {h['reasons'][0][1]!r}")
        print(f"      {h['text'][:120]}")
    print("不同模式数", len(seen))

    if "--json" in sys.argv:
        out = sys.argv[sys.argv.index("--json") + 1]
        json.dump(hits, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("已写", out)


if __name__ == "__main__":
    main()
