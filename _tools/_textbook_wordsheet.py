#!/usr/bin/env python
"""莱芜 13 册 —— 课本词表抽取（共享模块）

词表章节定位
  课本词表都在**书末**。不能用 scripts/extract-textbook-wordlists.py 的 tier 定位：
  那是「只降不升」的，命中一个 tier0 标题后后面所有页（含课文）都算 tier0
  （八下 121 页里 105 页是课文）。
  口径：**词表标题命中页集合里，取「连续命中 ≥2 页」那个连续段的起点**。
  目录页里也有 'Words and chunks in each unit 79' 这种带页码的目录行，
  但它孤零零只命中 1 页 → 会被这个规则排除。

  标题关键词：英文 referencewordlist / vocabularyindex / alphabetical /
  vocabularyaz / eachunit；中文「单元词汇表 / 词汇表 / 词语表 / 词汇索引」
  （小学五下的词表章节只有中文标题）。

解析规则（本模块 = 唯一口径，抽词 / 对账 / 写回都走这里）
  1) 词头带全角/半角括号注释 —— 'of（属于）……的'、'grandfather（外）祖父'
  2) 词头带尾部标点 —— 'How are you?'、'Good morning!'
  3) 词头带音标 —— 'mum /mʌm/ (= mom /ɒm/) n. 妈妈'
  4) 释义含句号 —— '很高兴见到你。'（短句特判放行）
  5) 词头尾部词性标记 —— 'absent /əˈbsent/ adj. 不在的' → 词头是 'absent'
     （剥词性时要求**前面有空格**，否则 'can'/'her' 这类普通词会被误伤）
  6) 跨行释义要先合并 —— 'centre(=center) （商业或其他活动' + '    的）中心'
  7) 括号里的英文同义写法 → 多个候选词头 —— 'I'm (I am)' → ['I'm','I am']
     但括号里是**虚词**（'play a role (in)'）时只取前半，不拆出 'in'
  8) 斜杠双写法 —— 'colour/color' → ['colour','color']（斜杠前有空格 = 短语内部，不拆）
  9) PDF 吃掉斜杠造成缩写粘连 —— 'TV/television' → 'TVtelevision' → 拆回两段
     （只认全大写前缀，'T-shirt' 不能被切成 'T-' + 'shirt'）
 10) 纯注释型词条要丢掉 —— 'a ... art. （用于单数）'（释义只有一个括号说明，没实际意思）
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ETW_PATH = os.path.join(ROOT, 'scripts', 'extract-textbook-wordlists.py')

# 加载 etw（屏蔽它的 stdout 包装，避免二次 import 把底层 buffer 关掉）
etw = {'__file__': ETW_PATH, '__name__': 'etw'}
_src = open(ETW_PATH, encoding='utf-8').read()
_src = _src.replace("sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')", "")
exec(compile(_src, ETW_PATH, 'exec'), etw)

CJK = re.compile(r'[\u4e00-\u9fff]')
BRACKET = re.compile(r'[（(][^）)]*[）)]')
PHON = re.compile(r'/[^/]{1,40}/')
WL_KEYS = ('referencewordlist', 'vocabularyindex', 'alphabetical',
           'vocabularyaz', 'eachunit',
           '单元词汇表', '词汇表', '词语表', '词汇索引')

# 目录区页数（各册目录都在 p.6~p.10，词表章节一律在书末 p.79+）
TOC_ZONE_PAGES = 20

# PDF 里 fi / fl 这类 ligature（'difficult' 抽成 'difficult'）
LIG = str.maketrans({
    'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl',
    'ﬅ': 'st', 'ﬆ': 'st', ' ': ' ',
})

# 词性标记：
#   可省略点的（n / v / adj / adv …）——课本两种写法都有（'absent adj.' 与 'adj'）
#   必须带点的（art / link / num / int / modal / abbr）——它们本身也是英语单词，
#   省略点会把 'the art' 剥成 'the'
POS_ANY = r'n|v|vt|vi|adj|adv|prep|conj|pron|interj|aux|modal|int|num|abbr'
POS_DOTTED_ONLY = r'art|link'
POS_TOKEN = r'(?:(?:' + POS_ANY + r')\s*\.?|(?:' + POS_DOTTED_ONLY + r')\s*\.)'
# 结尾的词性链，可带 '&' 连接：'across /əˈkrɒs/ adv. & prep.'
POS_TAIL = re.compile(r'(?:\s*&\s*|\s+)' + POS_TOKEN + r'\s*$', re.IGNORECASE)
MID_POS = re.compile(r'\s(?:n|v|vt|vi|adj|adv|prep|pron|conj|interj|aux|art|num)\s*\.',
                     re.IGNORECASE)

POS_ONLY = {'n', 'v', 'vt', 'vi', 'adj', 'adv', 'prep', 'conj', 'pron', 'num',
            'aux', 'art', 'modal', 'interj', 'int', 'link', 'abbr', 'pl', 'sing'}

# 括号里如果是这些，不能当成同义写法拆出独立词头
# （'play a role (in)' → 'in' 不是单词条目）
BRACKET_STOP = {'in', 'on', 'at', 'to', 'for', 'with', 'of', 'the', 'a', 'an',
                 'sb', 'sth', 'it', 'them', 'us', 'up', 'out', 'off'}

# 词头**结尾**是这些虚词 → 是被截断的短语（'Museum of'、'quite a'）
TAIL_DANGLE = {'of', 'the', 'a', 'an', 'to', 'in', 'on', 'at', 'for', 'with',
               'and', 'or', 'is', 'are', 'was', 'were', 'be', 'been', 'by',
               'from', 'as', 'that', 'this', 'it', 'its'}

# 词头**开头**是词性标记 → 切错了（'n. spoonful'）
LEAD_POS = re.compile(r'^(?:n|v|vt|vi|adj|adv|prep|pron|conj|interj|aux|art|num)\s*\.',
                      re.IGNORECASE)


def norm(w):
    w = (w or '').translate(LIG)
    w = w.replace('’', "'").replace('‘', "'")
    return re.sub(r'\s+', ' ', w).strip()


def head_key(w):
    """词头归一化键（撇号/连字归一，大小写保留，尾部点去掉：'A.D.' ↔ 'A.D'）"""
    return norm(w).rstrip('.').strip()


def strip_pos(head):
    """剥掉词头结尾的词性标记（'absent /əˈbsent/ adj.' → 'absent'）

    允许 '&' 连接：'across adv. & prep.' → 'across'
    """
    prev = None
    while prev != head:
        prev = head
        while True:
            m = POS_TAIL.search(head)
            if not m:
                break
            head = head[:m.start()].strip()
    return head.strip(' .,;:')


def paren_unbalanced(s):
    return s.count('（') > s.count('）') or s.count('(') > s.count(')')


def split_entry(line):
    """→ (英文侧, 中文侧)；括号注释不算释义起点"""
    spans = [(m.start(), m.end()) for m in BRACKET.finditer(line)]
    first_cjk = None
    for m in CJK.finditer(line):
        if not any(a <= m.start() < b for a, b in spans):
            first_cjk = m.start()
            break
    if first_cjk is None:
        return None
    cn_start = first_cjk
    for a, b in spans:
        if b <= first_cjk and line[b:first_cjk].strip() == '':
            cn_start = max(cn_start, b)
    en = line[:cn_start].strip()
    cn = line[cn_start:].strip()
    if not en or not cn:
        return None
    return en, cn


def clean_cn(cn):
    """释义清洗：丢掉纯注释 / 括号没闭合的 / 语法讲解整句"""
    cn = (cn or '').strip()
    if not cn:
        return None
    # 括号没闭合 → 是被截断的注释行（'a ... art. （用于单数'）
    if paren_unbalanced(cn):
        return None
    # 释义只有一个括号说明 → 没有实际意思（'（用于单数）'）
    if re.fullmatch(r'[（(][^）)]*[）)]', cn):
        return None
    # 前置长括号注释 + 真正的意思（'（商业或其他活动的）中心' → '中心'）
    m = re.match(r'^[（(][^）)]{4,}[）)]\s*(.+)$', cn)
    if m:
        cn = m.group(1).strip()
    # 一行里塞了多个词性（'patient n. 病人 adj. 有耐心的'）→ 只取第一个意思
    m = re.search(r'\s+(?:n|v|vt|vi|adj|adv|prep|pron|conj|num|int|interj|aux|'
                  r'modal|art|abbr|link)\s*\.', cn)
    if m:
        cn = cn[:m.start()].strip()
    cn = etw['clean_cn'](cn)
    if not cn:
        return None
    if '。' in cn and len(cn) > 12:
        return None
    if etw['cn_is_bad'](cn):
        # cn_is_bad 见到 '。' 就丢 → 短句（课本原句）特判放行
        if '。' in cn and len(cn) <= 12 and not re.search(r'[A-Za-z]', cn) \
                and cn.count('（') == cn.count('）'):
            return cn
        return None
    return cn


NOISE_LINE = re.compile(r'^(?:p\.?\s*\d+|\d{1,3})$')
# 词表章节标题（中文）——出现时是标题，不是某条的释义
HEADING_CN = re.compile(r'^(?:单元)?(?:词汇表|词语表|词汇索引|词语索引|附录|索引|目录|生词表)$')
# 续行也可能以词性开头（'n. 自行车；脚踏车' / 'adj. & adv. 每一百中'）
CONT_POS = re.compile(r'^(?:n|v|vt|vi|adj|adv|prep|conj|pron|modal|int|interj|'
                       r'num|art|abbr|aux|link)\s*\.', re.IGNORECASE)


# 附录表格的标题行 —— 出现即表示词表已结束（后面是附录，不是词表）
APPENDIX_KEYS = (
    'irregularverbs', 'irregularverb', 'regularverbs',
    'appendix', 'appendices',
)

# 页眉 / 章节标题（去掉非字母后比对）
# 注意：**不放单个真词**（'vocabulary' / 'unit' 本身是英语单词），
# 只放组合型的标题短语 + 表格列名。
HEADER_TOKENS = {
    'referencewordlist', 'vocabularyineachunit',
    'wordsandchunksineachunit', 'wordsandexpressionsineachunit',
    'vocabularyfromprimaryschoolineachunit',
    'vocabularyinalphabeticalorder', 'wordsandchunks', 'wordsandexpressions',
    'alphabeticalorder', 'pasttense', 'pastparticiple',
}

# 版权页 / 教材说明行 —— 整行丢掉
DROP_LINE_RE = re.compile(r'义务教育教科书|义务教育英语课程标准|本词表不含|'
                           r'本词表中的重点词汇|^注[:：]|^后记$')


def _is_header_line(s):
    """是不是页眉 / 章节标题 / 单元号 / A—Z 索引字母

    带音标（'/'）的一律不是页眉 —— 页眉不会有音标，
    而 'vocabulary /vəˈkæbjələri/ n. 词汇' 是货真价实的词条。
    """
    if CJK.search(s):
        return False
    if '/' in s:
        return False
    low = re.sub(r'[^a-z]', '', s.lower())
    if low in HEADER_TOKENS:
        return True
    if re.fullmatch(r'unit\d*', low):
        return True
    if re.fullmatch(r'[A-Z]', s):          # A—Z 索引的单个字母
        return True
    if low.startswith('vocabulary'):
        return True
    return False


def _bracket_spans(s):
    """这一行里所有「括号区」的范围（含**未闭合**的左括号 → 到行尾）

    BRACKET 正则只匹配闭合的括号对；词表里大量跨行注释（'centre(=center) （商业
    或其他活动' + '的）中心'）第一行的左括号是未闭合的，
    不补上就会把括号里的中文误判成「括号外」。
    """
    spans = [(m.start(), m.end()) for m in BRACKET.finditer(s)]
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in '（(':
            j = i + 1
            while j < n and s[j] not in '）)':
                j += 1
            if j >= n:
                spans.append((i, n))     # 未闭合 → 到行尾
            else:
                i = j                     # 已配对 → 跳过内容
        i += 1
    return spans


def _cn_outside_bracket(s):
    """这一行**括号外**有没有中文

    '在（……）对面' → True
    'Miss /mɪs/ （对未婚女子的礼貌称呼）' → False（释义在下一行）
    'centre(=center) （商业或其他活动' → False（括号没闭合，中文在续行里）
    """
    spans = _bracket_spans(s)
    for m in CJK.finditer(s):
        if not any(a <= m.start() < b for a, b in spans):
            return True
    return False


def _is_final(s):
    """这一行是不是已经定稿的词条（英文侧 + 中文释义 + 括号平衡）"""
    if paren_unbalanced(s):
        return False
    got = split_entry(s)
    if not got:
        return False
    en, cn = got
    return bool(en.strip()) and bool(cn.strip())


def merge_continuations(lines):
    """把词表文本流合并成一条条词条（v7）。

    合并语义 = v2（中文续行并进上一条），但：
      · 噪声行在进合并**之前**滤掉（页码 / 页眉 / 版权说明 / 附录整段截断）
      · 续行归属靠状态机判定，不靠'短中文行=标题'这种启发式
    """
    out = []
    pending = None          # 正在攒的词条
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if NOISE_LINE.match(s):
            continue                      # 页码 'p.18' / 'p54' / 纯数字
        if _is_header_line(s):
            continue                      # 页眉 / 单元号 / A—Z 索引字母
        if DROP_LINE_RE.search(s):
            continue                      # 版权页 / 教材说明
        low = re.sub(r'[^a-z]', '', s.lower())
        if low in APPENDIX_KEYS:
            break                         # 附录开始 → 后面整块丢掉
        if HEADING_CN.match(s):
            continue                      # '词汇表' / '单元词语表' 章节标题

        # ① 词性标记开头的行 → 一定是词条的续行（'adj. 失望的'）
        #    但只在「上一条还没定稿」或「这一行括号没闭合」时才并入
        if CONT_POS.match(s) and CJK.search(s):
            if pending is not None and (not _is_final(pending)
                                        or paren_unbalanced(s)):
                pending += s
            continue

        # ② 完整词条 → 收尾上一条，自己开新条
        if _is_final(s):
            if pending is not None:
                out.append(pending)
            pending = s
            continue

        # ③ 不完整的行
        if pending is None:
            pending = s
            continue
        if not _is_final(pending):
            # 上一条还没定稿 → 这一行是它的续行
            pending = pending + (s if CJK.search(s) else ' ' + s)
            continue
        # 上一条已定稿
        if _en_side_of(s):
            # 这一行有英文侧 → 是**新词条**的开始（释义可能跨行）
            out.append(pending)
            pending = s
            continue
        # 整行是中文且没有英文侧 → 小标题 / 版权段落 → 丢
        continue
    if pending is not None:
        out.append(pending)
    return out


def _cn_tail(line):
    """取一行里第一个中文之后的部分（没有中文返回 ''）"""
    m = CJK.search(line)
    return line[m.start():] if m else ''


def find_wordlist_start(doc):
    """词表章节起始页（0-based）

    课本书末有**两段**词表：
      · 单元词表（'单元词语表' / 'Vocabulary in Each Unit'）—— 短语、专名都在这
      · A—Z 索引（'词汇表' / 'Reference Word List' / 'Vocabulary Index'）—— 单词
    两段都要，所以起点取**最早的真实词表标题页**。

    怎么区分「真实章节」和「目录里的那一行」？两条一起判：
      · 目录行末尾带页码：'Words and chunks in each unit        79'
        真实标题不带：  '单元词语表' / 'Vocabulary in Each Unit'
      · 目录区在书的前 ~20 页（各册目录都在 p.6~p.10），
        词表章节一律在书末（实测最早 p.79）
    → 两种命中都忽略，再取最早的剩余页。

    （旧口径用「连续命中 ≥2 页」排除目录行，结果把只有 1 页标题的
      小学'单元词语表'整段跳过了 → 小学册少抽 11~40 个词）
    """
    hits = []
    for i in range(doc.page_count):
        if i < TOC_ZONE_PAGES:
            continue                     # 目录区
        for line in doc[i].get_text().splitlines():
            t = re.sub(r'[\s\d]+', '', line.lower())
            if any(k in t for k in WL_KEYS):
                s = line.strip()
                if re.search(r'(?:\d+|p\.\s*\d+)\s*$', s):
                    continue          # 目录行（末尾带页码）→ 跳过
                hits.append(i)
                break
    if hits:
        return min(hits)
    # 兜底：老口径（连续命中 ≥2 页）
    hits = []
    for i in range(doc.page_count):
        for line in doc[i].get_text().splitlines():
            t = re.sub(r'[\s\d]+', '', line.lower())
            if any(k in t for k in WL_KEYS):
                hits.append(i)
                break
    if not hits:
        return 0
    s = set(hits)
    n = doc.page_count
    for i in range(n):
        if i not in s:
            continue
        j = i
        while j + 1 < n and (j + 1) in s:
            j += 1
        if (j - i + 1) >= 2:
            return i
    return max(hits)


def _alts_of(h):
    """一个词头行 → 候选词头列表"""
    # 括号同义写法 —— 'I'm (I am)' → ['I'm','I am']；'centre(=center)' → ['centre','center']
    # 括号里是虚词（'play a role (in)'）→ 只取前半
    m_br = re.match(r"^([A-Za-z][A-Za-z'\- ]*?)\s*[(（]([^()（）]*)[)）]", h)
    if m_br:
        base = m_br.group(1).strip()
        inner = m_br.group(2).strip()
        if inner.startswith('='):
            inner = inner[1:].strip()
        inner = PHON.sub('', inner).strip()
        # 剥 'AmE.' / 'BrE.' 前缀（'grey (AmE gray /ɡreɪ/)' → 'gray'）
        inner = re.sub(r'^(?:AmE|BrE)\.?\s*', '', inner).strip()
        low = inner.lower()
        if inner and low not in BRACKET_STOP and len(inner) > 1 \
                and re.fullmatch(r"[A-Za-z][A-Za-z '\-]*", inner):
            return [base, inner]
        return [base]
    if '/' in h:
        parts = h.split('/')
        if all(' ' not in x for x in parts):
            return [x.strip() for x in parts if x.strip()]
        return [h]
    return [h]


def _split_glued(h):
    """PDF 吃掉斜杠造成缩写粘连（'TVtelevision' → ['TV','television']）

    只认**全大写字母**前缀（2~4 个），否则 'T-shirt' 会被切成 'T-' + 'shirt'。
    """
    if len(h) <= 5:
        return [h]
    for k in range(2, min(5, len(h)) + 1):
        if not re.fullmatch(r'[A-Z]{2,4}', h[:k]):
            continue
        if not h[k:][:1].islower() or len(h) - k < 3:
            continue
        return [h[:k], h[k:]]
    return [h]


def _en_side_of(s):
    """这一行有没有**英文侧**（去掉括号区后，剩下的是不是以字母开头）

    'weekday  工作日（星期一至星期五' → True（完整词条，释义括号跨行）
    '基数词' / '续表' / '出版社和山东教育出版社合作编写' → False
    '（美国城市） Spencer Silver' → True
    """
    spans = _bracket_spans(s)
    rest = []
    prev = 0
    for a, b in spans:
        rest.append(s[prev:a])
        prev = b
    rest.append(s[prev:])
    rest = ''.join(rest).strip()
    return bool(re.match(r'^[A-Za-z]', rest))


def entry_alts(piece):
    """一条合并后的行 → [(词头, 课本释义), ...]（可能多个同义写法）

    模块和诊断尺子共用这一份 —— 之前诊断脚本自己抄了一份，
    剥括号/剥私用区字符的规则改了尺子却没跟上，对拍结论全是假的。
    """
    got = split_entry(piece)
    if not got:
        return []
    en, cn = got
    # 'T-shirt  T 恤衫' → 中文侧起点前的孤立单字母是中文拼音首字母（T恤），
    # 不属于英文词头 → 剔掉，否则词头变成 'T-shirt T'
    en = re.sub(r'\s+[A-Za-z]$', '', en).strip()
    cn2 = clean_cn(cn)
    if not cn2:
        return []
    h = PHON.sub(' ', en)
    # 剥英文侧的前置括号注释（'（美国城市） Spencer Silver'）
    h = re.sub(r'^[（(][^）)]*[）)]\s*', '', h)
    # PDF 私用区字符（'Marie \uf020Curie' → 'Marie Curie'）
    h = re.sub(r'[\uf000-\uf8ff]', '', h)
    h = re.sub(r'\s+', ' ', h).strip()
    h = strip_pos(h)
    h = norm(h).strip(' .,;:')
    if not h:
        return []
    alts = _alts_of(h)
    if len(alts) == 1:
        alts = _split_glued(alts[0])
    return [(alt, cn2) for alt in alts if alt]


def heads_of(bid):
    """→ (有序词头列表, {词头: 课本释义})"""
    mode = 'primary' if bid.startswith('LWXX') else 'junior'
    import pymupdf
    doc = pymupdf.open(os.path.join(etw['PDF_DIR'], etw['PDFS'][bid]))
    start = find_wordlist_start(doc)
    order = []
    heads = {}
    stream = []
    for i in range(start, doc.page_count):
        stream.extend(doc[i].get_text().splitlines())
    for line in merge_continuations(stream):
        pieces = [line] if mode == 'primary' else \
            [x.strip() for x in re.split(r'p\.?\s*\d+', line) if x.strip()]
        for piece in pieces:
            for alt, cn2 in entry_alts(piece):
                if alt not in heads:
                    heads[alt] = cn2
                    order.append(alt)
    doc.close()
    return order, heads


def is_fragment(head, universe_keys):
    """PDF 抽字残缺检测（只对**全小写单词**生效，避开人名地名）

    课本词表里出现 'botom'（少一个 t）、'tention'（少两个 at）这种
    —— 真实词表不会有这种词，是 PDF 抽字掉了字符。
    判据：词头本身不在全库词表里，但全库里有
      · 长度差 1 的近邻（删/插了一个字符），或
      · 把它整个包含进去、且只多 1~2 个字符的词
    人名地名（首字母大写）不参与判定：'Billy' vs 'bill'、'Paula' vs 'Paul'
    是两个不同的词，不能当残缺。
    """
    if not universe_keys or len(head) < 5:
        return False
    if head != head.lower() or ' ' in head or '-' in head:
        return False
    low = head.lower()
    if low in universe_keys:
        return False
    for w in universe_keys:
        if abs(len(w) - len(low)) == 1 and edit1(w, low):
            return True
        if 1 <= len(w) - len(low) <= 2 and low in w:
            return True
    return False


def head_ok(h, dict_keys=None, universe_keys=None):
    """词头能不能作为词条补进词库"""
    if not h or len(h) > 24:
        return False
    if h.lower() in POS_ONLY:
        return False
    if '…' in h or '...' in h or '……' in h:
        return False
    if re.search('[《》“”"]', h):
        return False
    if re.search(r'[，。、；：（）()\[\]]', h):
        return False
    if h.endswith('-') or '--' in h:
        return False
    if re.search(r'\b(sb|sth)\b', h):
        return False
    # 被截断的短语（'bottom of one's heart  内心深处' 被 PDF 拆成两行，
    # 只剩 'bottom of one's' 配上了错位的释义）
    if re.search(r"\bone's\b", h, re.IGNORECASE):
        return False
    if MID_POS.search(h):
        return False
    if LEAD_POS.match(h):
        return False
    # 结尾是虚词 → 截断的短语，不是一条完整词条
    # （单词虚词在课本词表里是合法词条：小学的 'of'、初中的 'a'/'at'/'for'）
    if len(h.split()) >= 2 and h.split()[-1].lower().strip('.,;:') in TAIL_DANGLE:
        return False
    if not re.fullmatch(r"[A-Za-z][A-Za-z'\- .]*", h):
        return False
    if ' ' in h.strip():
        parts = h.split()
        if len(parts) > 3:
            return False
        if any(p.lower() in POS_ONLY for p in parts):
            return False
    if is_fragment(h, universe_keys):
        return False
    # PDF 抽字残缺（'botom'）：词库里有编辑距离 1 的词 → 同一个词，不补
    if dict_keys is not None and len(h) >= 4:
        low = h.lower()
        for k in dict_keys:
            if k != low and abs(len(k) - len(low)) <= 1 and edit1(k, low):
                return False
    return True


def edit1(a, b):
    """编辑距离 ≤1"""
    if abs(len(a) - len(b)) > 1:
        return False
    if a == b:
        return True
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    if len(a) > len(b):
        a, b = b, a
    i = j = 0
    skipped = False
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def dict_path(bid):
    return os.path.join(ROOT, 'public', 'dicts', 'en', 'word', etw['DICT_FILES'][bid])


def load_dict(bid):
    return json.load(open(dict_path(bid), encoding='utf-8'))


def gaps_of(bid, book=None, dict_keys=None, universe_keys=None):
    """→ [(词头, 课本释义)]，按课本词表顺序"""
    if book is None:
        book = load_dict(bid)
    if dict_keys is None:
        dict_keys = {head_key(str(w.get('word', '')).strip()).lower()
                     for w in book if isinstance(w, dict) and w.get('word')}
    order, heads = heads_of(bid)
    out = []
    for h in order:
        hk = head_key(h)
        if hk.lower() in dict_keys:
            continue
        if head_ok(h, dict_keys, universe_keys):
            out.append((h, heads[h]))
    return out
