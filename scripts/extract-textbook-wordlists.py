#!/usr/bin/env python
"""
从莱芜五四制课本 PDF 提取「课本词汇表」：word -> 课本中文释义
=========================================================

为什么要有这个
  复习页（book-review）显示的中文 = 词条 trans[0].cn 的第一段（通用词典首释义），
  而课本词表自带一套中文（教辅口径），两者不一致 → 用户看到「跟课本不一样」。
  本脚本把课本自己的口径抽出来，作为权威源。

课本里有好几套词表（都算「课本口径」），权威度不一样
  小学（LWXX_*）
    · Vocabulary in alphabetical order   全书 A—Z 总词表   ← 最权威
    · Words and chunks in each unit     每单元词表
    · 课内词卡（p.38~95）               ← 兜底
  初中（LWCZ_*）
    · Reference Word List               全书总词表          ← 最权威
    · Vocabulary A—Z
    · Vocabulary in Each Unit / Vocabulary from Primary School …
    · 课文正文里撞词的行                ← 兜底（优先级最低）

  PDF 文本抽取在两栏页上会**丢英文**（'cloudy' 只剩 'l' 'd'），
  同一条词条在不同来源里可能：英文完整/残缺、中文被拆两行/粘着下一条。
  → 策略：**多来源各抽一遍当候选，按章节定优先级，同级取最长**。

噪声控制（四道）
  1) 结构层：'p.N' 分块、词性标记（adj./n./v. …）当粘连信号切断
  2) 内容层：候选释义里出现 ASCII 字母 / 词性标记 / '单元词语表' / '注：' → 丢弃
  3) 章节层：正文撞词只能进兜底层，优先级最低
  4) 白名单层：只保留该册词库里真实存在的词头

用法
  python scripts/extract-textbook-wordlists.py --dump LWXX_3_1   # 打印抽样，不写文件
  python scripts/extract-textbook-wordlists.py --apply            # 写 data/textbook-wordlists.json

产物
  data/textbook-wordlists.json
    { "LWXX_3_1": { "greeting": "问候", "hello": "喂；你好", ... }, ... }
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 课本 PDF 所在目录（本机私有路径不入库）
#   env TW_TEXTBOOK_PDF_DIR → data/local_paths.json → <repo>/课本PDF
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from local_paths import resolve_pdf_dir  # noqa: E402
PDF_DIR = resolve_pdf_dir()

# 册 id -> PDF 文件名
PDFS = {
    'LWXX_3_1': '小学五四-三年级上册.pdf',
    'LWXX_3_2': '小学五四-三年级下册.pdf',
    'LWXX_4_1': '小学五四-四年级上册.pdf',
    'LWXX_4_2': '小学五四-四年级下册.pdf',
    'LWXX_5_1': '小学五四-五年级上册.pdf',
    'LWXX_5_2': '小学五四-五年级下册.pdf',
    'LWCZ_6_1': '初中五四-六年级上册.pdf',
    'LWCZ_6_2': '初中五四-六年级下册.pdf',
    'LWCZ_7_1': '初中五四-七年级上册.pdf',
    'LWCZ_7_2': '初中五四-七年级下册.pdf',
    'LWCZ_8_1': '初中五四-八年级上册.pdf',
    'LWCZ_8_2': '初中五四-八年级下册.pdf',
    'LWCZ_9_1': '初中五四-九年级全一册.pdf',
}
# 册 id -> 词库 json 文件名（public/dicts/en/word/）
DICT_FILES = {
    'LWXX_3_1': 'LWXX-3-1.json', 'LWXX_3_2': 'LWXX-3-2.json',
    'LWXX_4_1': 'LWXX-4-1.json', 'LWXX_4_2': 'LWXX-4-2.json',
    'LWXX_5_1': 'LWXX-5-1.json', 'LWXX_5_2': 'LWXX-5-2.json',
    'LWCZ_6_1': 'LWCZ-6-1.json', 'LWCZ_6_2': 'LWCZ-6-2.json',
    'LWCZ_7_1': 'LWCZ-7-1.json', 'LWCZ_7_2': 'LWCZ-7-2.json',
    'LWCZ_8_1': 'LWCZ-8-1.json', 'LWCZ_8_2': 'LWCZ-8-2.json',
    'LWCZ_9_1': 'LWCZ-9-1.json',
}

# 章节标题 → 权威层级（数字越小越权威）
# 各册标题不统一（'Vocabulary in Each Unit' / 'Words and Expressions in Each Unit' /
# 'Vocabulary Index' / 'Reference Word List' / 'Vocabulary in alphabetical order'），
# 所以用**规则**判层，不硬编码标题。
def section_tier(title_norm: str):
    t = title_norm
    if 'referencewordlist' in t or 'vocabularyindex' in t or 'alphabetical' in t:
        return 0                      # 全书总词表
    if 'vocabularyaz' in t:
        return 1                      # A—Z
    if 'eachunit' in t or 'fromprimaryschool' in t or t == 'vocabulary':
        return 2                      # 每单元词表
    return None


FALLBACK_TIER = 9                              # 课内词卡 / 正文撞词

CJK = re.compile(r'[\u4e00-\u9fff]')
# 中文起点：**只认全角括号**（半角 '(' 常出现在音标里：/pˈetə(r)/）
CN_START = re.compile(r'[\u4e00-\u9fff（]')
# 词头（纯英文词条，允许空格 / 连字符 / 撇号 / 括号内的补充形式）
EN_ONLY = re.compile(r"^[A-Za-z][A-Za-z'’\-\.\(\) ]{0,38}$")
# 词头（初中：带音标）
EN_HEAD = re.compile(r"^([A-Za-z][A-Za-z'\- ]*?)(?=\s*/|\s+[a-z]+\.|[\u4e00-\u9fff（]|$)")
PAGE_REF = re.compile(r'^p\.\s*\d+\s*$', re.I)
PAGE_NUM = re.compile(r'^\d{1,3}$')
# 词性标记 —— 在中文释义里出现 = 粘上了下一条
POS_WORD = re.compile(r'\b(?:adj|adv|v|vt|vi|n|prep|conj|pron|num|art|aux|modal|int|interj|abbr|pl|sing|imp|inf)\s*\.', re.I)
# 明确的中文噪声片段
NOISE_CN = ('单元词语表', '注：', 'Words and', 'Vocabulary in', '注释')
MAX_CN_LEN = 35


def norm_title(s: str) -> str:
    """章节标题归一化：只留字母与汉字（'Vocabulary A—Z' → 'vocabularyaz'）"""
    s = s.strip().lower()
    return ''.join(ch for ch in s if ch.isascii() and ch.isalpha() or CJK.match(ch))


def norm_key(en: str) -> str:
    s = en.split('(')[0].strip()
    s = s.rstrip('.。!！?？').strip()
    return s


# 撇号的各种 Unicode 形态 → 直撇号（课本 PDF 与词库用的形态不一致）
APOS_MAP = {
    '\u2019': "'", '\u2018': "'", '\u201b': "'", '\u201a': "'",
    '\u2032': "'", '\u02bc': "'", '\u275b': "'", '\u275c': "'",
}


def norm_word(w: str) -> str:
    """词条归一化：撇号统一（**保留大小写**）"""
    w = w.strip()
    for k, v in APOS_MAP.items():
        w = w.replace(k, v)
    return w


def norm_lo(w: str) -> str:
    return norm_word(w).lower()


def extract_cn(text: str):
    """从一段文本里切出「中文释义」

    处理这些坑：
      'centre /ˈsentə(r)/（= center）n. 中心；中央'
        → 等值说明 '（= center）' 跳过；半角 '(r)' 是音标 → 跳过；中文从 '中心' 开始
      'Peter /ˈpiːtə(r)/ 彼得'
        → 半角括号里没汉字 → 当音标整段跳过 → '彼得' ✓
      '另外的人（或物）adj.另外的；其他的'
        → 'adj.' 是**下一条**的词性标记 → 在 '另外的人（或物）' 处截断
      '（狗叫声）汪汪wow哇，呀dog狗'
        → 注释表串进来 → 在 '汪汪' 处截断
    """
    n = len(text)
    i = 0
    start = None
    while i < n:
        ch = text[i]
        if ch == '（':
            close = text.find('）', i)
            inner = text[i + 1:close] if close != -1 else text[i + 1:]
            if inner.lstrip().startswith('='):      # 等值说明 → 整段跳过
                i = (close + 1) if close != -1 else n
                continue
            start = i
            break
        if ch == '(':
            close = text.find(')', i)
            inner = text[i + 1:close] if close != -1 else text[i + 1:]
            if CJK.search(inner):                 # 括号里是中文 → 属于释义
                start = i
                break
            i = (close + 1) if close != -1 else n  # 括号里没中文 → 音标/英文，跳过
            continue
        if CJK.match(ch):
            start = i
            break
        i += 1
    if start is None:
        return None
    cn = text[start:]
    depth = 0
    seen_cn = False
    for idx, c in enumerate(cn):
        if c in '（(':
            depth += 1
        elif c in '）)':
            depth = max(0, depth - 1)
        elif depth == 0:
            if c.isascii() and (c.isalpha() or c == '.'):
                if seen_cn:
                    return cn[:idx]      # 后面混进了别的条目 → 截断
            elif CJK.match(c):
                seen_cn = True
            if seen_cn and c in '；;，,。 ':
                # 词性标记紧跟在中文后面 → 下一条的起点
                tail = cn[idx + 1:]
                m = POS_WORD.match(tail.lstrip())
                if m and tail.lstrip().startswith(m.group(0)):
                    cut = idx + 1 + (len(tail) - len(tail.lstrip()))
                    return cn[:cut]
    return cn


def clean_cn(cn: str) -> str:
    # PDF 里会混进定位控制字符（如 \x08 退格符），LWCZ_6_1 有 33 条释义被它粘住
    cn = ''.join(ch for ch in cn if ord(ch) >= 32 or ch in '\t\n\r')
    cn = re.sub(r'/[^/]*/', ' ', cn)                       # 去音标
    cn = re.sub(r'[（(]\s*pl\.\s*[^）)]*[）)]', ' ', cn, flags=re.I)  # 去 (pl. xxx)
    cn = re.sub(r'/[^）)一-鿿]{0,12}', '', cn)             # 去残留的半个音标（'记录/ˈ'）
    cn = re.sub(r'\s+', '', cn)
    cn = cn.strip('；;，,。. ')
    return cn


def _cn_outside_parens(text: str) -> str:
    """取括号外的中文（深度 0）"""
    out = []
    depth = 0
    for c in text:
        if c in '（(':
            depth += 1
        elif c in '）)':
            depth = max(0, depth - 1)
        elif depth == 0 and CJK.match(c):
            out.append(c)
    return ''.join(out)


def cn_is_bad(cn: str) -> bool:
    """候选释义是否明显是噪声/粘连"""
    if not cn:
        return True
    if len(cn) > MAX_CN_LEN:
        return True
    if POS_WORD.search(cn):
        return True
    for bad in NOISE_CN:
        if bad in cn:
            return True
    if '。' in cn:
        return True          # 语法讲解框的整句，不是词义
    if '例如' in cn or '意为' in cn:
        return True
    # 括号不闭合 → 释义被跨行截断了
    if cn.count('（') != cn.count('）'):
        return True
    # 末尾是个纯中文短括号、而它前面没有中文 → 中文被吞了，只剩残片
    #   '（shoot的过去式）（篮）'  ← '投' 字丢了
    #   '（sing的过去式）唱（歌）'  ← 正常（前面有 '唱'）
    #   '（am、is、are）是'         ← 正常（括号里是英文词形）
    lb = cn.rfind('（')
    close = cn.rfind('）')
    if lb != -1 and close > lb:
        inner = cn[lb + 1:close]
        if (re.fullmatch(r'[\u4e00-\u9fff]{1,2}', inner)
                and not _cn_outside_parens(cn[:lb])):
            return True
    return False


def parse_primary(line: str):
    """小学版式：一行一条，英文侧 + 中文侧"""
    m = CN_START.search(line)
    if not m:
        return None
    en = line[:m.start()].strip()
    if not EN_ONLY.match(en):
        return None
    cn = extract_cn(line[m.start():])
    if cn is None:
        return None
    cn = clean_cn(cn)
    if cn_is_bad(cn):
        return None
    return en, cn


def parse_block(block: str):
    """初中版式：一条可能跨行，形如 'unit /ˈjuːnɪt/ n. 单元'"""
    block = ' '.join(x.strip() for x in block.splitlines() if x.strip())
    if not block:
        return None
    # 块内可能粘连下一条（'世界卫生组织p.3UN联合国'）→ 按 p.N 截断
    mp = re.search(r'p\.\s*\d+', block)
    if mp:
        block = block[:mp.start()]
    block = block.strip()
    if not block:
        return None
    m = EN_HEAD.match(block)
    if not m:
        return None
    en = m.group(1).strip()
    rest = block[m.end():]
    if not rest:
        return None
    # 课本把音标插在词中间：'Angel /ˈeɪndʒl/ Falls 安赫尔瀑布'
    # → 英文词头其实是 'Angel Falls'
    m2 = re.match(r"^/[^/]*/\s*([A-Za-z][A-Za-z'\- ]*?)(?=\s|$)", rest)
    if m2:
        en = en + ' ' + m2.group(1).strip()
        rest = rest[m2.end():]
    cn = extract_cn(rest)
    if cn is None:
        return None
    cn = clean_cn(cn)
    if cn_is_bad(cn):
        return None
    return en, cn


def _mergeable(prev_cn: str) -> bool:
    """上一条的中文看起来没说完 → 下一行纯中文是它的续行"""
    if not prev_cn:
        return False
    if prev_cn.count('（') > prev_cn.count('）'):
        return True
    return prev_cn[-1] in '；;，,、'


def page_tiers(doc, mode):
    """逐页判定属于哪个词表章节 → 权威层级"""
    out = []
    cur = FALLBACK_TIER
    for i in range(doc.page_count):
        lines = doc[i].get_text().splitlines()
        for line in lines:
            # 章节标题必须是「独占一行、没有页码」的标题行（目录行带页码，排除）
            if re.search(r'\d', line):
                continue
            t = section_tier(norm_title(line))
            if t is not None and t < cur:
                cur = t
        out.append(cur)
    return out


def extract_raw(pdf_path, mode):
    import pymupdf
    doc = pymupdf.open(pdf_path)
    tiers = page_tiers(doc, mode)
    rows = []
    for i in range(doc.page_count):
        tier = tiers[i]
        lines = doc[i].get_text().splitlines()
        if mode == 'primary':
            last = None
            for line in lines:
                got = parse_primary(line)
                if got:
                    rows.append((got[0], got[1], tier))
                    last = got
                    continue
                # 教材把一条释义排成两行时，续行是「只有中文、没有英文」的行；
                # 只有上一条明显没说完时才合并，否则会把下一条的释义粘进来
                s = line.strip()
                if last and s and CJK.search(s) and not re.search(r'[A-Za-z]', s) \
                        and _mergeable(last[1]):
                    merged = clean_cn(last[1] + ' ' + s)
                    if cn_is_bad(merged):
                        rows.pop()
                        last = None
                    else:
                        last = (last[0], merged)
                        rows[-1] = (last[0], last[1], tier)
        else:
            buf = []
            for line in lines:
                s = line.strip()
                if PAGE_REF.match(s):
                    got = parse_block('\n'.join(buf))
                    if got:
                        rows.append((got[0], got[1], tier))
                    buf = []
                    continue
                if PAGE_NUM.match(s):
                    continue
                buf.append(line)
            got = parse_block('\n'.join(buf))
            if got:
                rows.append((got[0], got[1], tier))
            # 参考词表（Reference Word List）每条一行、没有 'p.N' → 逐行再抽一遍
            for line in lines:
                s = line.strip()
                if not s or PAGE_REF.match(s) or PAGE_NUM.match(s):
                    continue
                got = parse_block(s)
                if got:
                    rows.append((got[0], got[1], tier))
    doc.close()
    return rows


def dict_words(bid):
    """返回 (归一化 key -> 词库原样词头)

    key = 撇号统一后的**原样词头**（保留大小写）。
    必须**区分大小写**：课本里 'WHO'（世界卫生组织）和 'who'（谁）、'US'（美国）和
    'us'（我们）、'Brown'（布朗）和 'brown'（棕色）是不同词条，小写归一会串台。
    """
    path = os.path.join(ROOT, 'public', 'dicts', 'en', 'word', DICT_FILES[bid])
    if not os.path.exists(path):
        return None
    arr = json.load(open(path, encoding='utf-8'))
    out = {}
    for w in arr:
        if not isinstance(w, dict):
            continue
        word = str(w.get('word', '')).strip()
        if not word:
            continue
        out[norm_word(word)] = word
    return out


def build(bid):
    pdf = os.path.join(PDF_DIR, PDFS[bid])
    if not os.path.exists(pdf):
        return None, [], 'PDF 不存在: ' + pdf
    mode = 'primary' if bid.startswith('LWXX') else 'junior'
    rows = extract_raw(pdf, mode)
    allow = dict_words(bid)
    if allow is None:
        return None, rows, '词库 json 不存在'
    cands = {}
    for en, cn, tier in rows:
        raw = norm_key(en)
        if not raw:
            continue
        nw = norm_word(raw)
        key = allow.get(nw)                 # 撇号统一 + 大小写精确
        if key is None:
            # 大小写不一致（'who' 撞上词库里的 'WHO'）→ 歧义，宁可不写
            continue
        cands.setdefault(key, []).append((tier, cn))
    # 同一词多个候选 → 先按权威层级取最低，同级取最长
    out = {}
    for key, lst in cands.items():
        best_tier = min(t for t, _ in lst)
        same = [c for t, c in lst if t == best_tier]
        out[key] = max(same, key=len)
    return out, rows, ''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dump', help='只处理这一册并打印抽样（不写文件）')
    ap.add_argument('--apply', action='store_true', help='写 data/textbook-wordlists.json')
    args = ap.parse_args()

    targets = [args.dump] if args.dump else list(PDFS)
    outfile = os.path.join(ROOT, 'data', 'textbook-wordlists.json')
    merged = {}
    if os.path.exists(outfile):
        merged = json.load(open(outfile, encoding='utf-8'))

    for bid in targets:
        wl, rows, err = build(bid)
        if wl is None:
            print(f'[SKIP] {bid} {err}')
            continue
        allow = dict_words(bid)
        total = len(allow)
        merged[bid] = wl
        print(f'=== {bid} ({PDFS[bid]}) 命中 {len(wl)} 词 / 词库 {total} 词 '
              f'(覆盖率 {len(wl) * 100 // max(1, total)}%) / 宽松候选 {len(rows)} 行')
        for k, v in list(wl.items())[:25]:
            print(f'   {k!r} -> {v!r}')

    if args.apply:
        os.makedirs(os.path.dirname(outfile), exist_ok=True)
        with open(outfile, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=1, sort_keys=True)
        print('写出', outfile, '共', len(merged), '册')


if __name__ == '__main__':
    main()
