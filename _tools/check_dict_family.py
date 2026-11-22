"""尺子：词条内容与词头对不上（relWords 归属错误）。

判据（v1，最终版）：
  relWords 的整个词族（root + rels[].words[].c）里，
  没有任何一个词与词头有 ≥2 个字符的公共前缀 → 判为错配。

试过更宽的判据，全是假阳性，别再用：
  - 相似度占比 < 0.75：误杀 explosive←explode、drunk←drink、audience←auditory
    （英语派生不都是前缀关系，drink→drunk 是元音变化）
  - 词头不在族里：误杀 glorious←glory（族里只有 glory/glorified/gloriously）
  - 词源 etymology：源数据里混着别的词的词条说明，完全没法用
这一档（彻底无关）抽样人工核验 20 条，全部是真错配。

修复器：`_tools/fix_dict_relwords.py`（清空成 {root:'', rels:[]}）
"""
import os
import json
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST = os.path.join(ROOT, "public", "list", "word.json")


def lcp(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def similarity(word, root):
    """最长公共前缀占较短词的比例（仅供说明用，判据不用它）。"""
    if not word or not root:
        return 1.0
    return lcp(word.lower(), root.lower()) / min(len(word), len(root))


def family(rw):
    s = set()
    r = (rw.get("root") or "").strip().lower()
    if r:
        s.add(r)
    for rel in (rw.get("rels") or []):
        for x in (rel.get("words") or []):
            c = (x.get("c") or "").strip().lower()
            if c:
                s.add(c)
    return s


def bad_relwords(w):
    """返回 True = relWords 与词头彻底无关。"""
    word = (w.get("word") or "").strip().lower()
    fam = family(w.get("relWords") or {})
    if not word or not fam:
        return False
    return max(lcp(word, x) for x in fam) < 2


def main():
    lst = json.load(open(LIST, encoding="utf-8"))
    bad = []
    total = 0
    with_rw = 0
    for d in lst:
        f = os.path.join(WORD_DIR, d["url"])
        if not os.path.exists(f):
            continue
        arr = json.load(open(f, encoding="utf-8"))
        for i, w in enumerate(arr):
            total += 1
            rw = w.get("relWords") or {}
            if not (rw.get("root") or "").strip():
                continue
            with_rw += 1
            if bad_relwords(w):
                bad.append((d["enName"], i, w.get("word"), (rw.get("root") or "").strip()))
    print(f"扫描 {total} 词条，其中有 relWords.root 的 {with_rw} 条")
    print(f"relWords 归属错误 {len(bad)} 条（占 {len(bad)*100//max(1,with_rw)}%）")
    by_book = Counter(b[0] for b in bad)
    for k, v in by_book.most_common(12):
        print(f"  {k:<26} {v}")
    print("\n样例:")
    for b in bad[:15]:
        print("  ", b)


if __name__ == "__main__":
    main()
