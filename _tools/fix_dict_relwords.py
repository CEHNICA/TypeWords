"""清理词库里「内容与词头彻底无关」的 relWords（上游词库的整组错位）。

判据：relWords 的整个词族（root + rels[].words[].c）里，
      没有任何一个词与词头有 ≥2 个字符的公共前缀 → 判为错配。

为什么用这么严的判据（试过更宽的，都假阳性）：
  - 相似度占比 < 0.75：误杀 explosive←explode、drunk←drink、audience←auditory
  - 词头不在族里：误杀 glorious←glory（族里只有 glory/glorified）
  英文派生关系不是前缀关系，字符串判据只认「彻底无关」这一档。
  这档抽样人工核验 20 条，全部是真错配（textile←waste、harness←headmaster…）。

清空成 {root:'', rels:[]}：前端 WordMetaPanel / dict.vue 都有 root 守卫，
不显示比显示错的好；word-test.ts 的同根词相似度也不再被污染。

默认 dry-run，--apply 写盘。
"""
import os
import sys
import json
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from json_io import dump_like, load_preserve  # noqa: E402

WORD_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST = os.path.join(ROOT, "public", "list", "word.json")


def lcp(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


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


def is_mismatch(w):
    word = (w.get("word") or "").strip().lower()
    fam = family(w.get("relWords") or {})
    if not word or not fam:
        return False
    return max(lcp(word, x) for x in fam) < 2


def main():
    apply = "--apply" in sys.argv
    lst = json.load(open(LIST, encoding="utf-8"))
    total = 0
    touched = 0
    books = Counter()
    samples = []
    for d in lst:
        f = os.path.join(WORD_DIR, d["url"])
        if not os.path.exists(f):
            continue
        arr, raw = load_preserve(f)
        dirty = False
        for w in arr:
            if not is_mismatch(w):
                continue
            total += 1
            books[d["enName"]] += 1
            if len(samples) < 10:
                samples.append((d["enName"], w.get("word"),
                                (w.get("relWords") or {}).get("root")))
            if apply:
                w["relWords"] = {"root": "", "rels": []}
                dirty = True
        if apply and dirty:
            with open(f, "wb") as fh:
                fh.write(dump_like(raw, arr))
            touched += 1
    print(f"清空错位 relWords {total} 条，涉及词书 {touched} 册（apply={apply}）")
    for k, v in books.most_common(8):
        print(f"  {k:<26} {v}")
    print("样例:")
    for s in samples:
        print("  ", s)


if __name__ == "__main__":
    main()
