"""修中文译文里没翻译的 'Unit N ·' 前缀。

两个真缺陷：
1. 中文译文直接留英文 'Unit 2 · …'（LLM 翻译时把单位名原样留着了）
2. 更糟：英文标题已改成 Unit 9，中文还写着旧的 'Unit 3 · …' → 中英对不上

判据只看英文标题的 Unit 号，中文前缀一律按英文的号改写。
默认 dry-run，--apply 写盘。
"""
import os
import re
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")

EN_RE = re.compile(r"^Unit\s*(\d+)\s*·")
CN_NUM = "零一二三四五六七八九十"
CN_AR = re.compile(r"^第\s*(\d+)\s*单元")
CN_ZH = re.compile(r"^第\s*([%s]+)\s*单元" % CN_NUM)
EN_STYLE = re.compile(r"^Unit\s*(\d+)\s*·\s*", re.I)


def cn_num(n):
    if n <= 10:
        return CN_NUM[n] if n < 10 else "十"
    if n < 20:
        return "十" + CN_NUM[n - 10]
    return str(n)


def main():
    apply = "--apply" in sys.argv
    fixed = 0
    total = 0
    for fn in sorted(f for f in os.listdir(ART_DIR) if f.endswith(".json")):
        path = os.path.join(ART_DIR, fn)
        arr = json.load(open(path, encoding="utf-8"))
        dirty = False
        for a in arr:
            t = a.get("title") or ""
            tt = a.get("titleTranslate") or ""
            m = EN_RE.match(t)
            if not m:
                continue
            total += 1
            n = int(m.group(1))
            mm = CN_AR.match(tt)
            if mm:
                new = CN_AR.sub(f"第{n}单元", tt, count=1)
            else:
                mm = CN_ZH.match(tt)
                if mm:
                    new = CN_ZH.sub(f"第{cn_num(n)}单元", tt, count=1)
                else:
                    mm = EN_STYLE.match(tt)
                    if mm:
                        new = EN_STYLE.sub(f"第{cn_num(n)}单元 · ", tt, count=1)
                    else:
                        print(f"  [{fn}#{a.get('id')}] 中文既无数字前缀也无英文前缀，不动: {tt!r}")
                        continue
            if new != tt:
                fixed += 1
                dirty = True
                print(f"  [{fn}#{a.get('id')}] {tt!r} -> {new!r}")
                if apply:
                    a["titleTranslate"] = new
        if apply and dirty:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(arr, ensure_ascii=False, indent=2) + "\n")
    print(f"带 Unit 前缀 {total} 篇，需改 {fixed} 处（apply={apply}）")
    sys.exit(0)


if __name__ == "__main__":
    main()
