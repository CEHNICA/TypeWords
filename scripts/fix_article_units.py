#!/usr/bin/env python3
"""用课本 PDF 里的 Unit 标记，反查每篇课文的真实 unit，修正标题前缀。

思路（v5）
==========
**定位**（先解决「找错页」，页号错 unit 必错）
  1. 行文本直接复用原提取器的 collect_lines + clean_text ——
     这两样就是当初灌进 article json 的原文（连断词修复都一致），
     所以 PDF 行和 json 行的 token 序列天然对齐。
     自己另起一套切法必然对不齐（小学册 37 篇里 35 篇定位失败就是这么来的）。
  2. 全书拼成一条**全局 token 流**（token = 归一化实词，标点丢弃）。
     PDF 排版折行不打断 token 连续性，所以「json → token 流定位」能跨行匹配。
  3. **优先用标题当锚点**（标题在 PDF 里是完整一整行，最可靠）；
     小学课文是对话体，正文首句在 json 里被拆成 'Hello!' / \"I'm Li Ming.\" 两行，
     token 不连续，只能当兜底。
  4. 锚点取**全文最稀有的词**（句首多是 'The'/'What' 这种高频词，拿它当锚会全撞前几页）。
  5. 标题重复很常见（'Again, please' / 'Lesson 4 Again, please'），
     所以按文章顺序**只往后找**（pos > 上一篇的位置），才知道是哪个单元的那一篇。

**unit 判定**（解决「页号对但 unit 错」）
  6. 每页收集所有 unit「转换点」[(y, unit)]：span 级匹配（line_unit_label），
     避免页脚 '84 UNIT 7' 被读成 'Unit 847'。
  7. 页内 unit 转换点按 y 排序；文章在 (page, y) 处的 unit = **y 之前最后一个转换点**。
  8. 若该页在 y 之前没有任何转换点 → 用**跨页继承链**：
     上一页末尾生效的 unit 延续过来。
     （例：九上 p158 'It's a Long Way' 是 Unit 11 的 Poem 2，
       该页没有 unit 标记，早先版本错误回退到页脚继承 → 判成 Unit 1。）

**区域**（main / Reading Plus）
  9. 页面文本含 'Reading Plus' → 阅读拓展区。拓展区的 unit 号是**重排**过的
     （拓展 Unit 1 对应正文的 Unit 1，但拓展区从 Unit 1 重新开始），
     所以标题要标出 'Reading Plus'，否则跟正文同号会混。

用法：
  py -3 scripts/fix_article_units.py                     # 只出报告
  py -3 scripts/fix_article_units.py --add-missing       # 报告里也算「缺前缀」
  py -3 scripts/fix_article_units.py --apply             # 写盘（只改「前缀错」）
  py -3 scripts/fix_article_units.py --apply --add-missing
  py -3 scripts/fix_article_units.py --pages LWCZ_9_1    # 只跑某册
"""
import os
import re
import json
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 课本 PDF 所在目录（本机私有路径不入库）
#   env TW_TEXTBOOK_PDF_DIR → data/local_paths.json → <repo>/课本PDF
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from local_paths import resolve_pdf_dir  # noqa: E402
PDF_DIR = resolve_pdf_dir()
ART_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")

BOOKS = [
    ("LWXX_3_1", "小学五四-三年级上册.pdf"),
    ("LWXX_3_2", "小学五四-三年级下册.pdf"),
    ("LWXX_4_1", "小学五四-四年级上册.pdf"),
    ("LWXX_4_2", "小学五四-四年级下册.pdf"),
    ("LWXX_5_1", "小学五四-五年级上册.pdf"),
    ("LWXX_5_2", "小学五四-五年级下册.pdf"),
    ("LWCZ_6_1", "初中五四-六年级上册.pdf"),
    ("LWCZ_6_2", "初中五四-六年级下册.pdf"),
    ("LWCZ_7_1", "初中五四-七年级上册.pdf"),
    ("LWCZ_7_2", "初中五四-七年级下册.pdf"),
    ("LWCZ_8_1", "初中五四-八年级上册.pdf"),
    ("LWCZ_8_2", "初中五四-八年级下册.pdf"),
    ("LWCZ_9_1", "初中五四-九年级全一册.pdf"),
]

TITLE_PREFIX_RE = re.compile(r"^(?:Unit\s*\d+\s*·\s*)+", re.I)
READING_PLUS_RE = re.compile(r"reading\s*plus", re.I)
MATCH_LEVELS = (25, 15, 8)

_TTB = None


def load_extractor():
    """加载原提取器（复用它的行切分 / unit 标记口径）。"""
    global _TTB
    if _TTB is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ttb_extract", os.path.join(ROOT, "scripts", "extract-textbook-articles.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.path.pop(0)
        _TTB = mod
    return _TTB


def norm_tok(t):
    """token 归一化：只留小写字母数字。标点/引号 → 空串。"""
    return re.sub(r"[^a-z0-9]", "", t.lower())


def unit_of(text):
    """从 'Unit 3' 这类文本里取数字。"""
    m = re.search(r"(\d+)", text or "")
    return int(m.group(1)) if m else None


def detect_unit_label(ln, ttb, page_h):
    """从一行里找 'Unit N'，返回 'Unit N' 或 None。

    三个坑：
    1. 页脚 '16 UNIT 2' 是**两个 span**，整行正则会读成 'Unit 162' → 必须 span 级
       （原提取器的 line_unit_label 已经处理了这个）。
    2. 九上 p143 的单元扉页是**单个 span 'Unit 1Unit 1'**（PDF 双层文本叠加），
       span 级正则 `^unit\s*(\d+)$` 匹配不上 → 放宽成前缀匹配。
    3. 目录页里也有 'Unit 1  ...... 5'（10pt 正文），会污染跨页继承链
       → 只认「字号 >= 15」或「贴页脚」的行。
    """
    lab = ttb.line_unit_label(ln)
    if lab:
        return lab
    if ln.get("size", 0) >= 15 or ln.get("y", 0) >= page_h - 70:
        t = (ln["text"] or "").strip()
        if len(t) <= 24:
            m = re.match(r"^\*?\s*UNIT\s*(\d+)", t, re.I)
            if m:
                return "Unit " + m.group(1)
        for s in (ln.get("spans") or []):
            st = (s.get("text") or "").strip()
            if len(st) <= 20:
                m = re.match(r"^\*?\s*UNIT\s*(\d+)", st, re.I)
                if m:
                    return "Unit " + m.group(1)
    return None


class Book:
    """一本课本的解析结果。"""

    def __init__(self, pdfpath, log):
        import pymupdf
        ttb = load_extractor()
        self.ttb = ttb
        self.doc = pymupdf.open(pdfpath)
        n = self.doc.page_count
        self.tokens = []        # 全局 token 流：(normtok, page, y, x)
        self.page_trans = []    # 每页的 unit 转换点 [(y, unit)]，按 y 升序
        self.page_zone = []     # 每页的区域：'main' / 'rp'
        self.page_carry = []    # 每页「顶部生效」的 unit（跨页继承链）

        carry = None
        zone = "main"
        for p in range(n):
            page = self.doc[p]
            ph = page.rect.height
            lines = ttb.collect_lines(page)
            trans = []
            for ln in lines:
                lab = detect_unit_label(ln, ttb, ph)
                if lab:
                    u = unit_of(lab)
                    if u is not None:
                        trans.append((round(ln["y"], 1), u))
            trans.sort()
            self.page_trans.append(trans)

            # 区域：只有**大字号标题**级的 'Reading Plus' 才算区域起点。
            # 目录页里那条 '*Reading Plus p.133' 是 10pt 正文，早先版本拿它当起点，
            # 结果整本书从第 8 页起全被判成拓展区。
            for ln in lines:
                if (ln.get("size", 0) >= 18 and ln.get("y", 0) <= 120
                        and READING_PLUS_RE.search(ln["text"] or "")):
                    zone = "rp"
                    break
            self.page_zone.append(zone)

            self.page_carry.append(carry)
            for (_y, u) in trans:
                carry = u

            for ln in lines:
                txt = ttb.clean_text(ln["text"])
                for w in re.findall(r"[A-Za-z0-9']+", txt):
                    nt = norm_tok(w)
                    if nt:
                        self.tokens.append((nt, p, round(ln["y"], 1), round(ln["x"], 1)))
            if p % 40 == 0:
                log(f"    ... {p}/{n}")

        self.index = {}
        for i, (nt, p, y, x) in enumerate(self.tokens):
            self.index.setdefault(nt, []).append(i)

    def find(self, snippet_tokens, after_pos=-1):
        """在全局 token 流里定位，返回候选 [(page, y, level, pos)]，按 pos 升序。"""
        toks = [t for t in snippet_tokens if t]
        if len(toks) < 3:
            return []
        levels = [L for L in MATCH_LEVELS if L <= len(toks)] or [len(toks)]
        for level in levels:
            q = toks[:level]
            anchor = min(range(len(q)), key=lambda j: len(self.index.get(q[j], ())))
            out = []
            for pos in self.index.get(q[anchor], ())[:800]:
                if pos <= after_pos:
                    continue
                if self._match_around(q, anchor, pos):
                    nt, p, y, x = self.tokens[pos]
                    out.append((p, y, level, pos))
            if out:
                out.sort(key=lambda r: r[3])
                return out
        return []

    def _match_around(self, q, anchor, pos):
        """以 tokens[pos] 对应 q[anchor] 为中心，**严格相邻**核对整段 q。

        严格相邻是故意的：模糊子序列匹配会拿 'The cat sat on the mat' 去到处乱撞，
        命中率高但页号是错的 —— 页号错 unit 就错，比定位失败还糟。
        """
        T = self.tokens
        n = len(T)
        for j in range(anchor + 1, len(q)):
            k = pos + (j - anchor)
            if k >= n or T[k][0] != q[j]:
                return False
        for j in range(anchor - 1, -1, -1):
            k = pos - (anchor - j)
            if k < 0 or T[k][0] != q[j]:
                return False
        return True

    def resolve_unit(self, page, y):
        """给定命中页和 y，解析出 unit。"""
        trans = self.page_trans[page]
        if y and y > 0:
            below = [u for (ty, u) in trans if ty <= y]
            if below:
                return below[-1], "页内标记"
        # 页内没有生效的标记 → 用跨页继承链（本页顶部生效的 unit）
        return self.page_carry[page], "跨页继承"

    def zone_of(self, page):
        return self.page_zone[page]


def title_tokens(title):
    """标题 → 归一化 token 列表（去掉 'Unit n · ' 前缀）。"""
    base = TITLE_PREFIX_RE.sub("", title or "").strip()
    ttb = load_extractor()
    base = ttb.clean_text(base)
    return [norm_tok(w) for w in re.findall(r"[A-Za-z0-9']+", base)]


def first_sentence_tokens(text):
    """课文首句 → 归一化 token 列表。"""
    t = (text or "").split("\n\n")[0].split("\n")[0].strip()
    ttb = load_extractor()
    t = ttb.clean_text(t)
    return [norm_tok(w) for w in re.findall(r"[A-Za-z0-9']+", t)]


def locate_article(bk, a, after_pos):
    """定位一篇课文。返回 (page, y, level, how, pos)"""
    cand = bk.find(title_tokens(a.get("title")), after_pos)
    if cand:
        p, y, level, pos = cand[0]
        return p, y, level, "标题", pos
    cand = bk.find(first_sentence_tokens(a.get("text")), after_pos)
    if cand:
        p, y, level, pos = cand[0]
        return p, y, level, "正文", pos
    return None


def build_title(base, u, zone):
    """拼新标题。保持现有 'Unit N · 标题' 形态，不引入新格式。"""
    return f"Unit {u} · {base}"


_CN_DIGITS = "零一二三四五六七八九十"
_AR_UNIT_RE = re.compile(r"^第\s*(\d+)\s*单元")
_CN_UNIT_RE = re.compile(r"^第\s*([零一二三四五六七八九十]+)\s*单元")


def cn_num(n):
    """1 -> 一（只到 20，课本单元号用不到更大）。"""
    if n <= 10:
        return _CN_DIGITS[n] if n < 10 else "十"
    if n < 20:
        return "十" + _CN_DIGITS[n - 10]
    return str(n)


def sync_title_translate(tt, u):
    """英文标题的单元号变了，中文译文的 '第N单元' 要跟着变。

    两种写法都见过：'第1单元·…'（阿拉伯）和 '第二单元 · …'（中文数字），
    按原文风格改写，不统一格式。
    """
    if not tt:
        return tt
    if _AR_UNIT_RE.match(tt):
        return _AR_UNIT_RE.sub(f"第{u}单元", tt, count=1)
    if _CN_UNIT_RE.match(tt):
        return _CN_UNIT_RE.sub(f"第{cn_num(u)}单元", tt, count=1)
    return tt


def main():
    apply = "--apply" in sys.argv
    add_missing = "--add-missing" in sys.argv
    only = None
    if "--pages" in sys.argv:
        only = sys.argv[sys.argv.index("--pages") + 1].split(",")
    report = []
    changed_total = missing_total = failed_total = 0
    out = os.path.join(ROOT, "_tools", "_unit_report.txt")

    def log(msg):
        print(msg, flush=True)

    def flush():
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(report))

    for key, pdfname in BOOKS:
        if only and key not in only:
            continue
        pdfpath = os.path.join(PDF_DIR, pdfname)
        artpath = os.path.join(ART_DIR, key + ".json")
        if not os.path.exists(pdfpath):
            report.append(f"!! 缺 PDF: {pdfname}")
            flush()
            continue
        log(f"[{key}] 解析 PDF ...")
        bk = Book(pdfpath, log)
        arr = json.load(open(artpath, encoding="utf-8"))
        changed = missing = failed = 0
        last_pos = -1
        last_unit = {"main": None, "rp": None}
        report.append("=" * 110)
        report.append(f"[{key}] 篇数={len(arr)} PDF页数={bk.doc.page_count}")
        log(f"[{key}] 篇数={len(arr)}，定位 ...")
        for i, a in enumerate(arr):
            title = a.get("title") or ""
            m = re.match(r"^Unit\s*(\d+)\s*·\s*", title)
            cur = int(m.group(1)) if m else None
            base = TITLE_PREFIX_RE.sub("", title).strip()
            hit = locate_article(bk, a, last_pos)
            if hit is None:
                failed += 1
                report.append(f"  #{i:>2} 定位失败 title={title!r}")
                continue
            p, y, level, how, pos = hit
            last_pos = pos
            u, src = bk.resolve_unit(p, y)
            zone = bk.zone_of(p)
            flag = ""
            suspect = False
            # 单调性防呆：正文区的单元号必须**单调不减**。
            # 定位到错页时（泛标题 'Review 1'、'Again, please' 会撞到别的单元）
            # 就会出现 unit 倒退 → 判为可疑，不改标题。
            prev = last_unit.get(zone)
            if u is not None and prev is not None and u < prev:
                suspect = True
            if u is None:
                flag = "  (unit 未知)"
            elif suspect:
                flag = "  (定位可疑·不单调)"
            elif cur is not None and cur != u:
                flag = "  <<< 前缀错"
                changed += 1
            elif cur is None:
                flag = "  (缺前缀)"
                missing += 1
            if u is not None and not suspect:
                last_unit[zone] = u
            report.append(
                f"  #{i:>2} p={p:>4} y={y:>6} 档={level:>2} 定位={how} 区={zone} "
                f"unit={u}({src}) 现前缀={cur} {base[:36]!r}{flag}")
            if apply and u is not None and not suspect:
                newt = build_title(base, u, zone)
                if flag == "  <<< 前缀错" or (flag == "  (缺前缀)" and add_missing):
                    a["title"] = newt
                    a["titleTranslate"] = sync_title_translate(a.get("titleTranslate"), u)
        if apply:
            with open(artpath, "w", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(arr, ensure_ascii=False, indent=2) + "\n")
        changed_total += changed
        missing_total += missing
        failed_total += failed
        report.append(f"  --> 前缀错 {changed} / 缺前缀 {missing} / 定位失败 {failed}")
        report.append(f"累计: 前缀错 {changed_total} / 缺前缀 {missing_total} / 定位失败 {failed_total}  (apply={apply})")
        flush()
        log(f"[{key}] 完成：前缀错 {changed} / 缺前缀 {missing} / 定位失败 {failed}")
        bk.doc.close()
    report.append(f"\n总: 前缀错 {changed_total} / 缺前缀 {missing_total} / 定位失败 {failed_total}  (apply={apply})")
    flush()
    log(f"总: 前缀错 {changed_total} / 缺前缀 {missing_total} / 定位失败 {failed_total}")
    log("wrote " + out)


if __name__ == "__main__":
    main()
