#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TypeWords「莱芜课本课文」体检器
================================
维度：课本课文有没有真被提取出来、质量够不够跟打、书单里能不能看到。

产物（由 scripts/extract-textbook-articles.py 生成）：
  public/dicts/en/article/LWCZ_*.json / LWXX_*.json   每篇课文一个对象
  public/list/article.json                             书单条目

用法：
    python _tools/check_textbook_articles.py            # 静态体检
    python _tools/check_textbook_articles.py --http     # 再打本地 dev server

退出码 0 = 全绿；1 = 有缺陷（每条缺陷精确红在自己那条上）。
"""
import io
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("TW_BASE_URL", "http://localhost:5567")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

ARTICLE_DIR = os.environ.get("TTB_ARTICLE_DIR") or os.path.join(ROOT, "public", "dicts", "en", "article")
LIST_FILE = os.environ.get("TTB_LIST_FILE") or os.path.join(ROOT, "public", "list", "article.json")
EXTRACT_SCRIPT = os.path.join(ROOT, "scripts", "extract-textbook-articles.py")
WORD_INDEX = os.path.join(ROOT, "data", "word-index.json")

# 断词修复器（和提取器共用同一套判据，避免尺子与修法各说各话）
import textbook_text_repair as TTR  # noqa: E402

# 13 册课本 → 期望的产物文件名
#   min_articles：最少几篇（人教版八下整册课文本来就少，14 篇是正常值）
EXPECTED_BOOKS = [
    ("LWXX_3_1", "小学三四", 24),
    ("LWXX_3_2", "小学三四", 20),
    ("LWXX_4_1", "小学四上", 24),
    ("LWXX_4_2", "小学四下", 20),
    ("LWXX_5_1", "小学五上", 24),
    ("LWXX_5_2", "小学五下", 20),
    ("LWCZ_6_1", "初中六上", 16),
    ("LWCZ_6_2", "初中六下", 18),
    ("LWCZ_7_1", "初中七上", 20),
    ("LWCZ_7_2", "初中七下", 20),
    ("LWCZ_8_1", "初中八上", 22),
    # 八下是**山东版**（五·四学制，山东教育出版社），整册课文本来就少；
    # 早先的 12 篇里有一篇是 Grammar 附录页，已剔除 → 11 篇是真实值
    ("LWCZ_8_2", "初中八下", 10),
    ("LWCZ_9_1", "初中九上", 38),
]

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 词典
def load_words():
    words = set()
    if os.path.exists(WORD_INDEX):
        with io.open(WORD_INDEX, "r", encoding="utf-8") as f:
            words = set(w.lower() for w in json.load(f).keys())
    # 词典里没有的高频词 / 缩写
    words |= set("""a i an as at be by do go he if in is it me my no of on or so to up us we
the and are but for from had has her his how its not now off one our out own per put ran
she too two use was way who why yes yet you your all any few may nor say
mr mrs ms dr st jr sr prof etc eg ie no vol fig vs inc ltd co am pm approx dept est
let lets thats theres whats whos wheres hows doers cannot cant dont doesnt didnt isnt
arent wasnt werent wont wouldnt couldnt shouldnt mustnt
jan feb mar apr jun jul aug sep sept oct nov dec
chinese china chinese english britain britain american america london new york
""".split())
    return words


WORDS = load_words()

CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
# 单词被 PDF 连字 glyph 拆开："T e"（the）/"of en"（often）/"bett er"（better）
BROKEN_TOKEN_RE = re.compile(r"\b([A-Za-z]{1,4}) ([A-Za-z]{1,4})\b")
# 目录/栏目条目残留
TOC_RE = re.compile(
    r"(Speaking:\s|Talking about:|Writing:\s|Grammar:\s|Grammar Focus|"
    r"Pronunciation:\s|Useful Language|Function and Structure|"
    r"Section\s+[A-D]\b|Reading and Writing|SELF CHECK|Self check|"
    r"Reading Skills|Writing\s*$|Listening\s*$)",
)
# 附录 / 词汇表 / 听力原文 的标题（不是课文）
APPENDIX_TITLE_RE = re.compile(
    r"^(notes on the text|tapescripts?|listening scripts?|"
    r"words and expressions in each unit|vocabulary in each unit|"
    r"word list|irregular verbs|useful expressions|appendix)\b", re.I)
# 练习对话标签
SPEAKER_RE = re.compile(r"(?:^|\s)[A-D]\s*:\s")
# 小学册标题只有 "Lesson 3" 没有课名
EMPTY_LESSON_RE = re.compile(r"^Lesson\s*\d+\s*$", re.I)
# 目录里的碎片式标题（"Lesson 2 of fun" 这类被切碎的）
TRUNC_TITLE_RE = re.compile(r"^(Lesson\s*\d+\s+)?[a-z]{1,3}\b.*\b(of|for|the|in|on|at|to)\b", re.I)

# ---- 新增四类检查（2026-11-21）----
# ① 页脚 "Unit 3" 混进课文：必须是**独立成段**才算污染
#   （课文里正常出现 "Unit 1" 这种词不算）
UNIT_SEG_RE = re.compile(r"(?m)^\s*Unit\s*\d+\s*$", re.I)
# ② 缺 ToUnicode 的字体 → 撇号变成 U+FFFD
REPLACEMENT_CHAR = "\ufffd"
# ③ 艺术字双层叠印："WWoorrddss" —— 相邻字母重复，且**去重后是真实单词**
REPEAT_LETTER_RE = re.compile(r"([A-Za-z])\1")
# ④ span 粘连没补空格 → 出现超长连续字母（英语单词最长也就 15 字母）
#    注意排除社交账号 handle（"@thechinesechefblog" 是课文里真实出现的博主名）
LONG_TOKEN_RE = re.compile(r"(?<![@#_A-Za-z0-9])[A-Za-z]{17,}")
# ⑤ 撇号必须是 ASCII（跟打页逐字符比对，U+2019 会永远打不出来）
CURLY_APOS = "\u2019"


def check_products():
    """产物文件在不在、每册出没出够课文"""
    for key, name, min_arts in EXPECTED_BOOKS:
        path = os.path.join(ARTICLE_DIR, "%s.json" % key)
        if not os.path.exists(path):
            check("课文产物 %s.json 存在" % key, False, "文件不存在：" + path)
            continue
        try:
            data = json.loads(read(path))
        except Exception as e:
            check("课文产物 %s.json 是合法 JSON" % key, False, str(e))
            continue
        check("课文产物 %s.json 是合法 JSON" % key, True)
        check(
            "「%s」提取出足够课文（>=%d 篇）" % (name, min_arts),
            isinstance(data, list) and len(data) >= min_arts,
            "只有 %s 篇" % (len(data) if isinstance(data, list) else "?"),
        )


def check_content():
    """课文内容质量：干净、全英文、能跟打"""
    repairer = TTR.Repairer()
    for key, name, _min in EXPECTED_BOOKS:
        path = os.path.join(ARTICLE_DIR, "%s.json" % key)
        if not os.path.exists(path):
            continue
        data = json.loads(read(path))
        if not isinstance(data, list) or not data:
            continue

        bad_cjk, bad_toc, bad_speaker, bad_empty, bad_field = [], [], [], [], []
        bad_appendix, bad_title, bad_broken = [], [], []
        bad_unit, bad_fffd, bad_overprint, bad_long, bad_apos = [], [], [], [], []
        ids = []
        for a in data:
            ids.append(a.get("id"))
            title = (a.get("title") or "").strip()
            text = a.get("text") or ""
            paras = [p for p in text.split("\n\n") if p.strip()]
            if not title:
                bad_field.append("标题为空")
            if APPENDIX_TITLE_RE.match(title):
                bad_appendix.append(title)
            if EMPTY_LESSON_RE.match(title):
                bad_title.append(title)
            if not paras:
                bad_empty.append(title or "?")
                continue
            if CJK_CHAR_RE.search(text):
                # 课文里嵌一两个汉字当例子是正常的（"the character 旦"），
                # 只有「整段以中文为主」才算脏
                for p in paras:
                    vis = len(re.sub(r"\s", "", p))
                    cjk = len(CJK_CHAR_RE.findall(p))
                    if vis and cjk / float(vis) >= 0.3:
                        bad_cjk.append(title)
                        break
            if TOC_RE.search(text):
                bad_toc.append(title)
            if SPEAKER_RE.search(text):
                bad_speaker.append(title)
            # ① 页脚 "Unit 3" 混进课文
            if UNIT_SEG_RE.search(text):
                bad_unit.append(title)
            # ② U+FFFD（字体缺 ToUnicode，撇号变豆腐块）
            if REPLACEMENT_CHAR in text:
                bad_fffd.append(title)
            # ③ 艺术字双层叠印："WWoorrddss"
            #    叠印 = 整词画两遍 → **每个字母都成对**（重复对 ≥ 2 处）；
            #    "good" / "summer" / "travelling" 只有一处相邻重复，是正常单词。
            for w in re.findall(r"[A-Za-z]{4,}", text):
                pairs = re.findall(r"([A-Za-z])\1", w)
                if len(pairs) < 2:
                    continue
                squashed = "".join(dict.fromkeys(w))
                if len(squashed) >= 3 and squashed.lower() in WORDS:
                    bad_overprint.append("%s: %s" % (title, w))
                    break
            # ④ span 粘连（没补空格）
            m = LONG_TOKEN_RE.search(text)
            if m:
                bad_long.append("%s: %s" % (title, m.group(0)[:24]))
            # ⑤ 弯撇号必须归一成 ASCII
            if CURLY_APOS in text:
                bad_apos.append(title)
            # ⑥ 断词：用提取器同一套判据（R1~R5），不要另起炉灶
            broken = repairer.find_broken(text, limit=3)
            if broken:
                bad_broken.append("%s: %s" % (title, broken[0]))

        check(
            "「%s」课文没有整段中文" % name,
            not bad_cjk,
            "含中文段的篇：%s" % "、".join(bad_cjk[:3]),
        )
        check(
            "「%s」课文里没有目录/栏目残留" % name,
            not bad_toc,
            "残留的篇：%s" % "、".join(bad_toc[:3]),
        )
        check(
            "「%s」课文里没有练习对话残留（A:/B:）" % name,
            not bad_speaker,
            "残留的篇：%s" % "、".join(bad_speaker[:3]),
        )
        check(
            "「%s」课文里没有附录/词汇表" % name,
            not bad_appendix,
            "混进来的篇：%s" % "、".join(bad_appendix[:3]),
        )
        check(
            "「%s」课文标题完整（不是光一个 Lesson n）" % name,
            not bad_title,
            "残缺的篇：%s" % "、".join(bad_title[:3]),
        )
        check(
            "「%s」课文里没有断词（T e / of en）" % name,
            not bad_broken,
            "断词的篇：%s" % "、".join(bad_broken[:3]),
        )
        check(
            "「%s」课文里没有页脚 Unit N 残留" % name,
            not bad_unit,
            "残留的篇：%s" % "、".join(bad_unit[:3]),
        )
        check(
            "「%s」课文里没有 U+FFFD 豆腐块" % name,
            not bad_fffd,
            "含豆腐块的篇：%s" % "、".join(bad_fffd[:3]),
        )
        check(
            "「%s」课文里没有艺术字双层叠印" % name,
            not bad_overprint,
            "叠印的篇：%s" % "、".join(bad_overprint[:3]),
        )
        check(
            "「%s」课文里没有粘连长串（span 少空格）" % name,
            not bad_long,
            "粘连的篇：%s" % "、".join(bad_long[:3]),
        )
        check(
            "「%s」课文撇号已归一成 ASCII" % name,
            not bad_apos,
            "含弯撇号的篇：%s" % "、".join(bad_apos[:3]),
        )
        check(
            "「%s」每篇都有正文" % name,
            not bad_empty,
            "空篇：%s" % "、".join(bad_empty[:3]),
        )
        check(
            "「%s」每篇字段齐全（id/title/text/textTranslate/audioSrc）" % name,
            not bad_field,
            "缺字段：%s" % "、".join(bad_field[:3]),
        )
        check(
            "「%s」课文 id 不重复" % name,
            len(ids) == len(set(ids)),
            "有重复 id",
        )


def check_list():
    """书单条目：13 条都在，字段齐，能被前端读到"""
    if not os.path.exists(LIST_FILE):
        check("public/list/article.json 存在", False, "文件不存在")
        return
    data = json.loads(read(LIST_FILE))
    by_en = {x.get("enName"): x for x in data}
    for key, name, _min in EXPECTED_BOOKS:
        item = by_en.get(key.lower())
        if not item:
            check("书单里有「%s」" % name, False, "list/article.json 里没有 enName=%s" % key.lower())
            continue
        check("书单里有「%s」" % name, True)
        ok_fields = all(
            item.get(f) not in (None, "")
            for f in ("id", "enName", "name", "url", "length", "category", "tags", "type")
        )
        check(
            "「%s」书单条目字段齐全" % name,
            ok_fields,
            "缺字段：" + str([f for f in ("id", "enName", "name", "url", "length", "category", "tags", "type")
                              if item.get(f) in (None, "")]),
        )
        check(
            "「%s」书单条目指向的文件真实存在" % name,
            os.path.exists(os.path.join(ARTICLE_DIR, item.get("url") or "")),
            "找不到 " + str(item.get("url")),
        )
        # length 要跟实际篇数一致
        p = os.path.join(ARTICLE_DIR, item.get("url") or "")
        if os.path.exists(p):
            real = len(json.loads(read(p)))
            check(
                "「%s」书单 length 与实际篇数一致" % name,
                int(item.get("length") or 0) == real,
                "书单写 %s，实际 %d" % (item.get("length"), real),
            )
    # 原有 NCE 不能被弄坏
    for en in ("nce1", "nce2", "nce3", "nce4"):
        check(
            "原有《%s》还在书单里" % en,
            en in by_en,
            "被覆盖了",
        )


def check_script():
    check(
        "提取脚本存在（可复跑）",
        os.path.exists(EXTRACT_SCRIPT),
        "scripts/extract-textbook-articles.py 不见了",
    )


def check_http():
    try:
        req = urllib.request.Request(
            BASE_URL + "/list/article.json", headers={"User-Agent": "check-textbook"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "ignore")
            data = json.loads(body)
            check("HTTP: /list/article.json 可访问", r.status == 200, "状态 %s" % r.status)
            ens = {x.get("enName") for x in data}
            missing = [k for k, _, _ in EXPECTED_BOOKS if k.lower() not in ens]
            check(
                "HTTP: 书单接口里能拿到 13 册课本",
                not missing,
                "缺：" + "、".join(missing),
            )
    except Exception as e:
        check("HTTP: /list/article.json 可访问", False, "请求失败：%s" % e)

    for key, name, _min in EXPECTED_BOOKS:
        try:
            req = urllib.request.Request(
                BASE_URL + "/dicts/en/article/%s.json" % key,
                headers={"User-Agent": "check-textbook"},
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8", "ignore"))
                check(
                    "HTTP: %s 课文文件能下载且非空" % name,
                    r.status == 200 and isinstance(data, list) and len(data) > 0,
                    "状态 %s / 篇数 %s" % (r.status, len(data) if isinstance(data, list) else "?"),
                )
        except Exception as e:
            check("HTTP: %s 课文文件能下载且非空" % name, False, "请求失败：%s" % e)


check_products()
check_content()
check_list()
check_script()
if "--http" in sys.argv:
    check_http()

fail = 0
for name, ok, detail in results:
    if ok:
        print("[PASS] " + name)
    else:
        fail += 1
        print("[FAIL] " + name + ("  —— " + detail if detail else ""))
print("\n合计 %d 项，失败 %d 项" % (len(results), fail))
sys.exit(1 if fail else 0)
