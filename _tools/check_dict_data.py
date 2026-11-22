"""尺子：词库数据体检。

查 5 类脏数据：
  D1 释义为空       —— trans 里一条中文都没有
  D2 释义重复       —— 同一条词的 trans 出现多段完全相同的 (词性, 中文)
  D3 重复条目丢词性 —— 同一中文出现两次，其中一条 pos 为空
  D4 释义被 null 污染 —— 释义里混进字面量 'null' 或控制字符（上游数据损坏标记）
  D5 synos 有中文但 trans 没有 —— 词形映射错位

D3 的判据踩过坑：
  「所有中文都一样」会误杀 381 条 n. 预测 / v. 预测 这种（不同词性同中文，正常）。
  真缺陷是「同中文 + 其中一条 pos 为空」—— 那条是把同一条释义重复贴了一遍、
  又丢了词性标记，界面上会显示两条一模一样的中文。

用法：python _tools/check_dict_data.py
"""
import os
import re
import sys
import json
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST = os.path.join(ROOT, "public", "list", "word.json")

CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
NULL_TOKEN_RE = re.compile(r"(^|[\s;；,，、])null($|[\s;；,，、])", re.I)


def main():
    books = json.load(open(LIST, encoding="utf-8"))
    counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    samples = {1: [], 2: [], 3: [], 4: [], 5: []}
    scanned = 0
    for b in books:
        path = os.path.join(WORD_DIR, b["url"])
        if not os.path.exists(path):
            continue
        arr = json.load(open(path, encoding="utf-8"))
        scanned += 1
        for it in arr:
            w = it.get("word") or it.get("name") or ""
            trans = it.get("trans") or []
            synos = it.get("synos") or []
            cns = []
            for t in trans:
                c = (t.get("cn") or "").strip()
                if c:
                    cns.append(c)
            if not cns:
                counts[1] += 1
                if len(samples[1]) < 12:
                    samples[1].append((b["enName"], w))
                continue

            # D2：同一条词的 trans 出现 (pos, cn) 完全相同的条目
            c2 = Counter()
            for t in trans:
                c = (t.get("cn") or "").strip()
                if c:
                    c2[((t.get("pos") or "").strip(), c)] += 1
            dup = [k for k, v in c2.items() if v >= 2]
            if dup:
                counts[2] += 1
                if len(samples[2]) < 12:
                    samples[2].append((b["enName"], w, dup[:3]))
                continue

            # D3：同一中文出现多次，且其中有 pos 为空的（重复贴条 + 丢词性）
            bycn = {}
            for t in trans:
                c = (t.get("cn") or "").strip()
                if not c:
                    continue
                bycn.setdefault(c, []).append((t.get("pos") or "").strip())
            bad3 = False
            for c, ps in bycn.items():
                if len(ps) >= 2 and any(p == "" for p in ps):
                    bad3 = True
                    break
            if bad3:
                counts[3] += 1
                if len(samples[3]) < 12:
                    samples[3].append((b["enName"], w, cns[:4]))
                continue

            # D4：释义里有控制字符或字面量 null
            bad4 = None
            for field in ("trans", "synos"):
                for t in (it.get(field) or []):
                    cn = t.get("cn") or ""
                    if CTRL_RE.search(cn):
                        bad4 = ("CTRL", repr(cn[:40]))
                        break
                    if NULL_TOKEN_RE.search(cn):
                        bad4 = ("NULL", repr(cn[:40]))
                        break
                if bad4:
                    break
            if bad4:
                counts[4] += 1
                if len(samples[4]) < 12:
                    samples[4].append((b["enName"], w, bad4))
                continue

            # D5：synos 有中文但 trans 没有
            syn_cn = [(s.get("cn") or "").strip() for s in synos if (s.get("cn") or "").strip()]
            if syn_cn and not cns:
                counts[5] += 1

    print(f"扫描词书 {scanned} 册")
    print(
        f"D1 释义为空 {counts[1]} / D2 释义重复 {counts[2]} / "
        f"D3 重复条目丢词性 {counts[3]} / D4 null或控制字符 {counts[4]} / D5 synos有trans无 {counts[5]}"
    )
    names = {
        1: "D1 释义为空",
        2: "D2 释义重复",
        3: "D3 重复条目丢词性",
        4: "D4 null或控制字符",
    }
    for k, name in names.items():
        if samples[k]:
            print(f"\n== {name} ==")
            for s in samples[k]:
                print("   ", s)
    sys.exit(1 if any(counts.values()) else 0)


if __name__ == "__main__":
    main()
