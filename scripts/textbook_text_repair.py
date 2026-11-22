# -*- coding: utf-8 -*-
"""课本课文「文本清洗 + 断词修复」

==============================================================
课文是从扫描 PDF 里抽出来的，文本层有三类脏东西：

1. **撇号不统一**：PDF 里是 U+2019（’），但跟打页是逐字符比对的，
   用户打的是 ASCII 撇号 `'` → 必须归一化，否则永远打不对。
   另有少数字体缺 ToUnicode，撇号直接变成 U+FFFD。

2. **连字被拆**："ﬁ" "ﬂ" "ﬀ" 这些 Unicode 连字字符，
   以及 ArnoPro 字体把 "tt"/"ft"/"Th"/"fl" 连字映射成**空格**，
   结果课文里出现 "Th e" / "att ention" / "oft en" / "bett er"。

3. **连字符词**："well-known" 这类，跟打时要拆成两个词。

断词修复判据（**尺子和修法共用同一套判据**，所以体检器不会假阴性）：
    把 "X Y" 合并成 "XY"，当且仅当全部满足：

    R1  X、Y 都只含字母；X 不以撇号结尾（否则是所有格 "children's way"）
    R2  Y 的首字母是**小写**      → 排掉 "Hou Yi" / "Su Shi" / "Wu Ming"
    R3  XY 在本地词典里
    R4  X **不在**高频词层里     → 排掉 "not able"(notable) / "use less"(useless)
                                   / "visit or"(visitor) / "some day"(someday)
    R5  XY 在自然语料里作为**整词**出现过，或 XY 本身在高频词层里
        → 排掉 "kung fu"（kungfu 是教辅词书收的汉语拼音，不是英语词）

用法：
    from textbook_text_repair import Repairer
    fixed = Repairer().repair(text)
    left = Repairer().find_broken(text)     # 体检器用
"""
import io
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEX_FILE = os.path.join(ROOT, "data", "word-index.json")
STATS_FILE = os.path.join(ROOT, "data", "repair-stats.json")
ARTICLE_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")

# ---------------------------------------------------------------- 字符归一化
# PDF 连字字符 → 普通字母
LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl",
    "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
}
# 弯引号 → ASCII 撇号（跟打页逐字符比对，用户打的是 `'`）
#
# 别只列 U+2019！课本 PDF 里同一个撇号会出现**好几种 Unicode 形态**：
#   U+2019  RIGHT SINGLE QUOTATION MARK   （常见弯撇号）
#   U+2018  LEFT SINGLE QUOTATION MARK    （左单引号）
#   U+201B  HIGH REVERSED-2 QUOTATION MARK（八下 Unit 5/6/7 用的就是这个）
#   U+201A / U+2032 / U+02BC / U+275B      （其它教材偶尔出现）
# 漏掉任何一种，尺子就会放行 → 跟打页那个字**永远打不出来**。
QUOTE_MAP = {
    "’": "'", "‘": "'",
    "“": '"', "”": '"',
    "ʼ": "'", "＇": "'",
    "‛": "'", "‚": "'",
    "′": "'", "ʹ": "'",
    "ʻ": "'", "‵": "'",
}
# 高频词层：这些 src 是「学习者要背的常用词表」，里面的词一定是真英语词
HIGH_LAYER_SRCS = {
    "GaoKao_3500", "CET4_T", "CET6_T", "Oxford5000",
    "OxfordVocabulary_juniorMiddleSH", "ZhongKaoHeXin",
    "Level4luan_2_T", "Level8luan_2_T",
}
# 缩写：主语 + 结尾 → 加撇号（"I ll" → "I'll"）
CONTRACT_SUBJ = {
    "i", "we", "you", "they", "he", "she", "it", "that", "there",
    "who", "what", "where", "here", "let", "this", "there",
}
CONTRACT_END = {"ll", "ve", "m", "re", "d", "s"}

WORD_RE = re.compile(r"[A-Za-z]+")
# 一个「词」：字母 + 内部的撇号/连字符
TOKEN_RE = re.compile(r"[A-Za-z]+(?:['\-][A-Za-z]+)*")
# 夹在两个字母之间的 U+FFFD（缺 ToUnicode 的撇号）
FFFD_APOS_RE = re.compile(r"(?<=[A-Za-z])�(?=[A-Za-z])")


def normalize_chars(text):
    """字符级归一化：连字、弯引号、U+FFFD 撇号"""
    if not text:
        return text
    for k, v in LIGATURES.items():
        if k in text:
            text = text.replace(k, v)
    for k, v in QUOTE_MAP.items():
        if k in text:
            text = text.replace(k, v)
    text = FFFD_APOS_RE.sub("'", text)
    return text


# ---------------------------------------------------------------- 词典 & 语料
class Lexicon(object):
    """本地词典 + 高频词层"""

    def __init__(self, all_words, high_words):
        self.all = all_words
        self.high = high_words

    @classmethod
    def load(cls, path=LEX_FILE):
        allw, high = set(), set()
        if os.path.exists(path):
            with io.open(path, encoding="utf-8") as f:
                data = json.load(f)
            for w, e in data.items():
                lw = w.lower()
                allw.add(lw)
                if isinstance(e, dict) and e.get("src") in HIGH_LAYER_SRCS:
                    high.add(lw)
        return cls(allw, high)

    def has(self, w):
        return w.lower() in self.all

    def is_high(self, w):
        return w.lower() in self.high


def build_stats(lex=None):
    """统计自然语料的 uni / bigram

    语料 = 词典例句 + NCE 课文。
    词典例句是人写的干净英语；NCE 是真课文。都没有的话统计为空，
    此时 R5 退化为「只看高频词层」。
    """
    uni = Counter()
    bigram = Counter()
    # 词典例句
    if os.path.exists(LEX_FILE):
        with io.open(LEX_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for e in data.values():
            if not isinstance(e, dict):
                continue
            for s in e.get("sentences") or []:
                if isinstance(s, dict):
                    s = s.get("c") or ""
                if not s:
                    continue
                ws = [w.lower() for w in WORD_RE.findall(s)]
                uni.update(ws)
                for a, b in zip(ws, ws[1:]):
                    bigram[(a, b)] += 1
    # NCE 课文
    if os.path.isdir(ARTICLE_DIR):
        for fn in sorted(os.listdir(ARTICLE_DIR)):
            if not fn.startswith("NCE_"):
                continue
            try:
                data = json.loads(io.open(os.path.join(ARTICLE_DIR, fn),
                                         encoding="utf-8").read())
            except Exception:
                continue
            for a in data:
                ws = [w.lower() for w in WORD_RE.findall(a.get("text") or "")]
                uni.update(ws)
                for a2, b2 in zip(ws, ws[1:]):
                    bigram[(a2, b2)] += 1
    return {"uni": dict(uni), "bigram": {"%s\t%s" % k: v
                                         for k, v in bigram.items()}}


class Stats(object):
    def __init__(self, uni=None, bigram=None):
        self.uni = uni or Counter()
        self.bigram = bigram or Counter()

    @classmethod
    def load(cls, path=STATS_FILE, rebuild=False):
        if not rebuild and os.path.exists(path):
            try:
                with io.open(path, encoding="utf-8") as f:
                    raw = json.load(f)
                uni = Counter(raw.get("uni") or {})
                bigram = Counter()
                for k, v in (raw.get("bigram") or {}).items():
                    a, _, b = k.partition("\t")
                    bigram[(a, b)] = v
                return cls(uni, bigram)
            except Exception:
                pass
        st = build_stats()
        uni = Counter(st["uni"])
        bigram = Counter()
        for k, v in st["bigram"].items():
            a, _, b = k.partition("\t")
            bigram[(a, b)] = v
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with io.open(path, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False)
        except Exception:
            pass
        return cls(uni, bigram)


# ---------------------------------------------------------------- 修复器
class Repairer(object):
    def __init__(self, lex=None, stats=None):
        self.lex = lex or Lexicon.load()
        self.stats = stats or Stats.load()

    # ---- 断词判定（尺子与修法共用） ----
    def merge_target(self, x, y, x_prefix=""):
        """X Y 该合并成什么？不该合并返回 None

        `x_prefix` 是 X 在原文里的前一个字符（用来排掉所有格 "'s way"）。
        """
        if not re.fullmatch(r"[A-Za-z]+", x) or not re.fullmatch(r"[A-Za-z]+", y):
            return None
        if x_prefix == "'":
            return None                      # R1：所有格 "'s way" 不是断词
        if not y[0].islower():
            return None                      # R2：人名 / 专名
        # 缩写优先："I ll" → "I'll"
        c = self._contraction(x, y)
        if c:
            return c
        xy = (x + y).lower()
        if not self.lex.has(xy):
            return None                      # R3
        # R4：X 必须是个**碎片**，不能是真词
        if len(x) == 1:
            # 单字母碎片太容易撞词（"a long"→along / "s in"→sin /
            # "sat in"→satin），所以单字母要求更严：
            #   Y 不能是高频词（"s in" 的 in 是常用词 → 是两个词）
            #   合并结果必须在高频词层（"r e"→re 不是常用词 → 不认）
            if self.lex.is_high(y):
                return None
            if not self.lex.is_high(xy):
                return None
        else:
            if self.lex.is_high(x):
                return None
            if self.stats.uni.get(x.lower(), 0) > 3:
                return None
        # R5：XY 必须是真的英语词
        if self.lex.is_high(xy) or self.stats.uni.get(xy, 0) > 0:
            return x + y
        return None

    @staticmethod
    def _contraction(x, y):
        a, b = x.lower(), y.lower()
        if a in CONTRACT_SUBJ and b in CONTRACT_END:
            return x + "'" + y
        return None

    # ---- 主流程 ----
    def repair(self, text):
        if not text:
            return text
        text = normalize_chars(text)
        out = []
        pos = 0
        toks = list(TOKEN_RE.finditer(text))
        i = 0
        while i < len(toks):
            m = toks[i]
            # 找下一个 token
            if i + 1 < len(toks):
                m2 = toks[i + 1]
                gap = text[m.end():m2.start()]
                if gap == " ":
                    x, y = m.group(0), m2.group(0)
                    prefix = text[m.start() - 1] if m.start() > 0 else ""
                    merged = self.merge_target(x, y, prefix)
                    if merged:
                        out.append(text[pos:m.start()])
                        out.append(merged)
                        pos = m2.end()
                        i += 2
                        continue
            i += 1
        out.append(text[pos:])
        return "".join(out)

    def find_broken(self, text, limit=10):
        """体检器用：文本里还剩哪些「该合并却没合并」的断词"""
        bad = []
        text = normalize_chars(text or "")
        toks = list(TOKEN_RE.finditer(text))
        for i in range(len(toks) - 1):
            m, m2 = toks[i], toks[i + 1]
            if text[m.end():m2.start()] != " ":
                continue
            x, y = m.group(0), m2.group(0)
            prefix = text[m.start() - 1] if m.start() > 0 else ""
            if self.merge_target(x, y, prefix):
                bad.append("%s %s" % (x, y))
                if len(bad) >= limit:
                    break
        return bad
