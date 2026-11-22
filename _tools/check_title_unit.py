"""尺子：课文标题的英文 Unit 前缀与中文译文「第N单元」必须一致。

只查一致性，不改数据。
"""
import os
import re
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")

EN_RE = re.compile(r"^Unit\s*(\d+)\s*·")
CN_NUM = "零一二三四五六七八九十"
CN_RE = re.compile(r"^第\s*(\d+)\s*单元")
CN_ZH_RE = re.compile(r"^第\s*([%s]+)\s*单元" % CN_NUM)


def zh_to_int(s):
    if not s:
        return None
    if s == "十":
        return 10
    if s.startswith("十"):
        return 10 + CN_NUM.index(s[1:])
    if "十" in s:
        a, b = s.split("十")
        return CN_NUM.index(a) * 10 + (CN_NUM.index(b) if b else 0)
    return CN_NUM.index(s)


def main():
    files = sorted(f for f in os.listdir(ART_DIR) if f.endswith(".json"))
    bad = []
    n_en = n_cn = 0
    for fn in files:
        arr = json.load(open(os.path.join(ART_DIR, fn), encoding="utf-8"))
        for a in arr:
            t = a.get("title") or ""
            tt = a.get("titleTranslate") or ""
            me = EN_RE.match(t)
            mc = CN_RE.match(tt) or CN_ZH_RE.match(tt)
            en = int(me.group(1)) if me else None
            if en is None:
                continue
            n_en += 1
            if mc is None:
                bad.append((fn, a.get("id"), t, tt, "中文缺单元前缀"))
                continue
            n_cn += 1
            cn = int(mc.group(1)) if CN_RE.match(tt) else zh_to_int(mc.group(1))
            if cn != en:
                bad.append((fn, a.get("id"), t, tt, f"编号不一致 en={en} cn={cn}"))
    print(f"带 Unit 前缀的课文 {n_en} 篇，其中中文有单元前缀 {n_cn} 篇")
    print(f"失败项 {len(bad)}")
    for b in bad[:40]:
        print(f"  [{b[0]}#{b[1]}] {b[2]!r} | {b[3]!r}  {b[4]}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
