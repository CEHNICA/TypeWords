#!/usr/bin/env python3
"""定点修复课文里的结构性损坏（每一条都有课本 PDF 版面证据）。

三类损坏：
  A 跨页断头  —— 段落前半句被页脚吞掉，后半句落到下一页成了独立段落
  B 表格拉平  —— 练习表格/清单被压成一行乱码，混进课文
  C 双栏乱序  —— 双栏版面左右栏内容交错

用法：
  py -3 scripts/fix_structural_damage.py            # 预演（不改文件）
  py -3 scripts/fix_structural_damage.py --apply    # 写盘
"""
import os
import re
import json
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")

# ---------------------------------------------------------------------------
# 修复清单。para 为段落下标（按 `\n\n` 切）。
# ---------------------------------------------------------------------------
FIXES = [
    # ---- A 类：跨页断头，把上一页末尾的前半句补回来 ----------------------
    {
        "book": "LWCZ_7_2", "idx": 8, "kind": "prepend",
        "para": 2,
        "prefix": "TCM is also helpful when we are sick. It helps stop the sickness "
                  "from getting worse. And it prevents our body from losing too much "
                  "energy. After we get",
        "expect": "well, if we follow TCM advice",
        "pdf": "七下 p55 末段 → p56 首行",
    },
    {
        "book": "LWCZ_9_1", "idx": 1, "kind": "prepend",
        "para": 4,
        "prefix": "Later on, the papermaking technique not only speeded up the development",
        "expect": "of Chinese culture, but also changed civilizations around the world.",
        "pdf": "九上 p16 末行 → p17 首行",
    },
    {
        "book": "LWCZ_9_1", "idx": 5, "kind": "prepend",
        "para": 3,
        "prefix": "The fourth one was given on 12 October 2022. The Shenzhou 14 crew "
                  "introduced the experiment cabinets at the Wentian lab and presented "
                  "several water-related phenomena inside the space station. They even "
                  "invited students",
        "expect": "to do similar experiments along with them",
        "pdf": "九上 p33 末段 → p34 首行",
    },
    {
        "book": "LWCZ_9_1", "idx": 11, "kind": "prepend",
        "para": 1,
        "prefix": "Since the establishment of the People's Republic of China, Chinese government",
        "expect": "has consistently paid attention to physical education and national health.",
        "pdf": "九上 p57 末行 → p58 首行",
    },
    {
        "book": "LWCZ_9_1", "idx": 17, "kind": "prepend",
        "para": 2,
        "prefix": "In the Warring States Period, the area of Shandong was mainly made up of",
        "expect": "the Qi State and the Lu State.",
        "pdf": "九上 p81 末行 → p82 首行",
    },
    {
        "book": "LWCZ_9_1", "idx": 38, "kind": "prepend",
        "para": 1,
        "prefix": "Things changed for Rodin in 1875 when he had a chance to visit Italy. "
                  "He found new inspiration when he saw the works of Michelangelo. His breakthrough",
        "expect": "work—The Age of Bronze—was completed that same year.",
        "pdf": "九上 p152 末段 → p153 首行",
    },

    # ---- B 类：表格/清单被拉平，剔除 --------------------------------------
    {
        "book": "LWCZ_8_1", "idx": 26, "kind": "drop",
        "para": 6,
        "expect": "difficult to balance shoes for bread",
        "pdf": "八上 p104 4 列对比表被拉平",
    },
    {
        "book": "LWCZ_8_2", "idx": 3, "kind": "drop",
        "para": 3,
        "expect": "yes no how often yes no how often",
        "pdf": "八下 p38 Grammar Focus 4c 清单被拉平",
    },
    {
        "book": "LWCZ_9_1", "idx": 4, "kind": "drop",
        "para": 11,
        "expect": "build a research station on the moon send a spacecraft",
        "pdf": "九上 p31 3b 讨论清单被拉平",
    },
    {
        "book": "LWCZ_9_1", "idx": 30, "kind": "drop",
        "para": 9,
        "expect": "a header showing what the page is about",
        "pdf": "九上 p140 Project 清单被拉平",
    },
    {
        "book": "LWCZ_8_2", "idx": 8, "kind": "replace",
        "para": 1,
        "expect": "listened to pop music enjoys country music",
        "new": "e.g. Emily didn‛t use to eat a lot of vegetables, but now she loves "
               "carrots and tomatoes.",
        "pdf": "八下 p62 Grammar Focus 4b 表格被拉平，只留 e.g. 例句",
    },

    # ---- C 类：双栏乱序，拆回两栏 ----------------------------------------
    {
        "book": "LWCZ_8_2", "idx": 6, "kind": "set",
        "expect": "Finally, explain why you like it",
        "new_paras": {
            5: "First, introduce the festival and when it is celebrated.\n"
               "Then talk about what people do and eat.\n"
               "Finally, explain why you like it best and how it makes you feel.",
            6: "My favorite Chinese festival is ...\n"
               "It is celebrated in/on ...\n"
               "During this festival, people ...\n"
               "It‛s my favorite festival because ...\n"
               "It makes me feel ...",
        },
        "pdf": "八下 p50 左右两栏内容交错",
    },

    # ---- 残余断词（PDF 文本层少一个字形） --------------------------------
    {"book": "LWCZ_8_2", "idx": 2, "kind": "replace_text",
     "old": "T erefore, we should usually discuss", "new": "Therefore, we should usually discuss"},
    {"book": "LWCZ_8_2", "idx": 3, "kind": "replace_text",
     "old": "Th e teacher spoke so quickly", "new": "The teacher spoke so quickly"},
    {"book": "LWCZ_8_2", "idx": 6, "kind": "replace_text",
     "old": "reaches the bot om, everyone", "new": "reaches the bottom, everyone"},
    {"book": "LWCZ_8_2", "idx": 6, "kind": "replace_text",
     "old": "T e Chinese New Year, or the Spring Festival", "new": "The Chinese New Year, or the Spring Festival"},
    {"book": "LWCZ_8_2", "idx": 6, "kind": "replace_text",
     "old": "T is reunion shows that family", "new": "This reunion shows that family"},
    {"book": "LWCZ_8_2", "idx": 6, "kind": "replace_text",
     "old": "T e name of the festival means", "new": "The name of the festival means"},
    {"book": "LWCZ_8_2", "idx": 6, "kind": "replace_text",
     "old": "T ey also go out and enjoy picnics", "new": "They also go out and enjoy picnics"},
    {"book": "LWCZ_8_2", "idx": 8, "kind": "replace_text",
     "old": "different af er she became famous", "new": "different after she became famous"},
    {"book": "LWCZ_8_2", "idx": 8, "kind": "replace_text",
     "old": "However, too much at ention can also be a bad thing.",
     "new": "However, too much attention can also be a bad thing."},
    {"book": "LWCZ_8_2", "idx": 7, "kind": "replace_text",
     "old": "I‛m looking forward to your reply.",
     "new": "I’m looking forward to your reply."},
]

# ---- 拆分：九上 #1 把「造纸」和「飞机」两篇课文混成了一篇 ------------------
SPLITS = [
    {
        "book": "LWCZ_9_1", "idx": 1,
        "keep_paras": [0, 1, 2, 3, 4],
        "keep_title": "An Invention That Changed the World",
        "new_title": "The Invention of the Plane",
        "new_paras": [5, 6, 7],
        "pdf": "九上 p16-17 造纸（1b）+ p19 飞机（3a）被并成一篇",
    },
]


def paras(a):
    return (a.get("text") or "").split("\n\n")


def set_paras(a, plist):
    a["text"] = "\n\n".join(plist)


def main():
    apply = "--apply" in sys.argv
    books = {}
    order = []

    def load(book):
        if book not in books:
            p = os.path.join(ART_DIR, book + ".json")
            books[book] = json.load(open(p, encoding="utf-8"))
            order.append(book)
        return books[book]

    log = []
    ok = 0
    fail = 0
    skipped = 0

    # ---- 定点修复（先做：拆分会让后续段落下标整体后移） --------------------
    for fx in FIXES:
        arr = load(fx["book"])
        a = arr[fx["idx"]]
        pl = paras(a)
        kind = fx["kind"]

        if kind == "replace_text":
            if fx["old"] in a.get("text", ""):
                a["text"] = a["text"].replace(fx["old"], fx["new"])
                ok += 1
                log.append(f"[断词] {fx['book']} #{fx['idx']} {fx['old']!r} → {fx['new']!r}")
            else:
                skipped += 1
                log.append(f"[跳过-断词] {fx['book']} #{fx['idx']} 未命中 {fx['old']!r}")
            continue

        if kind == "prepend":
            i = fx["para"]
            if i >= len(pl):
                fail += 1
                log.append(f"[失败] {fx['book']} #{fx['idx']} 段 {i} 不存在")
                continue
            if pl[i].startswith(fx["prefix"][:40]):
                skipped += 1
                log.append(f"[跳过-已修] {fx['book']} #{fx['idx']} 段 {i}")
                continue
            if fx["expect"] not in pl[i]:
                fail += 1
                log.append(f"[失败] {fx['book']} #{fx['idx']} 段 {i} 未命中锚点 {fx['expect']!r}")
                continue
            lines = pl[i].split("\n")
            lines[0] = fx["prefix"] + " " + lines[0]
            pl[i] = "\n".join(lines)
            set_paras(a, pl)
            a["textTranslate"] = ""
            ok += 1
            log.append(f"[A断头] {fx['book']} #{fx['idx']} 段 {i} 补回前半句（{fx['pdf']}）")
            continue

        if kind == "drop":
            i = fx["para"]
            if i >= len(pl):
                fail += 1
                log.append(f"[失败] {fx['book']} #{fx['idx']} 段 {i} 不存在")
                continue
            if fx["expect"] not in pl[i]:
                fail += 1
                log.append(f"[失败] {fx['book']} #{fx['idx']} 段 {i} 未命中锚点 {fx['expect']!r}")
                continue
            del pl[i]
            set_paras(a, pl)
            a["textTranslate"] = ""
            ok += 1
            log.append(f"[B拉平] {fx['book']} #{fx['idx']} 删段 {i}（{fx['pdf']}）")
            continue

        if kind == "replace":
            i = fx["para"]
            if i >= len(pl):
                fail += 1
                log.append(f"[失败] {fx['book']} #{fx['idx']} 段 {i} 不存在")
                continue
            if fx["expect"] not in pl[i]:
                fail += 1
                log.append(f"[失败] {fx['book']} #{fx['idx']} 段 {i} 未命中锚点 {fx['expect']!r}")
                continue
            pl[i] = fx["new"]
            set_paras(a, pl)
            a["textTranslate"] = ""
            ok += 1
            log.append(f"[B拉平] {fx['book']} #{fx['idx']} 段 {i} 重写（{fx['pdf']}）")
            continue

        if kind == "set":
            blob = "\n\n".join(pl)
            if fx["expect"] not in blob:
                fail += 1
                log.append(f"[失败] {fx['book']} #{fx['idx']} 未命中锚点 {fx['expect']!r}")
                continue
            for pi, txt in fx["new_paras"].items():
                if pi >= len(pl):
                    fail += 1
                    log.append(f"[失败] {fx['book']} #{fx['idx']} 段 {pi} 不存在")
                    continue
                pl[pi] = txt
            set_paras(a, pl)
            a["textTranslate"] = ""
            ok += 1
            log.append(f"[C双栏] {fx['book']} #{fx['idx']} 拆回两栏（{fx['pdf']}）")
            continue

    # ---- 拆分（最后做：插入新篇会让后面所有段落下标 +1） ------------------
    for sp in SPLITS:
        arr = load(sp["book"])
        a = arr[sp["idx"]]
        pl = paras(a)
        if len(pl) <= max(sp["keep_paras"] + sp["new_paras"]):
            log.append(f"[跳过-拆分] {sp['book']} #{sp['idx']} 段数不够")
            skipped += 1
            continue
        max_id = max((int(x.get("id") or 0) for x in arr), default=0)
        new_art = {
            "id": max_id + 1,
            "title": sp["new_title"],
            "titleTranslate": "",
            "text": "\n\n".join(pl[i] for i in sp["new_paras"]),
            "textTranslate": "",
            "audioSrc": None,
            "lrcPosition": [],
            "question": None,
            "nameList": None,
            "quote": None,
            "userId": None,
        }
        # 原篇只留 keep_paras，标题换成真正的课文标题
        base_title = a.get("title", "")
        m = re.match(r"^(Unit\s*\d+\s*·\s*)?(.*)$", base_title)
        prefix = m.group(1) or ""
        a["title"] = prefix + sp["keep_title"]
        set_paras(a, [pl[i] for i in sp["keep_paras"]])
        a["textTranslate"] = ""
        a["titleTranslate"] = ""
        arr.insert(sp["idx"] + 1, new_art)
        log.append(f"[拆分] {sp['book']} #{sp['idx']} → 「{sp['keep_title']}」+ 新篇「{sp['new_title']}」（{sp['pdf']}）")
        ok += 1

    if apply:
        for book in order:
            p = os.path.join(ART_DIR, book + ".json")
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(books[book], ensure_ascii=False, indent=2) + "\n")
            log.append(f"[写盘] {book}.json")

    out = os.path.join(ROOT, "_tools", "_struct_fix.log")
    open(out, "w", encoding="utf-8").write("\n".join(log))
    print("\n".join(log))
    print(f"\n成功 {ok}  跳过 {skipped}  失败 {fail}   (apply={apply})")
    print("wrote", out)


if __name__ == "__main__":
    main()
