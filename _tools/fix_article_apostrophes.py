"""把英文课文里的各种 Unicode 撇号统一成 ASCII `'`
=======================================================

为什么：
  跟打页是**逐字符比对**的，用户键盘打出来的是 ASCII `'`。
  课本 PDF 里同一个撇号有多种 Unicode 形态（U+2019 / U+2018 / U+201B / …），
  漏掉任何一种 → 那个字**永远打不出来**。

只改 `text` / `title`（英文）；
`textTranslate` / `titleTranslate` 里的 U+2018/U+2019 是**中文单引号**，
是正确的中文标点，**不能动**。

用法：
  python _tools/fix_article_apostrophes.py            # dry-run
  python _tools/fix_article_apostrophes.py --apply    # 写盘
"""
import os
import sys
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLE_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")

BOOKS = [
    "LWXX_3_1", "LWXX_3_2", "LWXX_4_1", "LWXX_4_2", "LWXX_5_1", "LWXX_5_2",
    "LWCZ_6_1", "LWCZ_6_2", "LWCZ_7_1", "LWCZ_7_2", "LWCZ_8_1", "LWCZ_8_2", "LWCZ_9_1",
]

# 所有「长得像撇号」的 Unicode 字符 → ASCII '
APOS_MAP = {
    "\u2019": "'", "\u2018": "'", "\u201b": "'", "\u201a": "'",
    "\u2032": "'", "\u02bc": "'", "\u275b": "'", "\u02b9": "'",
    "\u0312": "'", "\u0060": "'", "\u0060": "'",
}
# 中文引号不碰（在译文里），但英文正文里出现就是错的
CJK_FIELDS = ("textTranslate", "titleTranslate")


def normalize(s):
    if not isinstance(s, str):
        return s, 0
    n = 0
    for k, v in APOS_MAP.items():
        c = s.count(k)
        if c:
            s = s.replace(k, v)
            n += c
    return s, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    total = 0
    changed_books = 0
    for book in BOOKS:
        path = os.path.join(ARTICLE_DIR, book + ".json")
        if not os.path.exists(path):
            print(f"[SKIP] {book}.json 不存在")
            continue
        raw = open(path, "rb").read()
        arr = json.loads(raw.decode("utf-8-sig"))
        n_book = 0
        touched = False
        for art in arr:
            for field in ("text", "title"):
                v = art.get(field)
                if isinstance(v, str):
                    nv, n = normalize(v)
                    if n:
                        art[field] = nv
                        n_book += n
                        touched = True
        if touched:
            changed_books += 1
            total += n_book
            print(f"  {book}: 归一 {n_book} 处")
            if args.apply:
                text = json.dumps(arr, ensure_ascii=False, indent=2) + "\n"
                with open(path, "wb") as fh:
                    fh.write(text.encode("utf-8"))
    print(f"{'已写盘' if args.apply else 'DRY-RUN'}：改动 {changed_books} 册，共归一 {total} 处")


if __name__ == "__main__":
    main()
