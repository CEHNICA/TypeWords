"""
从莱芜五四制英语课本 PDF 提取课文 → TypeWords article 书
==========================================================

输入：课本 PDF（目录见 scripts/local_paths.py 的解析顺序：
      env TW_TEXTBOOK_PDF_DIR → data/local_paths.json → <repo>/课本PDF）
输出：
  public/dicts/en/article/LWCZ_<册>.json   每篇课文一个对象
  public/list/article.json                加对应的书单条目

为什么不能直接 dump 文本：
- 课本 PDF 是**艺术字排版**，粗体标题的 span 会被拆碎（"a nd le a rn"），
  只有正文字体才是完整单词 → 用**字体**分类，而不是关键词黑名单。
- 课文正文散落在插图周围，PDF 的 block 顺序 ≠ 阅读顺序 → 必须按坐标排序。
- 一句话在 PDF 里常常被拆成两行（换行），只看"带标点的那行"会丢掉半句
  → 必须按**续行规则**把行拼回整句。

两种版式的课文长什么样：
  小学：对话（气泡里 或 缩进 + 说话人前缀），一课 = 一页
  初中：阅读课文是自然段（双栏，需要按 x 分栏 + y 聚类）

怎么认出「这不是课文，是练习」：
  - 填空练习：PDF 里会画一条**下划线**（零高度笔画）→ 按笔画位置剔除
  - 编号题：段内有 ≥2 个 "1. " 编号
  - 活动编号：段内有 "2a" "3c" 这种活动号
  - 表格/词库：段内有 "A. xxx B. xxx" 或 ≥3 个 "词：" 形式
  - 练习对话：段内有 "A: xxx" / "B: xxx"

用法：
  python scripts/extract-textbook-articles.py            # 全量
  python scripts/extract-textbook-articles.py --only 小学五四-三年级上册
  python scripts/extract-textbook-articles.py --dump      # 只打印提取结果不写文件
"""
import argparse
import io
import json
import os
import re
import sys
from collections import Counter

import pymupdf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import textbook_text_repair as TTR   # noqa: E402  文本清洗 + 断词修复

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 课本 PDF 所在目录（本机私有路径不入库）
#   env TW_TEXTBOOK_PDF_DIR → data/local_paths.json → <repo>/课本PDF
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from local_paths import resolve_pdf_dir  # noqa: E402
PDF_DIR = resolve_pdf_dir()
ARTICLE_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")
LIST_FILE = os.path.join(ROOT, "public", "list", "article.json")

# ---- 小学段落过滤开关（默认全开；可用环境变量做 A/B 回归）----
REJECT_ELLIPSIS = os.environ.get("TTB_REJECT_ELLIPSIS", "1") == "1"
REJECT_LOWERCASE = os.environ.get("TTB_REJECT_LOWER", "1") == "1"
PRIMARY_MIN_WORDS = int(os.environ.get("TTB_MIN_WORDS", "0") or 0)

# ---------------------------------------------------------------- 册子定义
BOOKS = [
    {"file": "小学五四-三年级上册.pdf", "key": "LWXX_3_1", "name": "莱芜小学英语 三年级上册",
     "stage": "primary", "grade": "三年级上"},
    {"file": "小学五四-三年级下册.pdf", "key": "LWXX_3_2", "name": "莱芜小学英语 三年级下册",
     "stage": "primary", "grade": "三年级下"},
    {"file": "小学五四-四年级上册.pdf", "key": "LWXX_4_1", "name": "莱芜小学英语 四年级上册",
     "stage": "primary", "grade": "四年级上"},
    {"file": "小学五四-四年级下册.pdf", "key": "LWXX_4_2", "name": "莱芜小学英语 四年级下册",
     "stage": "primary", "grade": "四年级下"},
    {"file": "小学五四-五年级上册.pdf", "key": "LWXX_5_1", "name": "莱芜小学英语 五年级上册",
     "stage": "primary", "grade": "五年级上"},
    {"file": "小学五四-五年级下册.pdf", "key": "LWXX_5_2", "name": "莱芜小学英语 五年级下册",
     "stage": "primary", "grade": "五年级下"},
    {"file": "初中五四-六年级上册.pdf", "key": "LWCZ_6_1", "name": "莱芜初中英语 六年级上册",
     "stage": "junior", "grade": "六年级上"},
    {"file": "初中五四-六年级下册.pdf", "key": "LWCZ_6_2", "name": "莱芜初中英语 六年级下册",
     "stage": "junior", "grade": "六年级下"},
    {"file": "初中五四-七年级上册.pdf", "key": "LWCZ_7_1", "name": "莱芜初中英语 七年级上册",
     "stage": "junior", "grade": "七年级上"},
    {"file": "初中五四-七年级下册.pdf", "key": "LWCZ_7_2", "name": "莱芜初中英语 七年级下册",
     "stage": "junior", "grade": "七年级下"},
    {"file": "初中五四-八年级上册.pdf", "key": "LWCZ_8_1", "name": "莱芜初中英语 八年级上册",
     "stage": "junior", "grade": "八年级上"},
    {"file": "初中五四-八年级下册.pdf", "key": "LWCZ_8_2", "name": "莱芜初中英语 八年级下册",
     "stage": "junior", "grade": "八年级下"},
    {"file": "初中五四-九年级全一册.pdf", "key": "LWCZ_9_1", "name": "莱芜初中英语 九年级全一册",
     "stage": "junior", "grade": "九年级"},
]

# ---------------------------------------------------------------- 通用规则
# 粗体/黑体字体 → 用来区分「正文」和「标题/指令」
BOLD_FONT_RE = re.compile(r"(Bold|Black|Smbd|DINCond-Medium|DIN-Medium|DIN-Bold)", re.I)
# 句子结束符
TERMINALS = (".", "!", "?", '"', "'", "”", "’", "。", "！", "？")
# 活动编号（1a / 2b / 3c …）
ACT_ID_RE = re.compile(r"\b\d[a-d]\b")
# 编号题目
NUMBERED_ITEM_RE = re.compile(r"\b\d\s*[.、]\s")
# 练习对话（单字母说话人）
SPEAKER_TAG_RE = re.compile(r"(?:^|[\s“\"(])([A-D])\s*[:：]\s")
# 填空痕迹（文本层面）
BLANK_RE = re.compile(r"…|\b(?:T|F)\s+(?:T|F)\b|_{2,}|\(\s*\)")
# 括号动词练习 "(write) to you"
#
# **坑**：早先写成 `\([a-z]{2,}\s+[^)]*\)` → 课文里的
# "the sea level (or the horizon)" 被当成填空动词，整段课文被丢掉
# （八上 "The Art and History of Chinese Characters" 开篇两段就这么废的）。
# 现在只认**括号里孤零零一个原形动词**，且必须是常见动词表里的词 ——
# 这样 "(dan)"（汉字注音）、"(or the moon)" 都不会误伤。
BRACKET_VERB_WORDS = [
    "write", "read", "look", "listen", "complete", "choose", "find", "act",
    "match", "number", "think", "talk", "share", "use", "check", "draw",
    "play", "sing", "follow", "join", "point", "circle", "underline",
    "translate", "ask", "answer", "work", "let", "put", "make", "take",
    "learn", "study", "practise", "practice", "repeat", "fill", "see",
    "go", "get", "come", "give", "call", "mean", "spell", "open", "close",
    "start", "stop", "move", "live", "help", "want", "need", "like",
    "love", "do", "say", "tell", "show", "buy", "send", "eat", "drink",
    "sleep", "run", "walk", "swim", "dance", "count", "add", "brush",
    "wash", "wear", "sit", "stand", "wait", "stay", "try", "keep",
    "bring", "carry", "clean", "wash", "cook", "ride", "fly", "sing",
    "cut", "fix", "wash", "climb", "throw", "catch", "kiss", "hug",
    "visit", "travel", "arrive", "leave", "return", "invite", "borrow",
    "lend", "buy", "sell", "spend", "save", "lose", "find", "win",
    "play", "join", "wear", "wash", "cook", "clean", "iron", "fold",
]
BRACKET_VERB_RE = re.compile(
    r"\(\s*(?:%s)\s*\)" % "|".join(sorted(set(BRACKET_VERB_WORDS))), re.I)
# 表格行 "Name: John Lennon Year of birth: 1940"
TABLE_FIELD_RE = re.compile(r"\b[A-Z][A-Za-z ]{1,20}:")
# 指令句（粗体的活动说明）
INSTRUCTION_PAT = re.compile(
    r"^(look|listen|read|write|complete|choose|find|act|match|number|think|talk|share|use|check|"
    r"review|draw|play|sing|follow|join|point|circle|underline|translate|ask|answer|work|let|"
    r"put|make|take|learn|study|practise|practice|repeat|fill|discuss|in pairs|in groups|"
    r"self check|fun time|culture corner|words in each unit|words and chunks|pronunciation|"
    r"grammar focus|section [a-d]|here and now|big question|project|review|"
    r"add the times|read the video|describe the photo|imagine you|help ben|"
    r"after you read|before you read|use the information|according to the chart)",
    re.I,
)
# 装饰性散排字母（"S E C T I O N"）
SPACED_CAPS_RE = re.compile(r"^(?:[A-Z]\s*)+$")

# ---------------------------------------------------------------- 初中课文标题字体
# 两种版式（实测 7 册初中）：
#   莱芜版（六上~九上）：课文标题 = DINCond-Black 20/24pt
#       —— MyriadPro-Bold 是**页眉话题行**（"What do we like about your family?"），
#          Arial-Black 是 Section A/B 字母，MyriadPro-Bold 18 是单元导语
#   人教版（八下）：课文标题 = ArnoPro-SmbdCaption 15pt
#       —— ArnoPro-BoldDisplay 28pt 是**单元大标题**（"When was he born?"）
# 靠字号区分不可靠（两版标题字号不同，页眉话题字号却一样），必须靠字体。
JUNIOR_TITLE_FONTS = {
    "DINCond-Black",            # 莱芜版课文标题
    "ArnoPro-SmbdCaption",      # 人教版课文标题
}
# 明确**不是**课文标题的字体（页眉话题 / 单元大标题 / Section 字母 / 栏目标）
JUNIOR_NOT_TITLE_FONTS = {
    "MyriadPro-Bold",           # 页眉话题行
    "ArnoPro-BoldDisplay",      # 人教版单元大标题
    "Arial-Black",              # Section A/B 字母
    "DIN-Black",                # Section A/B 字母
    "DIN-Medium",               # 单元名
    "DINAlternate-Bold",        # UNIT n
    "DIN-BoldAlternate",
    "FZLTTHJW--GB1-0",          # 单元大数字
    "JokermanLetPlain",         # "Section"
    "AGaramondPro-Bold",        # "Grammar"
    "Frutiger-BlackCn",         # 页码 / "Contents"
    "Frutiger-ExtraBlackCn",    # 页眉 "UNIT n"
    "AppleGothic",              # 目录里的 ➊ ➋
    "TektonPro-BoldCond",       # 页脚格言
    "MyanmarMN-Bold",           # 偶尔的课文副标题
    "DINCond-Bold",
    "SignPainter-HouseScript",
    "TimesNewRomanPS-BoldMT",   # 九上 "Chopin: A Great Inspiration"
}
# 说话人标签（"Wang Hong:" / "Peter:" / "Miss Zhang："）
SPEAKER_LABEL_RE = re.compile(r"^[A-Z][a-zA-Z]*(?:\s[A-Z][a-zA-Z]*)*\s*[:：]\s*\S")
# 单独的说话人标签（整段就是 "Alice:" / "Lin Hui:"）
SPEAKER_LABEL_ONLY_RE = re.compile(r"^[A-Z][a-zA-Z]*(?:\s[A-Z][a-zA-Z]*)*\s*[:：]$")
# 续行缩进量（对话换行后往右缩进这么多）
CONT_INDENT = (15, 40)


def clean_text(s):
    s = s.replace("\u00a0", " ").replace("\u200b", "").replace("\u2007", " ")
    s = s.replace("\u3000", " ")
    s = re.sub(r"[ \t]{2,}", " ", s)
    # PDF 里 "Anna:" 和后面的话是两个 span，拼起来会变成 "Anna:It's" → 补空格
    s = re.sub(r"([A-Za-z]\.)[:：](?=[A-Za-z])", r"\1: ", s)
    # 字符级归一化：连字（ﬁﬂ）、弯引号（’→'）、缺 ToUnicode 的 U+FFFD 撇号
    s = TTR.normalize_chars(s)
    return s.strip()


_REPAIRER = None


def repairer():
    """全局 repairer（懒加载：词典 26MB，构造要几秒）"""
    global _REPAIRER
    if _REPAIRER is None:
        _REPAIRER = TTR.Repairer()
    return _REPAIRER


def repair_text(s):
    """文本清洗 + 断词修复（撇号归一化 + 'Th e' → 'The'）"""
    if not s:
        return s
    return repairer().repair(s)


CJK_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")


def has_cjk(s):
    """这一串里有没有中文字符（**任意一个**就算）"""
    return bool(CJK_CHAR_RE.search(s))


def is_chinese_line(s):
    """这一行是不是「中文说明行」（教材的中文注释、指令提示）

    **坑**：英文课文里经常嵌一两个汉字当例子，比如
    「...in the Chinese character "旦 (dan)", the upper part...」
    「a tree is 木, a group of trees is 林, and a forest is 森.」
    早先用 `has_cjk()` 一刀切 → 整行英文被丢掉，段落从中间开始、
    句子被劈成两半（八上 "The Art and History of Chinese Characters" 就是这么废的）。

    判据：汉字数 >= 2 **且** 汉字占可见字符 >= 15% → 才算中文行。
    """
    if not s:
        return False
    cjk = len(CJK_CHAR_RE.findall(s))
    if cjk < 2:
        return False
    visible = len(re.sub(r"\s", "", s))
    if visible <= 0:
        return False
    return cjk / float(visible) >= 0.15


def ends_sentence(s):
    return s.rstrip().endswith(TERMINALS)


def font_profile(line):
    """一行里占字数最多的字体 + 字号；以及粗体占比"""
    counts = Counter()
    bold_chars = 0
    total = 0
    for sp in line["spans"]:
        t = sp["text"].strip()
        if not t:
            continue
        n = len(t)
        total += n
        counts[sp["font"]] += n
        if BOLD_FONT_RE.search(sp["font"]):
            bold_chars += n
    if not total:
        return None, 0, 1.0
    font = counts.most_common(1)[0][0]
    return font, total, bold_chars / float(total)


def _same_text_row(a, b):
    """两个字形是不是同一行（按垂直重叠判定，对页面倾斜免疫）

    **坑（高字形「桥接」两行）**：聚行是「拿新字形和当前行最后一个字形比」，
    于是一个**又高又大的装饰字母**（Section 的巨型 "B"，38pt）可以同时和
    上下的正文行都「垂直重叠 100%」→ 把两行**桥接成一行**。
    后果：课本的折行标题被拼成一团乱码
    （"What do we need to know about a" + "new friend?" → "Wnehwa tf rdieon wde?"）。

    解法：高度差太多的两个字形不算同一行（比值 < 0.55 直接分开）。
    正常正文相邻字形高度一致（比值 ≈ 1），不受影响。
    """
    top = max(a["bbox"][1], b["bbox"][1])
    bot = min(a["bbox"][3], b["bbox"][3])
    ov = bot - top
    if ov <= 0:
        return False
    ha = a["bbox"][3] - a["bbox"][1]
    hb = b["bbox"][3] - b["bbox"][1]
    h = min(ha, hb)
    if h <= 0:
        return False
    big = max(ha, hb)
    if big > 0 and h / big < 0.55:
        return False       # 高度差太多 → 不是一个行
    return ov >= 0.5 * h


def _dedupe_overprint(items):
    """去掉「描边（stroke）叠印」产生的重复字形

    课本标题用了描边效果：同一个位置被**画了两遍** —— 字符相同、bbox 几乎重合，
    但 origin 有 0.3~1.1pt 的偏移（描边层比填充层偏一点点）。
    不去重就会得到 "LLiisstteenn aanndd ttaallkk"（小学）/
    "WWoorrddss aanndd cchhuunnkkss"（初中）。

    **按 origin 去重没用**（偏移非 0），只能按 **bbox 重合度**：
    同字符 + 字号相同 + 横向/纵向重合都 ≥ 70% → 判定为叠印副本。

    **阈值不能低**：正文里相邻字母的 advance bbox 本来就重叠 1.5~2.7pt
    （约字宽的 20%）→ 70% 才不会误杀正常文字。
    """
    if not items:
        return items
    # 空间哈希：桶边长 3pt，偏移最大 1.1pt → 只需看 3×3 邻域
    buckets = {}
    kept = []
    for it in items:
        bb = it["bbox"]
        w = bb[2] - bb[0]
        h = bb[3] - bb[1]
        dup = False
        if w > 0 and h > 0:
            bx = int(bb[0] // 3)
            by = int(bb[1] // 3)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for p in buckets.get((bx + dx, by + dy), ()):
                        if p["t"] != it["t"]:
                            continue
                        if abs(p["size"] - it["size"]) > 0.6:
                            continue
                        pb = p["bbox"]
                        pw = pb[2] - pb[0]
                        ph = pb[3] - pb[1]
                        if pw <= 0 or ph <= 0:
                            continue
                        ox_ov = min(bb[2], pb[2]) - max(bb[0], pb[0])
                        oy_ov = min(bb[3], pb[3]) - max(bb[1], pb[1])
                        if ox_ov >= 0.7 * min(w, pw) and oy_ov >= 0.7 * min(h, ph):
                            dup = True
                            break
                    if dup:
                        break
                if dup:
                    break
        if dup:
            continue
        kept.append(it)
        key = (int(it["bbox"][0] // 3), int(it["bbox"][1] // 3))
        buckets.setdefault(key, []).append(it)
    return kept


def _needs_space(prev_span, next_span):
    """两个 span 相接的地方要不要补空格

    PDF 里同一句话常被拆成多个 span（字体/字号/粗细不同），直接拼起来会变成
    "Lesson 1What's wrong with you?"。

    **判据用几何间距，不用字符类别**：
    - 课本有专门的字体（HeinemannSpecial-Bold）给单词里的**单个字母**做造型，
      "same" 会被拆成 "s"(Arial-Black) + "a"(特殊字体) + "me"(Arial-Black)
      —— 按字符类别补空格会变成 "s a me"（错），按间距判断才是 "same"（对）。
    - 真·词间距在 PDF 里是实打实的横向空隙（≥0.2em），字内间距接近 0。

    另外：冒号后面直接跟字母一定是缺空格（"Anna:It's"）。
    """
    ptxt = prev_span["text"]
    ntxt = next_span["text"]
    if not ptxt or not ntxt:
        return False
    a = ptxt[-1]
    b = ntxt[0]
    if a.isspace() or b.isspace():
        return False
    if b == "'" and a.isalnum():
        return False
    if a in "-'":
        return False
    if a in ":;,!?)" and b.isalnum():
        return True
    gap = next_span["_x0"] - prev_span["_x1"]
    size = max(prev_span["size"], next_span["size"]) or 1.0
    return gap > 0.18 * size


def _join_spans(spans):
    """把 span 拼成一行文本（必要时补空格）"""
    parts = []
    for i, s in enumerate(spans):
        if i > 0 and _needs_space(spans[i - 1], s):
            parts.append(" ")
        parts.append(s["text"])
    return "".join(parts)


def collect_lines(page):
    """把一页拆成行：[{text, spans, size, bbox, y, x, gap}]

    用 `page.get_texttrace()` 而不是 `page.get_text("dict")`：
    实测同一本 96 页的课本 PDF，`dict` 要 **50.5 秒**，`texttrace` 只要 **0.2 秒**
    （250 倍）。texttrace 给的是 span + 逐字符 origin/bbox，行要自己按**基线 y** 聚类重建。
    """
    tr = page.get_texttrace()
    items = []
    for sp in tr:
        if sp.get("type") != 0:
            continue
        font = sp.get("font", "")
        size = sp.get("size", 0)
        for ch in sp.get("chars", []):
            uni = ch[0]
            if uni is None:
                continue
            c = chr(uni)
            if not c.strip() and c not in (" ",):
                continue
            bb = ch[3]
            items.append({
                "t": c,
                "ox": ch[2][0],
                "oy": ch[2][1],
                "font": font,
                "size": size,
                "bbox": bb,
            })
    if not items:
        return []

    # 去掉描边叠印的重复字形（"LLiisstteenn"）
    items = _dedupe_overprint(items)

    # 按「字形框垂直重叠」聚成行 —— **不能**按基线 y 的固定容差聚
    #
    # **坑（扫描页有轻微倾斜）**：课本 PDF 的正文页是斜着印的，基线 y 沿
    # 一行缓慢下移（实测每字漂 0.2pt，一行 60 字就漂 12pt）。早先按
    # `abs(oy - 行首oy) <= 3.0` 聚行 → 一行被从**词中间**劈成两三段，
    # 拼段落时补空格 → 满篇断词（"hav e" / "Th e" / "W elcome" / "oft en"）。
    #
    # 垂直重叠判据对倾斜免疫：同一行的字形框互相压着（行高 12pt、漂移 3pt
    # → 重叠 9pt = 75%），相邻两行完全不重叠（行距 16pt > 字高 12pt）。
    items.sort(key=lambda it: (it["oy"], it["ox"]))
    rows = []
    for it in items:
        if rows and _same_text_row(rows[-1][-1], it):
            rows[-1].append(it)
        else:
            rows.append([it])

    # 装饰性字母（"S E C T I O N" 阶梯状排布）会和话题行共用基线，
    # 但横向隔了 100pt —— 按**横向空隙**把一行再切成若干「连续片段」，
    # 每个片段才算一行文字（dict 版天然是分块，效果一样）。
    seg_rows = []
    for row in rows:
        row.sort(key=lambda it: it["ox"])
        cur = [row[0]]
        lead = 0.0
        for prev, it in zip(row, row[1:]):
            gap = it["bbox"][0] - prev["bbox"][2]
            if gap > max(15.0, 1.2 * it["size"]):
                seg_rows.append((cur, lead))
                cur = [it]
                lead = gap
            else:
                cur.append(it)
        seg_rows.append((cur, lead))

    lines = []
    for row, lead_gap in seg_rows:
        row.sort(key=lambda it: it["ox"])
        # 连续同字体同字号 → 一个 span
        spans = []
        for it in row:
            if spans and spans[-1]["font"] == it["font"] and \
                    abs(spans[-1]["size"] - it["size"]) < 0.01:
                spans[-1]["text"] += it["t"]
                spans[-1]["_x1"] = it["bbox"][2]
                spans[-1]["bbox"] = (
                    min(spans[-1]["bbox"][0], it["bbox"][0]),
                    min(spans[-1]["bbox"][1], it["bbox"][1]),
                    max(spans[-1]["bbox"][2], it["bbox"][2]),
                    max(spans[-1]["bbox"][3], it["bbox"][3]),
                )
            else:
                spans.append({
                    "text": it["t"],
                    "font": it["font"],
                    "size": it["size"],
                    "bbox": tuple(it["bbox"]),
                    "_x0": it["bbox"][0],
                    "_x1": it["bbox"][2],
                })
        text = clean_text(_join_spans(spans))
        if not text:
            continue
        bbox = [
            round(min(s["bbox"][0] for s in spans), 1),
            round(min(s["bbox"][1] for s in spans), 1),
            round(max(s["bbox"][2] for s in spans), 1),
            round(max(s["bbox"][3] for s in spans), 1),
        ]
        # 行内最大横向空隙：填空练习的「空格」在 PDF 里没有字符，只有空隙
        gap = lead_gap
        gap_punct = bool(row) and not row[0]["t"][0].isalnum() if lead_gap > 0 else False
        for i in range(len(row) - 1):
            g = row[i + 1]["bbox"][0] - row[i]["bbox"][2]
            if g > gap:
                gap = g
                nxt = row[i + 1]["t"]
                # 空格后面紧跟标点（"…it's ____ . Many people…"）→ 那是填空
                # 空格后面跟单词（"It's | in Chongqing…"）→ 那是绕排缩进，不是填空
                gap_punct = bool(nxt) and not nxt[0].isalnum()
        ln = {
            "text": text,
            "spans": spans,
            "fonts": [s["font"] for s in spans],
            "size": max(round(s["size"]) for s in spans),
            "bbox": bbox,
            "y": round((bbox[1] + bbox[3]) / 2, 1),
            "x": round(bbox[0], 1),
            "x1": round(bbox[2], 1),
            "gap": round(gap, 1),
            "gap_punct": gap_punct,
        }
        ln["font"], _n, ln["bold_ratio"] = font_profile(ln)
        # 说话人标签（"Alice:" / "Lin Hui:"）用 DIN-Medium 10pt 单独排版，
        # 跟正文不是一套字体 → 数出来，后面用来区分「对话」和「表格字段」
        ln["speakers"] = sum(
            1 for s in spans
            if s["font"].startswith("DIN-Medium")
            and SPEAKER_LABEL_ONLY_RE.match(s["text"].strip()))
        lines.append(ln)
    return lines


def page_rules(page):
    """一次遍历拿到两种横线信息（性能：`get_drawings()` 单独调很慢）

    返回 (blanks, all_ys)：
      blanks —— 「填空用的下划线」：零高度笔画，宽 > 15pt，
                排除表格网格线（同一条横线出现 ≥3 次）。
      all_ys —— 页面**所有**零高度横线的 y（含表格网格线）。
    """
    strokes = []
    for d in page.get_drawings():
        if d.get("type") not in ("s", "ms"):
            continue
        for it in d.get("items", []):
            if it[0] != "l":
                continue
            p1, p2 = it[1], it[2]
            if abs(p1.y - p2.y) > 1.5:
                continue
            if abs(p2.x - p1.x) < 15:
                continue
            strokes.append((round(p1.y, 1), round(min(p1.x, p2.x), 1),
                            round(max(p1.x, p2.x), 1)))
    cnt = Counter((a, b) for _, a, b in strokes)
    blanks = [s for s in strokes if cnt[(s[1], s[2])] < 3]
    all_ys = sorted(set(s[0] for s in strokes))
    return blanks, all_ys


def blank_underlines(page):
    """页面上「填空用的下划线」：零高度笔画，宽 > 15pt

    表格网格线也是零高度笔画，但同一条横线会出现 ≥3 次（成网格）→ 排除。
    真课文页一个下划线都没有（教材不给人名生词加线），所以这个信号很干净。
    """
    return page_rules(page)[0]


def all_underlines(page):
    """页面上**所有**零高度横线（含表格网格线）的 y 坐标

    表格里的问答（"Do you have any friends living in New Zealand?"）被 PDF
    拼成一行，光看文本分不出是表格；但表格一定有横线 → 用线来定位表格区。
    """
    return page_rules(page)[1]


def body_font_profile(doc):
    """自动识别「正文用哪个字体 + 字号」

    小学各册排版完全不一样（三上~五上是 HeinemannSpecial-Roman，五下是 ArialMT），
    写死字体必然漏册 → 按字符数投票。
    """
    cnt = Counter()
    for page in list(doc)[:30]:
        for l in collect_lines(page):
            if is_chinese_line(l["text"]):
                continue
            if l["bold_ratio"] > 0.5:
                continue
            if not (10 <= l["size"] <= 17):
                continue
            cnt[(l["font"], l["size"])] += len(l["text"])
    if not cnt:
        return None, None
    (font, size), _n = cnt.most_common(1)[0]
    return font, size


# ================================================================ 小学
SECTION_RE = re.compile(r"^\s*(\d)\s*[^\dA-Za-z]")


def line_unit_label(l):
    """行内 **span 级**找 "Unit N"

    **坑**：页脚的 "Unit 1" 和页码 "3" 是同一行的**两个 span**，
    拼起来的整行文本是 "Unit 13" → 用整行正则读出来的单元号是 13（错的，
    产物里出现过 "Unit 13" / "Unit 327" / "Unit 433"）。
    反过来也有 "2Unit 1"（页码在前）→ 整行正则压根匹配不上。
    所以必须**逐 span** 匹配。
    """
    for s in l.get("spans") or []:
        m = re.match(r"^unit\s*(\d+)$", s["text"].strip(), re.I)
        if m:
            return "Unit %s" % m.group(1)
    return None


def split_sections(lines):
    """按活动区标题把一页切成若干区

    活动区标题 = 16pt 以上 + "1 Look, listen and learn" / "1. Listen and say"
    这种「编号 + 指令」开头。标题行本身不计入任何区。

    返回 [(区编号或 None, [行])]。
    """
    secs = []
    num = None
    cur = []
    for l in sorted(lines, key=lambda x: (x["y"], x["x"])):
        t = l["text"].strip()
        if l["size"] >= 16:
            m = SECTION_RE.match(t)
            if m:
                secs.append((num, cur))
                num = m.group(1)
                cur = []
                continue
        cur.append(l)
    secs.append((num, cur))
    return secs


def _h_overlap(a, b, ratio=0.5):
    """两个字形行的横向重合度（相对窄的那个）"""
    ax0, ax1 = a["bbox"][0], a["bbox"][2]
    bx0, bx1 = b["bbox"][0], b["bbox"][2]
    ov = min(ax1, bx1) - max(ax0, bx0)
    if ov <= 0:
        return 0.0
    narrow = min(ax1 - ax0, bx1 - bx0)
    if narrow <= 0:
        return 0.0
    return ov / float(narrow)


def _lesson_extra_lines(lines, li):
    """课名块（"Lesson 1" 旁边的课名）

    三种版式都见过：
    - **A 同行右侧更大字号的块**（五下 "Lesson 1" x=33 + 28pt 课名 x=174，
      课名还可能折成两行）
    - **B 下一行的课名**（三上 "Lesson 3" x=211 + 下一行 "My father is a PE teacher" x=79）
    - **C 下一行的折行尾巴**（五下 "Lesson 3They are having lots" + 下一行 "of fun" x=271）

    B 和 C 用 **x 相对 li.x 的位置**区分：课名在左边（B）还是右边（C）。
    """
    # ---- 版式 A：同行右侧更大字号的块
    cands = [l for l in lines
             if l is not li and abs(l["y"] - li["y"]) <= 12
             and l["x"] > li["x1"] + 4 and l["size"] > li["size"]]
    if cands:
        c = min(cands, key=lambda l: (l["x"], l["y"]))
        extra = [c]
        # 课名折行：同字号、与 c 横向重合、行距 ≤ 34pt
        for l2 in sorted(lines, key=lambda x: x["y"]):
            if l2 is c or l2["y"] <= c["y"]:
                continue
            if l2["y"] - c["y"] > 34:
                break
            if abs(l2["size"] - c["size"]) > 0.6:
                continue
            if _h_overlap(l2, c, 0.5) < 0.5:
                continue
            extra.append(l2)
        return extra

    # ---- 版式 B / C：下一行的大字（课名）
    # 字号允许比 "Lesson N" **略小**（四上 "Lesson 3" 28pt + 下一行
    # "What do you do on Saturdays?" 26pt → 早先按「字号必须完全相同」
    # 判定，课名直接丢了，标题只剩 "Lesson 3"）
    below = [l for l in lines
             if l is not li and 18 <= l["y"] - li["y"] <= 46
             and li["size"] - 3 <= l["size"] <= li["size"]
             and l["size"] >= 18
             and not re.match(r"^lesson\s*\d+", l["text"].strip(), re.I)]
    if not below:
        return []
    b = min(below, key=lambda l: l["y"])
    if b["x"] < li["x"]:
        return [b]          # 版式 B：独立一行课名
    return [b]              # 版式 C：li 自己的折行尾巴


def _lesson_title(lines, li):
    """Lesson 标题块的完整标题 = "Lesson N" + 课名"""
    base = li["text"].strip()
    m = re.match(r"^(lesson\s*\d+)\b", base, re.I)
    if not m:
        return None
    label = m.group(1)
    rest = base[m.end():].strip()
    extra = _lesson_extra_lines(lines, li)
    if extra:
        tail = " ".join(x["text"].strip() for x in extra).strip()
        name = ("%s %s" % (rest, tail)).strip() if rest else tail
    else:
        name = rest
    if not name:
        return label
    return "%s %s" % (label, name)


def _side_split(items, page_w):
    """按页面中线分左右两栏（对话是左右交替的）"""
    half = page_w / 2.0
    left = [x for x in items if x["x"] < half]
    right = [x for x in items if x["x"] >= half]
    return left, right


def _merge_continuations(lines):
    """把被换行拆开的句子拼回去

    两种断行情况：
    1. 上一行**没有句末标点** → 它是被截断的半句，下一行是它的续行
    2. 上一行有句末标点，但下一行**往右缩进了一小段**（对话续行缩进 ~24pt），
       且下一行**不是新的说话人行** → 也是续行
    """
    out = []
    cur = None
    for l in sorted(lines, key=lambda x: (x["y"], x["x"])):
        if cur is not None:
            prev = cur[-1]
            dx = l["x"] - prev["x"]
            close = 0 < (l["y"] - prev["y"]) <= prev["size"] * 2.2
            if close and dx >= -25:
                if not ends_sentence(prev["text"]):
                    cur.append(l)
                    continue
                if (CONT_INDENT[0] <= dx <= CONT_INDENT[1]
                        and not SPEAKER_LABEL_RE.match(l["text"])):
                    cur.append(l)
                    continue
        cur = [l]
        out.append(cur)
    return out


def _utterance_text(group):
    parts = []
    for l in group:
        parts.append(l["text"])
    return " ".join(parts).strip()


def split_two_columns(lines):
    """把正文行拆成左右两栏（是「真双栏」才拆，否则返回 None）

    真双栏的特征（小学五上/五下的短文就是这种）：
    - 左栏行右边界明显不到页面右边界（窄带）
    - 右栏从页面文字顶部就开始（不是从中间）
    → 读法：**左栏读完再读右栏**

    注意下限：绕排插图的短文常只有 **3+3 = 6 行**，用 8 行下限会漏判，
    结果左右两栏**逐行交错**（"Some They were his students ten teenagers…"）。

    还有一种版式是**并排两列**（小学 "Read and enjoy" 的韵文）：
    左边一句、右边一句，同一水平带各一行，句子在列内硬折行
    （"A panda has a big head," / "but it has small ears."）。
    这种块行数少（2+1 / 2+2），必须一起放行 —— 否则逗号结尾的半句
    会被 ends_sentence 直接丢掉，课文只剩后半句。
    """
    if len(lines) < 3:
        return None
    page_right = max(l["x1"] for l in lines)
    xs = sorted(l["x"] for l in lines)
    gaps = [(xs[i + 1] - xs[i], xs[i]) for i in range(len(xs) - 1)]
    if not gaps:
        return None
    maxgap, xat = max(gaps)
    if maxgap <= 60:
        return None
    left = sorted([l for l in lines if l["x"] <= xat], key=lambda l: (l["y"], l["x"]))
    right = sorted([l for l in lines if l["x"] > xat], key=lambda l: (l["y"], l["x"]))
    if len(left) < 2 or len(right) < 1:
        return None
    if max(l["x1"] for l in left) > page_right - 60:
        return None
    text_top = min(l["y"] for l in lines)
    if min(l["y"] for l in right) > text_top + 40:
        return None
    return [left, right]


def _paired_rows(left, right):
    """两列是不是「并排」（同一水平带上左右各一句）

    小学韵文是并排两列；真双栏散文是左右各连续排（同一 y 没有对应行）；
    对话气泡是左右交错（y 也对不上）。
    返回配对比例：0 = 完全不对齐，1 = 逐行对齐。
    """
    ly = sorted(l["y"] for l in left)
    ry = sorted(l["y"] for l in right)
    m = min(len(ly), len(ry))
    if m == 0:
        return 0.0
    hits = 0
    j = 0
    for y in ly:
        while j < len(ry) and ry[j] < y - 2:
            j += 1
        if j < len(ry) and abs(ry[j] - y) <= 2:
            hits += 1
    return hits / float(m)


def split_blocks(lines, gap_ratio=2.5):
    """按 y 的「大空隙」把正文切成若干块

    小学课本一页里经常有好几段独立内容（插图把它们隔开），
    每一块内部再单独判断版式。
    """
    if not lines:
        return []
    lines = sorted(lines, key=lambda l: (l["y"], l["x"]))
    blocks = []
    cur = [lines[0]]
    for l in lines[1:]:
        prev = cur[-1]
        if (l["y"] - prev["y"]) > max(prev["size"], l["size"]) * gap_ratio:
            blocks.append(cur)
            cur = [l]
        else:
            cur.append(l)
    blocks.append(cur)
    return blocks


def _continuation_ratio(col):
    """这一栏里「上一行没结句（是换行续写）」的比例

    散文（双栏短文）：行是硬折断的 → 比例高
    对话（气泡）：每句都是完整的一句话 → 比例低

    下限必须是 2 而不是 3：并排韵文常常只有 2 行一列，
    早先按 3 行算会直接返回 0，把「逗号结尾的半句 + 它的续行」判成不连续。
    """
    if len(col) < 2:
        return 0.0
    pairs = list(zip(col, col[1:]))
    cont = sum(1 for a, b in pairs if not ends_sentence(a["text"]))
    return cont / float(len(pairs))


def _join_prose(col, gap_ratio=1.6):
    """把一栏散文行拼成段落（按 y 大空隙分段，段内行用空格连起来）"""
    col = sorted(col, key=lambda l: (l["y"], l["x"]))
    paras = []
    cur = []
    prev = None
    for l in col:
        if prev is not None and (l["y"] - prev["y"]) > max(prev["size"], l["size"]) * gap_ratio and cur:
            paras.append(" ".join(cur).strip())
            cur = []
        cur.append(l["text"])
        prev = l
    if cur:
        paras.append(" ".join(cur).strip())
    return paras


def _has_hard_fold(col):
    """这一列里有没有**真正的硬折行**

    硬折行 = 上一行没结句（以逗号/无标点结尾）+ 下一行紧接着（行距 ≤ 1.8 倍字号）。
    这是「按列读」唯一的可靠前提：
    - 并排韵文 / 双栏散文 → 有硬折行 ✓
    - 对话气泡（左右交替）→ 每句都是完整句，列内行距又大 → 没有硬折行 ✗

    **不能用「上一行没结句的比例」当前提**：对话气泡里只要有一句
    "Nice to meet you, Guo Yang." 之类以逗号结尾，比例就超阈值，
    整页对话会被误当成并排两列，顺序变成「左列读完再右列」→ 课文错乱。
    """
    for a, b in zip(col, col[1:]):
        if not ends_sentence(a["text"].strip()) and (b["y"] - a["y"]) <= a["size"] * 1.8:
            return True
    return False


def read_block(block):
    """读一个内容块，返回段落列表

    双栏散文 / 并排两列（小学韵文）→ 左栏读完再读右栏，列内硬折行拼回整句
    其余（单栏 / 气泡对话）→ 按 (y, x) 顺序逐句读
    """
    cols = split_two_columns(block)
    if cols:
        left, right = cols
        if _has_hard_fold(left) or _has_hard_fold(right):
            paras = []
            for col in (left, right):
                paras.extend(_join_prose(col))
            return paras
    return [_utterance_text(g) for g in _merge_continuations(block)]


def _lesson_marks(pages):
    """扫全书找「课」标题行（"Lesson 1  Hi! I'm Jenny"）

    小学每课跨**两页**，课标题在两页上各出现一次（一次是目录/预览页，
    一次是正文页），所以相邻的同名标题要归并成一课。

    **不能**再拿「下一行同字体」去拼课名 —— 那是五下误拼的根源
    （"Lesson 3 of fun"：下一行是折行的课名尾巴）。
    课名要么在同一行里，要么在**同行右侧更大字号的块**里，见 `_lesson_title`。
    """
    marks = []
    for pno, lines in enumerate(pages):
        for l in lines:
            t = l["text"].strip()
            if l["size"] < 20 or is_chinese_line(t):
                continue
            if not re.match(r"^lesson\s*\d+", t, re.I):
                continue
            title = _lesson_title(lines, l)
            if not title:
                continue
            marks.append((pno, l["y"], title))
    return marks


def _merge_lessons(marks, n_pages):
    """一课 = Lesson 标题页 + **紧接着的一页**（小学每课跨两页）

    **坑**：不能一路吃到「下一个 Lesson 标题页」—— 中间夹着下一个单元的
    扉页和「本单元课文预览页」，那些页没有 Lesson 标题，会被整锅端进上一课
    （实测五下 Unit2 的 "Lesson 4 Again, please" 一度吞了 51 段、跨了 17 页）。

    同名相邻的标题（三上 p10 / p11 的 "Lesson 1 Hi! I'm Jenny"，
    p11 是单元扉页）属于**同一课**，要跳过。
    """
    lessons = []
    i = 0
    while i < len(marks):
        pno, y, title = marks[i]
        j = i + 1
        while j < len(marks) and marks[j][2] == title:
            j += 1
        next_p = marks[j][0] if j < len(marks) else n_pages
        p1 = min(pno + 1, max(pno, next_p - 1))
        lessons.append({"p0": pno, "p1": p1, "title": title})
        i = j
    return lessons


def is_primary_para(t):
    """小学：这一句是课文内容（对话气泡 / 短文），而不是练习题？

    小学课本里练习和课文混排，靠这几个特征区分：
    - 填空线（"He has ________."）
    - 编号题（"(1) It's September 10 today."）
    - 全是问句的讨论题（"When are days long? Why can planes fly?"）
    - **单字母说话人的练习对话**（"A: What subjects do you like?" /
      "B: I like science and IT."）—— 课文的对话说话人是**人名**
      （"Li Ming: …" / "Peter: …"），一眼能分开
    - 表格行（"Activity / Name / visit / take"）
    """
    t = t.strip()
    if len(t) < 8:
        return False
    if re.search(r"_{3,}", t):
        return False
    if re.match(r"^\(?\d+\)?[\s.]", t):
        return False
    if len(re.findall(r"\(\d+\)", t)) >= 2:
        return False
    # 练习对话：单字母说话人
    if re.match(r"^[A-D]\s*[:：]\s", t):
        return False
    # 表格行 / 勾叉 / 星号标记
    if re.search(r"\b(Subject|Activity)\b", t):
        return False
    if re.search(r"[√×☆★]", t):
        return False
    # 填空占位（"pictures in the ..." / "It 's …"）
    if REJECT_ELLIPSIS and ("…" in t or "..." in t):
        return False
    # 句子残片：以小写字母开头（"in the museum." / "pictures in the ..."）
    if REJECT_LOWERCASE and t[0].islower():
        return False
    # 残片：单词太少 **且不像完整句子** —— 小学课文大量 2~3 词短句
    #（"Nice to meet you."），一刀切按词数拒会把课文砍掉三成。
    if PRIMARY_MIN_WORDS and len(t.split()) < PRIMARY_MIN_WORDS \
            and not re.search(r"[.!?][\"']?$", t):
        return False
    sents = [s for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    if len(sents) >= 2 and all(s.rstrip().endswith("?") for s in sents):
        return False
    return True


def _is_activity_head(l):
    """这一行是「活动区标题」（"1. Let's read" / "2 Look and say"）"""
    return l["size"] >= 16 and bool(SECTION_RE.match(l["text"].strip()))


def _is_unit_cover(l, page_w):
    """这一行是「单元扉页」的大标题（"UNIT 1"）→ 硬边界

    **坑**：课本每页外侧也有个单元标记（"UNIT 1"，32pt，贴着页面右边缘），
    那是页眉不是扉页 → 用 x 位置区分（扉页在页面中间，标记在最右侧）。
    """
    t = l["text"].strip()
    if l["size"] < 24 or not re.match(r"^unit\s*\d+$", t, re.I):
        return False
    return l["x"] < 0.6 * page_w


# 小学的**结构化标题**（能当切分点的只有这几类）
#   "Lesson 3 …"      一课
#   "Try yourself"    单元复习页
#   "Review 1"        期末复习页
#   "Read and enjoy"  复习页里的故事标题
# 其余 >=20pt 的行**不能**当切分点 —— 实测早先按「任意 >=20pt」切，
# 切出了一堆碎片篇（"Task 1" / "I've got ___★" / "Country Life" /
# "He doesn't do it"），每篇只有 2~4 段垃圾。
STRUCTURED_TITLE_RE = re.compile(
    r"^(lesson\s*\d+|try yoursel|review\s*\d*|read and enjoy)\b", re.I)


def _primary_segments(pages, widths):
    """把全书按「结构化标题行」切成篇（跨页自然延续）

    切分点 = 结构化标题行（"Lesson N …" / "Try yourself" / "Review N" /
    "Read and enjoy"），但排除：
    - 页面外侧的元素（x < 0 / x > 页宽）—— 那是跨页印刷的溢出块
    - 单元扉页（"UNIT 1"）—— 它只当**边界**，用来切断上一课
    - **连页重复的页眉**（"Review 1" 在 p49~p52 每页都印一遍 → 只在第一页切）
    """
    segs = []
    cur_lines = []
    cur_title = None
    cur_head = None
    cur_page = 0
    prev_struct = []          # 上一页的结构化标题（判「页眉重复」用）
    for pno, lines in enumerate(pages):
        w = widths[pno]
        # 课名块（"Lesson 1" 右侧的大字）不是切分点，要排除
        skip = set()
        for l in lines:
            if l["size"] < 16:
                continue
            if re.match(r"^lesson\s*\d+", l["text"].strip(), re.I):
                for e in _lesson_extra_lines(lines, l):
                    skip.add(id(e))
        heads = []
        struct = []
        raw_struct = []
        for l in lines:
            t = l["text"].strip()
            if l["size"] < 16 or not t or is_chinese_line(t):
                continue
            if l["x"] < 0 or l["x"] > w:
                continue
            if id(l) in skip:
                continue
            if _is_unit_cover(l, w):
                heads.append((l, "cover"))
                continue
            if re.match(r"^unit\s*\d+$", t, re.I):
                continue        # 页面外侧的单元标记，不是课文标题
            if not STRUCTURED_TITLE_RE.match(t):
                continue        # 不是结构化标题 → 不切
            raw_struct.append((t, l["x"], l["y"]))
            # 连页重复的页眉 → 不切
            if any(ptext == t and abs(py - l["y"]) <= 4 and abs(px - l["x"]) <= 15
                   for (ptext, px, py) in prev_struct):
                continue
            struct.append((t, l["x"], l["y"]))
            heads.append((l, "title"))
        prev_struct = raw_struct
        heads.sort(key=lambda h: h[0]["y"])
        hi = 0
        for l in sorted(lines, key=lambda x: (x["y"], x["x"])):
            while hi < len(heads) and heads[hi][0]["y"] < l["y"] - 1:
                h, kind = heads[hi]
                hi += 1
                segs.append({"title": cur_title, "lines": cur_lines,
                             "page": cur_page, "head": cur_head})
                cur_lines = []
                cur_title = None if kind == "cover" else h
                cur_head = h if kind != "cover" else None
                cur_page = pno
            l["_pno"] = pno
            cur_lines.append(l)
            if cur_page is None:
                cur_page = pno
        while hi < len(heads):
            h, kind = heads[hi]
            hi += 1
            segs.append({"title": cur_title, "lines": cur_lines,
                         "page": cur_page, "head": cur_head})
            cur_lines = []
            cur_title = None if kind == "cover" else h
            cur_head = h if kind != "cover" else None
            cur_page = pno
    segs.append({"title": cur_title, "lines": cur_lines,
                 "page": cur_page, "head": cur_head})
    return segs


def _seg_title(seg, page_lines, page_w):
    """课文段的标题

    优先级：
    1. 段首的 "Lesson N + 课名"
    2. 段内的 18pt 小标题（"The Story of Nian" / "Read and enjoy"）
    3. 标题行本身（"Try yourself"）

    **课名只能在同一页里找**：`_lesson_extra_lines` 找的是「Lesson N 右边
    那个更大字号的块」，如果不限定页，跨页的同高度行会被误当成课名
    （五下 "Lesson 4" 曾被拼成 "Lesson 4 Try yourself Again, please"）。
    """
    head = seg.get("head")
    lines = seg["lines"]
    if head is None:
        return None
    t = head["text"].strip()
    if re.match(r"^lesson\s*\d+", t, re.I):
        tt = _lesson_title(page_lines, head)
        if tt:
            return tt
    # 复习页：优先用段内的课文小标题
    # 候选必须是**独立标题行**，不能是活动区的续行：
    #   "1. Re a d, then group the words with" / "the s a me sounds"
    #   → 续行首字母小写，且上一行没结句
    #
    # **段是跨页的**：排序必须按 (页号, y, x)，只按 y 排会把上一页的行
    # 插进当前页的行中间，「上一行」判据全乱 → 真标题被当成续行丢掉
    # （"Lovely animals" / "Nice to meet you!" 全是这样丢的）。
    hp = head.get("_pno", seg["page"])
    ordered = sorted([x for x in lines if x.get("_pno", seg["page"]) == hp],
                      key=lambda x: (x["y"], x["x"]))
    for idx, l in enumerate(ordered):
        if l["size"] >= 15 and not _is_activity_head(l) and not _is_unit_cover(l, page_w):
            tt = l["text"].strip()
            if len(tt) < 3 or tt[0].islower():
                continue
            if STRUCT_TITLE_RE.match(tt):
                continue        # "Read and enjoy" / "Try yourself" / "Review 1" 这类结构标题
            if idx > 0:
                prev = ordered[idx - 1]["text"].strip()
                if (l["y"] - ordered[idx - 1]["y"]) <= ordered[idx - 1]["size"] * 1.8 \
                        and not ends_sentence(prev):
                    continue
            if (tt and not SECTION_RE.match(tt) and tt != t
                    and not _is_instr_title(tt) and not is_chinese_line(tt)):
                return tt
    return t


# 明显是「练习指令」的小标题，不能当课文标题
INSTR_TITLE_RE = re.compile(
    r"^(task\s*\d+|step\s*\d+|part\s*[a-z0-9]+|activity\s*\d*|"
    r"exercise\s*\d*|\(\d+\))\b", re.I)

# 结构性标题：只是活动区/页面的名字，不是课文标题
STRUCT_TITLE_RE = re.compile(
    r"^(read\s+and\s+(enjoy|read|write)|try\s+yourself(\s+again)?|"
    r"review\s*\d*|check\s+it|let'?s\s+read|talk\s+together|"
    r"act\s+out|listen\s+and\s+\w+|look\s+and\s+\w+|read\s+and\s+\w+)\b", re.I)


def _is_instr_title(t):
    return bool(INSTR_TITLE_RE.match(t.strip()))


def extract_primary(doc, book):
    """小学：**一课一篇课文**

    切篇依据是**标题行**（"Lesson 1 …" / "Try yourself"），不是活动区 ——
    小学一课的课文散在好几个活动区里（对话在 "1 Listen and say"，
    表演在 "3 Act out"，韵文在 "2 Talk together"），
    只取编号 1 会砍掉六成内容（实测小学 6 册从 9.2 万字符掉到 3.7 万）。

    练习内容靠**段落级判据**剔除：
    - 单字母说话人（"A: …" / "B: …"）→ 练习对话（课文对话是人名："Li Ming: …"）
    - 填空线 / 编号题 / 全问句 → 已有 is_primary_para
    - 单词表、表格行 → 没有句末标点，ends_sentence 拦掉
    """
    bf, bsize = body_font_profile(doc)
    if not bf:
        return []
    pages = [collect_lines(doc[pno]) for pno in range(len(doc))]
    widths = [doc[pno].rect.width for pno in range(len(doc))]

    # 每页属于哪个单元（页脚 "Unit 1" + 页码 "3" 是**两个 span** → span 级读）
    page_unit = []
    cur_unit = None
    for lines in pages:
        for l in lines:
            u = line_unit_label(l)
            if u:
                cur_unit = u
        page_unit.append(cur_unit)

    # 每页的课标题（"Lesson 1 What did you do in the holidays?"）
    lesson_by_page = {}
    for pno, y, title in _lesson_marks(pages):
        lesson_by_page.setdefault(pno, title)

    # 第一课的页码：**前面的目录页**（"Unit 1 Winter Holidays / 2" 那种）
    # 里也有 16pt 的 "Review" / "Unit N …" 行 → 会当成结构化标题切出垃圾篇
    first_lesson = None
    for pno, lines in enumerate(pages):
        for l in lines:
            if re.match(r"^lesson\s*\d+", l["text"].strip(), re.I) and l["size"] >= 16:
                first_lesson = pno
                break
        if first_lesson is not None:
            break

    articles = []
    for seg in _primary_segments(pages, widths):
        if seg["title"] is None:
            continue
        if first_lesson is not None and seg["page"] < first_lesson:
            continue
        title = _seg_title(seg, pages[seg["page"]], widths[seg["page"]])
        if not title:
            continue
        paras = []
        by_page = {}
        for l in seg["lines"]:
            by_page.setdefault(l["_pno"], []).append(l)
        for pno in sorted(by_page):
            page = doc[pno]
            h = page.rect.height
            w = page.rect.width
            body = []
            for l in by_page[pno]:
                if l["font"] != bf or abs(l["size"] - bsize) > 2:
                    continue
                if l["bold_ratio"] > 0.5:
                    continue
                if is_chinese_line(l["text"]):
                    continue
                if line_unit_label(l):
                    continue
                if re.match(r"^\s*(unit\s*\d+|\d{1,3})\s*$", l["text"], re.I):
                    continue
                if l["y"] < 45 or l["y"] > h - 45:
                    continue
                if l["x"] < 0 or l["x"] > w:
                    continue      # 跨页出血的标题块（x 为负）
                body.append(l)
            if not body:
                continue
            # **按页分块**：不同页的 y 会撞车，混在一起会把两页的段落交错
            for block in split_blocks(body):
                for t in read_block(block):
                    t = t.strip()
                    if not t or len(t) < 2:
                        continue
                    if not ends_sentence(t):
                        continue          # 短语表（"shaking hands"）
                    if t.startswith(("●", "•", "·")):
                        continue
                    if len(t) > 600:
                        continue
                    if not is_primary_para(t):
                        continue
                    paras.append(t)
        if len(paras) < 2:
            continue
        articles.append({
            "title": title,
            "unit": page_unit[seg["page"]],
            "paragraphs": paras,
            "page": seg["page"] + 1,
        })
    return articles




# ================================================================ 初中
# 栏目标题（不能当课文标题）
SECTION_NAMES_RE = re.compile(
    r"^(\*\s*)?(reading plus|grammar|grammar focus|vocabulary in use|self check|"
    r"big question|useful language|function and structure|reading and writing|"
    r"writing|speaking|listening|pronunciation|section\s+[a-d]\b|"
    r"project|review|words in each unit|words and chunks|after you read|"
    r"before you read|fun time|culture corner|check it out|computer time)",
    re.I,
)


# 句号后紧跟小写 → 段落被拆乱了（"every Teng Fei's grandpa loves sport. week."）
# 缩写要放行："Mr. Smith" / "e.g. this"
ABBREV = {"mr", "mrs", "ms", "dr", "st", "jr", "sr", "prof", "etc",
          "eg", "ie", "no", "vol", "fig", "vs", "inc", "ltd", "co",
          "am", "pm", "approx", "dept", "est"}


def _dot_then_lower(text):
    for m in re.finditer(r"\b([A-Za-z]+)\.\s+([a-z])", text):
        if m.group(1).lower().strip(".") in ABBREV:
            continue
        return True
    return False


def passage_fail_reason(text, speakers=0):
    """这一段**不是**课文时，返回原因标签；是课文则返回 None

    拆出原因是为了能定位「为什么这段被丢了」，不用靠猜。
    """
    t = text.strip()
    if len(t) < 80:
        return "too_short"
    if len(NUMBERED_ITEM_RE.findall(t)) >= 2:
        return "numbered_item"
    if SPEAKER_TAG_RE.search(t):
        return "speaker_tag"
    # 朗读练习对话："I'm good / fine" —— 斜杠是换行选项。
    # 只有**多人对话 + 斜杠**才是练习；课文里也有 "in front of / on the wall"
    # 这种介词备选（单说话人），那种要留着。
    if speakers >= 2 and re.search(r"\s/\s", t):
        return "dialog_slash"
    if re.match(r"^\d+\s*[.、]\s", t):
        return "unit_goal"
    if BRACKET_VERB_RE.search(t):
        return "bracket_verb"
    if BLANK_RE.search(t):
        return "blank_line"
    if ACT_ID_RE.search(t):
        return "act_id"
    if re.search(r"\bParagraph\s+\d", t, re.I):
        return "paragraph_match"
    if len(re.findall(r"(?:^|\s)([A-D])\.\s+\S", t)) >= 2:
        return "option_list"
    if len(TABLE_FIELD_RE.findall(t)) - speakers >= 3:
        return "table_row"
    if t.count("√") >= 1 or t.count("×") >= 1:
        return "judge_item"
    # 表格里的两栏被并到一行：问句后面直接跟小写（"? there will be"）
    if re.search(r"\?[a-z]", t):
        return "question_lower"
    # 句号后紧跟小写 → 段落被拆乱了（填空后重新排序）
    if _dot_then_lower(t):
        return "dot_then_lower"
    # 单词表 / 词条栏（没有句末标点 + 没有逗号 + 一串短词）
    # → 它不是课文，别让它跟下一段粘起来
    if (not ends_sentence(t) and "," not in t
            and len(re.findall(r"[A-Za-z]{2,}", t)) >= 8):
        return "word_list"
    # 全是问句的讨论题（"What can similarities bring to a friendship? …?"）
    sents = [s for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    if len(sents) >= 2 and all(s.rstrip().endswith("?") for s in sents):
        return "all_questions"
    # 练习对话：短句占多数（"Wake up! Wake up! I don't want to get up. …"）
    if len(sents) >= 3:
        short = [s for s in sents if len(s) < 22]
        if len(short) >= 3 and len(short) / len(sents) >= 0.6:
            return "short_dialog"
    return None


def is_passage_para(text, speakers=0):
    """这一段是课文（叙事/说明），而不是题目 / 练习要点 / 练习对话？

    `speakers` = 这一段里出现的说话人标签个数（"Alice:" / "Lin Hui:"）。
    表格字段（"Name:" / "Age:"）和说话人标签长得一样，靠字体区分：
    说话人标签是 DIN-Medium 单独排的，表格字段跟正文同字体。
    """
    return passage_fail_reason(text, speakers) is None


def _is_true_two_column(lines, page_right):
    """判断这页是不是「真双栏排版」

    真双栏：左栏所有行都很窄（右边界明显小于页面右边界），且右栏从页面顶部开始。
    绕排插图：文字会先窄后宽，或右栏从页面中部才开始 → 不是双栏，按 y 顺序读。
    """
    if len(lines) < 8:
        return False
    xs = sorted(l["x"] for l in lines)
    gaps = [(xs[i + 1] - xs[i], xs[i]) for i in range(len(xs) - 1)]
    if not gaps:
        return False
    maxgap, xat = max(gaps)
    if maxgap <= 60:
        return False
    left = [l for l in lines if l["x"] <= xat]
    right = [l for l in lines if l["x"] > xat]
    if len(left) < 4 or len(right) < 4:
        return False
    # 左栏必须是窄带（行右边界离页面右边界很远）
    if max(l["x1"] for l in left) > page_right - 60:
        return False
    # 右栏必须从页面顶部就开始
    text_top = min(l["y"] for l in lines)
    if min(l["y"] for l in right) > text_top + 40:
        return False
    return True


def merge_columns(lines, gap_ratio=1.6):
    """把一页的正文行拼成段落

    - 真双栏 → 左栏读完再读右栏
    - 其余（绕排插图、单栏）→ 按 y 顺序读
    段落边界 = 行距突然变大（> 字号 × gap_ratio）
    """
    if not lines:
        return []
    page_right = max(l["x1"] for l in lines)
    if _is_true_two_column(lines, page_right):
        xs = sorted(l["x"] for l in lines)
        gaps = [(xs[i + 1] - xs[i], xs[i]) for i in range(len(xs) - 1)]
        _maxgap, xat = max(gaps)
        cols = [[l for l in lines if l["x"] <= xat],
                [l for l in lines if l["x"] > xat]]
    else:
        cols = [lines]

    paras = []
    for col in cols:
        col = sorted(col, key=lambda l: (l["y"], l["x"]))
        cur = []
        cur_y = None
        cur_blank = False
        cur_fonts = {}
        cur_speakers = 0
        prev_y = None
        for l in col:
            if prev_y is not None and (l["y"] - prev_y) > l["size"] * gap_ratio and cur:
                paras.append({"text": " ".join(cur), "y": cur_y, "blank": cur_blank,
                              "fonts": cur_fonts, "speakers": cur_speakers})
                cur = []
                cur_y = None
                cur_blank = False
                cur_fonts = {}
                cur_speakers = 0
            if cur_y is None:
                cur_y = l["y"]
            cur.append(l["text"])
            cur_blank = cur_blank or bool(l.get("blank"))
            cur_speakers += int(l.get("speakers") or 0)
            for f in (l.get("fonts") or [l.get("font", "")]):
                cur_fonts[f] = cur_fonts.get(f, 0) + len(l["text"])
            prev_y = l["y"]
        if cur:
            paras.append({"text": " ".join(cur), "y": cur_y, "blank": cur_blank,
                          "fonts": cur_fonts, "speakers": cur_speakers})
    return paras


def merge_continued(paras):
    """上一段最后一句没有结句 → 它被拆开了，并到下一段前面"""
    out = []
    for p in paras:
        if out and not ends_sentence(out[-1]["text"]):
            out[-1]["text"] = out[-1]["text"].rstrip() + " " + p["text"]
            out[-1]["blank"] = out[-1].get("blank") or p.get("blank")
            continue
        out.append(p)
    return out


def page_footer_unit(lines, page_h):
    """从页脚里找单元号

    页脚的 "UNIT 1" 只有 10pt，**不能按字号过滤**（早先按 size>=14 找，
    结果前 90 多页正文全被跳过）。
    """
    for l in lines:
        if l["y"] < page_h - 62:
            continue
        m = re.match(r"^UNIT\s*(\d+)$", l["text"].strip(), re.I)
        if m:
            return "Unit %s" % m.group(1)
    return None


# 人教版（八下）把 UNIT 放在**页眉**（y≈46），页脚只有页码
HEADER_APPENDIX_MARKERS = re.compile(
    r"^(contents|vocabulary index|irregular verbs|word list|"
    r"list of the main characters|notes on the text|tapescripts|"
    r"words and expressions in each unit|vocabulary from primary school)\b", re.I)

# 正文里也有 "Grammar" 这个**栏目标题**（18pt），
# 而八下附录页眉的 "Grammar" 只有 12pt → 用字号区分，不能一刀切。
HEADER_APPENDIX_GRAMMAR_RE = re.compile(r"^grammar$", re.I)

# 附录都在**书末** → 这些标记一旦出现，后面全是附录
APPENDIX_TAIL_MARKERS = re.compile(
    r"^(irregular verbs|word list|list of the main characters|"
    r"notes on the text|tapescripts|words and expressions in each unit|"
    r"vocabulary from primary school|vocabulary index)$", re.I)


def is_appendix_header(l):
    """这一行是附录/索引的页眉标记"""
    t = l["text"].strip()
    if HEADER_APPENDIX_MARKERS.match(t):
        return True
    if l["size"] <= 13 and HEADER_APPENDIX_GRAMMAR_RE.match(t):
        return True
    return False



def page_header_unit(lines):
    """页眉里的 "UNIT n"（人教版八下用这个）"""
    for l in lines:
        if l["y"] > 70:
            continue
        m = re.match(r"^UNIT\s*(\d+)$", l["text"].strip(), re.I)
        if m:
            return "Unit %s" % m.group(1)
    return None


def page_unit(lines, page_h):
    """这一页属于哪个单元：页脚优先（莱芜版），页眉兜底（人教版）"""
    return page_footer_unit(lines, page_h) or page_header_unit(lines)


def is_toc_page(lines):
    """目录页 / 附录索引页 → 不该出课文

    人教版八下把 "Contents" / "Vocabulary Index" / "Irregular Verbs" 放在页眉，
    不在页脚 → 只能整页扫。

    **必须只扫页眉区**（y≤92）：莱芜版 Reading Plus 区的页脚就写着
    "Reading Plus"（奇数页带星号、偶数页不带），整页扫会把那些页全判成目录页。
    """
    for l in lines:
        if l["y"] > 92:
            continue
        if is_appendix_header(l):
            return True
    return False


def starts_appendix_tail(lines):
    """这一页是不是**附录的起点**（附录都在书末 → 后面全丢）"""
    for l in lines:
        if l["y"] > 92:
            continue
        t = l["text"].strip()
        if APPENDIX_TAIL_MARKERS.match(t):
            return True
        if l["size"] <= 13 and HEADER_APPENDIX_GRAMMAR_RE.match(t):
            return True
    return False



# 附录页（附录里没有课文，只有语法表/词汇表/听力原文）
# 注意：**不能**匹配 "Reading Plus 85" 这种——莱芜版每一页的页脚都是
# "Reading Plus <页码>"，早先写成 `reading plus\s*/?\s*\d` 会把
# Reading Plus 拓展区的**偶数页整页丢掉**（课文全丢）。
APPENDIX_FOOTERS = re.compile(
    r"(grammar|vocabulary|pronunciation|irregular verbs|listening scripts|"
    r"vocabulary a)", re.I)


def is_appendix_page(lines, page_h):
    """这一页是附录（语法表/词汇表/听力原文）→ 不该出课文"""
    for l in lines:
        if l["y"] < page_h - 62:
            continue
        if APPENDIX_FOOTERS.search(l["text"]):
            return True
    return False


# --- 莱芜版：正文课文**没有独立标题行**，只有 Section 话题行 -------------
# 每个 Section（A/B）开头有一个 18~20pt 的 MyriadPro-Bold 话题行
# （"How do we get to know each other?" / "What do you like about your family?"），
# 这个话题行就是该 Section 全部课文段落的分组锚点。
TOPIC_BLOCK = {
    "grammar focus", "over to you", "pronunciation", "project",
    "section a", "section b", "section c", "section d",
    "reading plus", "listening scripts", "vocabulary", "grammar",
    "review", "self check", "big question", "useful language",
    "words in each unit", "after you read", "before you read",
    "computer time", "fun time", "culture corner", "check it out",
    "comprehension", "writing", "listening", "speaking",
}

UNIT_LABEL_RE = re.compile(r"^unit\s*\d+$", re.I)


def _fold_groups(lines):
    """同一个标题被排版折成多行 → 合并成一条

    判据：同一 x 起点（或右对齐）+ 行距 ≤ 34pt。
    例："What do we need to know about a" + "new friend?"
    """
    groups = []
    for l in sorted(lines, key=lambda x: (x["y"], x["x"])):
        if groups:
            prev = groups[-1]
            pv = prev["lines"][-1]
            same_x = abs(l["x"] - pv["x"]) <= 6 or abs(l["x1"] - pv["x1"]) <= 6
            gap_ok = 0 < (l["y"] - pv["y"]) <= 34
            if same_x and gap_ok:
                prev["lines"].append(l)
                continue
        groups.append({"lines": [l]})
    out = []
    for grp in groups:
        text = " ".join(x["text"].strip() for x in sorted(grp["lines"], key=lambda x: x["y"]))
        out.append((grp["lines"][0]["y"], text))
    return out


def junior_title_marks(lines):
    """真标题行（课文名）—— 按**字体**判定，不靠字号"""
    out = []
    for l in lines:
        t = l["text"].strip()
        if not t or is_chinese_line(t):
            continue
        if l["font"] in JUNIOR_NOT_TITLE_FONTS:
            continue
        if l["font"] not in JUNIOR_TITLE_FONTS:
            continue
        # 同一个字体既能当标题也能当指令行（人教版 ArnoPro-SmbdCaption）：
        # 标题 15/20pt，指令行 13pt → 用字号再卡一道
        if l["size"] < 15:
            continue
        if len(t) < 3:
            continue
        if INSTRUCTION_PAT.match(t):
            continue
        if SECTION_NAMES_RE.match(t):
            continue
        if SPACED_CAPS_RE.match(t):
            continue        # "S E C T I O N" 这种装饰性字母
        if re.match(r"^\d\s*[a-d]$", t, re.I):
            continue
        out.append(l)
    return _fold_groups(out)


def junior_topic_marks(lines):
    """Section 话题行（莱芜版正文课文的分组锚点）"""
    out = []
    # 同页有 "Over to You" → 这是活动页，标题是项目名（"Guess what it is"），不是 Section 话题
    over_to_you = any(
        l["font"] == "Arial-Black" and l["text"].strip().lower() == "over to you"
        for l in lines)
    # 同页必须有 Section 大字母（Arial-Black 39pt 的 A/B）才是 Section 话题页。
    # "Project" 页（"Learn how to use a dictionary"）也是 18pt MyriadPro-Bold，
    # 但它没有大字母 —— 靠这个把它排除掉。
    has_section_letter = any(
        l["font"] == "Arial-Black" and l["size"] >= 30 for l in lines)
    if not has_section_letter:
        return []
    for l in lines:
        if l["font"] != "MyriadPro-Bold":
            continue
        if not (16 <= l["size"] <= 24):
            continue
        # Section 话题永远在页顶（y≤88）；页中间的（y>88）是栏内小标题。
        # 阈值放宽到 88：话题行经常折成两行，第二行基线在 70~80 之间
        # （"What do we need to know about a" + "new friend?"）。
        if l["y"] > 88:
            continue
        t = l["text"].strip()
        if not t or is_chinese_line(t):
            continue
        if len(t) < 4:
            continue        # 艺术字装饰（单字母）
        if t.lower() in TOPIC_BLOCK:
            continue
        if UNIT_LABEL_RE.match(t):
            continue
        if re.match(r"^\d+[a-c]?$", t):
            continue
        if over_to_you:
            continue
        out.append(l)
    return _fold_groups(out)


def reading_plus_start(lines):
    """莱芜版教材末尾的 "Reading Plus" 拓展阅读区起点（返回 y 或 None）"""
    for l in lines:
        if l["font"] in ("DIN-Bold", "DINAlternate-Bold", "ArnoPro-SmbdSmText"):
            if re.match(r"^reading\s+plus\b", l["text"].strip(), re.I):
                return l["y"]
    return None


def unit_cover_page(lines):
    """这一页是「单元封面页」→ 单元正文从这里开始

    莱芜版：单元封面用 `DINAlternate-Bold` 54pt 的大 "UNIT n"；
    人教版：页眉 `Frutiger-ExtraBlackCn` 34pt 的 "UNIT n"。

    **不能用小字号的 "Unit n"**：莱芜版 Reading Plus 拓展区每单元开头也有
    一个 18pt 的 "Unit n"（MyriadPro-Bold），用它当起点会直接跳过正文。
    """
    for l in lines:
        if l["size"] < 20:
            continue
        if UNIT_LABEL_RE.match(l["text"].strip()):
            return True
    return False


def extract_junior(doc, book):
    """初中：课文 = 阅读段落（长自然段）

    切分模型：**按分组锚点切**
    - 莱芜版正文课文没有独立标题 → 用 Section 话题行（18~20pt MyriadPro-Bold）
      当锚点，一个 Section 的全部课文段落归一篇，标题 = 话题
    - 莱芜版末尾 "Reading Plus" 拓展区 → 有真标题的按真标题切，
      没真标题的按页分组（"Reading Plus · 第N篇"）
    - 人教版八下 → 课文都有真标题（ArnoPro-SmbdCaption 15pt），按真标题切
    - 锚点**之前**的段落属于前一篇（跨页续接），**之后**的属于新一篇
    → 这样「同一篇课文跨两页」不会被切成两篇
    """
    articles = []
    pages_lines = [collect_lines(doc[pno]) for pno in range(len(doc))]

    cur_unit = None

    # ---------- 先扫全书，收集所有分组锚点 ----------
    # marks: (页号, y, 类型, key)
    #   "title" → 真标题（课文名）
    #   "topic" → Section 话题（莱芜版正文课文的锚点）
    #   "rp"    → 进入 Reading Plus 拓展区
    marks = []
    rp_mode = False
    for pno in range(len(doc)):
        lines = pages_lines[pno]
        for (y, text) in junior_title_marks(lines):
            marks.append((pno, y, "title", text))
        if not rp_mode:
            for (y, text) in junior_topic_marks(lines):
                marks.append((pno, y, "topic", text))
            ry = reading_plus_start(lines)
            if ry is not None:
                rp_mode = True
                marks.append((pno, ry, "rp", None))
    marks.sort(key=lambda m: (m[0], m[1]))

    # 正文从**第一个 Section 页**开始：前面的单元目录 / Contents / 角色表
    # 里也有 18pt 的话题行和真标题（"List of the Main Characters"），
    # 但那些页不是课文页 → 整段跳过
    start_p = 0
    for kind in ("topic", "title"):
        cand = [m[0] for m in marks if m[2] == kind]
        if cand:
            start_p = min(cand)
            break

    groups = {}      # key -> {"title","paras","page","unit"}
    order = []
    rp_seq = 0
    rp_key_cache = {}

    for pno in range(start_p, len(doc)):
        page = doc[pno]
        lines = pages_lines[pno]
        page_h = page.rect.height
        # 附录在书末 → 见到附录起点页，后面整段都是附录（词汇表/语法表/听力原文）
        if starts_appendix_tail(lines):
            break
        if is_appendix_page(lines, page_h) or is_toc_page(lines):
            continue
        u = page_unit(lines, page_h)
        if u:
            cur_unit = u

        blanks, rule_ys = page_rules(page)

        def has_blank(l):
            if l["gap"] > l["size"] * 1.5 and l["gap_punct"]:
                return True
            for by, _bx0, _bx1 in blanks:
                if l["bbox"][1] - 2 <= by <= l["bbox"][3] + 3:
                    return True
            return False

        body = []
        for l in lines:
            if is_chinese_line(l["text"]):
                continue
            if not (10 <= l["size"] <= 15):
                continue
            if l["bold_ratio"] > 0.5:
                continue          # 指令句 / 标题
            if l["text"].startswith(("●", "•", "·")):
                continue
            if re.match(r"^\s*(unit\s*\d+|review\s*\d*|\d{1,3})\s*$", l["text"], re.I):
                continue
            if l["y"] < 45 or l["y"] > page_h - 45:
                continue
            # 有填空痕迹的行**不直接丢**，而是标记出来：
            # 整段都是填空练习 → 整段都要丢，否则会剩半截残片
            l["blank"] = has_blank(l)
            body.append(l)
        if not body:
            continue

        paras = merge_columns(body)
        # 表格区：段落首行贴着表格横线 → 是表格里的问答，不是课文
        _dbg = os.environ.get("EXTRACT_DEBUG")
        if _dbg:
            print("  [p%d] body=%d paras=%d rules=%s" % (pno + 1, len(body), len(paras), rule_ys[:8]))
        paras = [p for p in paras
                 if is_passage_para(p["text"], p.get("speakers") or 0) and not p.get("blank")
                 and not any(abs(p["y"] - ry) <= 6 for ry in rule_ys)]
        if _dbg:
            print("  [p%d] after=%d" % (pno + 1, len(paras)))
        if not paras:
            continue

        # ---- 把段落分配到「锚点」分组
        for p in paras:
            hit = None
            for mp, my, mkind, mkey in marks:
                if mp > pno:
                    break
                if mp == pno and my > p["y"] + 2:
                    break
                hit = (mp, my, mkind, mkey)
            if hit is None:
                continue
            _mp, _my, mkind, mkey = hit
            if mkind == "title":
                key = ("title", mkey)
                gtitle = mkey
            elif mkind == "topic":
                key = ("topic", mkey)
                gtitle = mkey
            else:   # "rp" → Reading Plus 区且没有真标题 → 按页分组
                if pno not in rp_key_cache:
                    rp_seq += 1
                    rp_key_cache[pno] = ("rp", rp_seq)
                key = rp_key_cache[pno]
                gtitle = "Reading Plus · 第%d篇" % rp_seq

            g = groups.get(key)
            if g is None:
                g = {
                    "title": gtitle,
                    "paras": [],
                    "page": pno,
                    "unit": cur_unit,
                }
                groups[key] = g
                order.append(key)
            g["paras"].append(p["text"])

    for key in order:
        a = groups[key]
        if not a["paras"]:
            continue
        paras = merge_continued([{"text": t} for t in a["paras"]])
        if not paras:
            continue
        articles.append({
            "title": a["title"],
            "unit": a["unit"],
            "paragraphs": [p["text"] for p in paras],
            "page": a["page"] + 1,
        })

    out = []
    for a in articles:
        out.append({
            "title": a["title"],
            "unit": a["unit"],
            "paragraphs": a["paragraphs"],
            "page": a["page"],
        })
    return out


# ---------------------------------------------------------------- 落盘
def to_article(a):
    title = repair_text(a["title"]).strip()
    if a.get("unit") and not title.startswith(a["unit"]):
        title = "%s · %s" % (a["unit"], title)
    paras = [repair_text(p).strip() for p in a["paragraphs"]]
    paras = [p for p in paras if p]
    text = "\n\n".join(paras)
    return {
        "id": 0,
        "title": title,
        "titleTranslate": "",
        "text": text,
        "textTranslate": "",
        "audioSrc": None,
        "lrcPosition": [],
        "question": None,
        "nameList": None,
        "quote": None,
        "userId": None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只处理某个 pdf 文件名")
    ap.add_argument("--dump", action="store_true", help="只打印，不写文件")
    ap.add_argument("--full", action="store_true", help="dump 时打印每篇全文")
    args = ap.parse_args()

    books = BOOKS
    if args.only:
        books = [b for b in BOOKS if args.only in b["file"]]
        if not books:
            print("没找到册子：%s" % args.only)
            sys.exit(1)

    results = {}
    for b in books:
        path = os.path.join(PDF_DIR, b["file"])
        if not os.path.exists(path):
            print("[SKIP] %s 不存在" % b["file"])
            continue
        doc = pymupdf.open(path)
        try:
            if b["stage"] == "primary":
                arts = extract_primary(doc, b)
            else:
                arts = extract_junior(doc, b)
        finally:
            doc.close()
        arts = [a for a in arts if sum(len(p) for p in a["paragraphs"]) >= 40]
        results[b["key"]] = arts
        chars = sum(len(p) for a in arts for p in a["paragraphs"])
        print("[OK] %-28s 课文 %3d 篇 / %6d 字符" % (b["name"], len(arts), chars))
        sys.stdout.flush()

    if args.dump:
        for key, arts in results.items():
            print("\n" + "=" * 76)
            print(key)
            for a in arts:
                print("-" * 70)
                print("标题:", a["title"], "| 页:", a["page"], "| 段数:", len(a["paragraphs"]))
                if args.full:
                    for p in a["paragraphs"]:
                        print("   ", p)
                else:
                    for p in a["paragraphs"][:4]:
                        print("   ", p[:150])
        return

    os.makedirs(ARTICLE_DIR, exist_ok=True)
    list_data = []
    if os.path.exists(LIST_FILE):
        with io.open(LIST_FILE, encoding="utf-8") as f:
            list_data = json.load(f)

    next_book_id = max([int(x.get("id", 0)) for x in list_data] + [0]) + 1
    next_art_id = 10000
    existing_urls = {x.get("url") for x in list_data}

    for b in books:
        key = b["key"]
        if key not in results:
            continue
        arts = results[key]
        if not arts:
            continue
        url = "%s.json" % key
        out = []
        for a in arts:
            art = to_article(a)
            art["id"] = next_art_id
            next_art_id += 1
            out.append(art)
        with io.open(os.path.join(ARTICLE_DIR, url), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        if url not in existing_urls:
            list_data.append({
                "id": next_book_id,
                "enName": key.lower(),
                "name": b["name"],
                "description": "山东莱芜五四制英语课本 %s 的课文精选，可逐句跟打。" % b["grade"],
                "categoryId": 4,
                "url": url,
                "length": len(out),
                "language": "en",
                "translateLanguage": "zh_CN",
                "version": 1,
                "type": "article",
                "isDefault": False,
                "recommended": False,
                "userId": "00000000-0000-0000-0000-000000000001",
                "createdAt": "2026-11-21 00:00:00.000000",
                "updatedAt": "2026-11-21 00:00:00.000000",
                "cover": None,
                "hidden": False,
                "category": "文章学习",
                "tags": ["莱芜五四制", "课本课文"],
            })
            next_book_id += 1
        else:
            # 已有条目：**必须同步 length**，否则重跑提取后书单显示的篇数
            # 跟真实文件对不上（前端按 length 展示）
            hit = next(x for x in list_data if x.get("url") == url)
            hit["length"] = len(out)
            hit["name"] = b["name"]
            hit["description"] = "山东莱芜五四制英语课本 %s 的课文精选，可逐句跟打。" % b["grade"]
    with io.open(LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(list_data, f, ensure_ascii=False, indent=2)
    print("\n写完：%s + %s" % (ARTICLE_DIR, LIST_FILE))


if __name__ == "__main__":
    main()
