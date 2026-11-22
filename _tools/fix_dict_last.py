"""修最后 5 条缺释义的词条。

1. laurel（level8 / TOEFL_ZhangHongYan / gmat / IELTSXDF7000 各 1 条）
   trans 空，但 synos 里有中文 '桂冠，殊荣；月桂树' → 搬进 trans（不是新编，是搬）。

2. problemn（beijing_junior_high_school 一条）
   双重损坏：
     - 词头 'problemn' 多了个 n（词序上它正好该在 positive 和 possible 之间 → 本该是 problem）
     - 整条内容却是 snowy 的（synos「下雪的」、relWords.root=snow、etymology=snowy）
   同册 1438 已有完整的 'snowy' → 这里只把词头改回 'problem'，
   释义从离线大词典取，snowy 那套错内容一并清掉。

默认 dry-run，--apply 写盘。
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from json_io import dump_like, load_preserve  # noqa: E402

WORD_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST = os.path.join(ROOT, "public", "list", "word.json")
INDEX = os.path.join(ROOT, "data", "word-index.json")


def first_cn(idx, word):
    v = idx.get(word)
    if not isinstance(v, dict):
        return None
    for t in (v.get("trans") or []):
        c = (t.get("cn") or "").strip()
        if c:
            p = (t.get("pos") or "").strip()
            return {"pos": p, "cn": c}
    return None


def main():
    apply = "--apply" in sys.argv
    idx = json.load(open(INDEX, encoding="utf-8"))
    lst = json.load(open(LIST, encoding="utf-8"))
    changes = []
    for d in lst:
        f = os.path.join(WORD_DIR, d["url"])
        if not os.path.exists(f):
            continue
        arr, raw = load_preserve(f)
        dirty = False
        for i, w in enumerate(arr):
            word = (w.get("word") or "").strip()
            trans = w.get("trans") or []
            if any((t.get("cn") or "").strip() for t in trans):
                continue
            # 2) 词头疑似错拼 → 先处理（它的 synos 里是别人的释义，不能搬）
            if word == "problemn":
                fix = first_cn(idx, "problem")
                changes.append((d["enName"], i, word, "改词头为 problem", fix))
                if apply:
                    w["word"] = "problem"
                    w["trans"] = [fix] if fix else [{"pos": "n.", "cn": "问题；难题"}]
                    # snowy 那套错内容清掉（同册 1438 有完整的 snowy）
                    w["synos"] = []
                    w["relWords"] = {"root": "", "rels": []}
                    w["etymology"] = []
                    dirty = True
                continue
            # 1) synos 里就有中文 → 搬进 trans
            syn = w.get("synos") or []
            cn = None
            for s in syn:
                c = (s.get("cn") or "").strip()
                if c:
                    cn = {"pos": (s.get("pos") or "").strip(), "cn": c}
                    break
            if cn:
                changes.append((d["enName"], i, word, "synos→trans", cn))
                if apply:
                    w["trans"] = [cn]
                    dirty = True
                continue
            # 2) 词头疑似错拼 → 查离线词典里同拼写变体
            if word == "problemn":
                fix = first_cn(idx, "problem")
                changes.append((d["enName"], i, word, "改词头为 problem", fix))
                if apply:
                    w["word"] = "problem"
                    w["trans"] = [fix] if fix else [{"pos": "n.", "cn": "问题；难题"}]
                    # snowy 那套错内容清掉（同册 1438 有完整的 snowy）
                    w["synos"] = []
                    w["relWords"] = {"root": "", "rels": []}
                    w["etymology"] = []
                    dirty = True
        if apply and dirty:
            with open(f, "wb") as fh:
                fh.write(dump_like(raw, arr))
    for c in changes:
        print("  ", c)
    print(f"共 {len(changes)} 处（apply={apply}）")


if __name__ == "__main__":
    main()
