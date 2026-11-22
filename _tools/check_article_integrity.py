"""
课文文本损坏检测器（尺子）
=========================
三类损坏：
  T1 字符交错   —— 两句的字符被逐字穿插（"am beomookr ioefs p thhoatto sst uadnedn ts"）
  T2 句首小写   —— 句子开头小写，说明上一行被切断
  T3 悬空续句   —— 上一行以句号结尾，但下一行是某个更早句子的后半截（中间内容丢失）

用法： python _tools/check_article_integrity.py
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "public", "dicts", "en", "article")
BOOKS = ["LWXX_3_1", "LWXX_3_2", "LWXX_4_1", "LWXX_4_2", "LWXX_5_1", "LWXX_5_2",
         "LWCZ_6_1", "LWCZ_6_2", "LWCZ_7_1", "LWCZ_7_2", "LWCZ_8_1", "LWCZ_8_2", "LWCZ_9_1"]

WORD = re.compile(r"[A-Za-z']+")

# 常见英文词（用于判断交错出来的两半是否都是真词）
COMMON = set("""a an the and or but if so of to in on at by for with from as is are was were be been being
this that these those it its he she they we you i me my your his her their our not no do does did done
have has had will would can could shall should may might must love likes like liked want wants wanted
go goes going went come comes came make makes made get gets got give gives gave take takes took
book books read reads reading write writes writing student students school schools teacher teachers
learn learns learning learn-ing study studies easy hard best better more most much many little
paper papers print prints printing four four- four- miao name names friend friends good morning class
classroom work works working world worlds culture civilizations changed change changes living live lives
peace wars war physics technology scientist scientists contribution contributions chinese china
""".split())


def is_wordlike(w):
    return w.lower() in COMMON or len(w) >= 3


def interleaved(token):
    """判断一个 token 是否是两句字符交错产生的：奇偶位各成词"""
    t = token.strip("'")
    if len(t) < 6 or len(t) % 2 != 0:
        return None
    ev = t[0::2]
    od = t[1::2]
    return ev if is_wordlike(ev) and is_wordlike(od) else None


def scan_token_interleave(line):
    """一行里找被交错的 token；返回交错的 token 列表"""
    hits = []
    for m in WORD.finditer(line):
        tok = m.group(0)
        if len(tok) < 6:
            continue
        # 尝试把 token 拆成两半交错：即连续奇偶切分
        r = interleaved(tok)
        if r:
            hits.append((tok, r[0::2], r[1::2]))
    return hits


def main():
    t1 = t2 = t3 = 0
    details = []
    for b in BOOKS:
        p = os.path.join(DIR, b + ".json")
        if not os.path.exists(p):
            continue
        arr = json.load(open(p, encoding="utf-8"))
        for ai, a in enumerate(arr):
            lines = []
            for para in (a.get("text") or "").split("\n\n"):
                for s in para.split("\n"):
                    if s.strip():
                        lines.append(s.strip())
            for i, s in enumerate(lines):
                # T1 字符交错：强信号 —— 同一行里 >=3 个 token 连续呈交错形态
                hits = scan_token_interleave(s)
                toks = [m.group(0) for m in WORD.finditer(s)]
                if len(toks) >= 3:
                    # 逐 token 判定是否交错形态
                    inter_tokens = []
                    for m in WORD.finditer(s):
                        tok = m.group(0)
                        if len(tok) >= 6 and interleaved(tok):
                            inter_tokens.append(m.group(0))
                    if len(inter_tokens) >= 3 and len(inter_tokens) >= len(toks) * 0.5:
                        t1 += 1
                        details.append(("T1-字符交错", b, ai, a.get("title", ""), s,
                                        "交错token: " + ", ".join(inter_tokens[:6])))
                        continue
                # T2 句首小写
                if re.match(r"^[a-z]", s):
                    t2 += 1
                    details.append(("T2-句首小写", b, ai, a.get("title", ""), s, ""))
            # T3 悬空续句：下一行首字母大写但以逗号/介词开头，且上一行已句号结束
            for i in range(len(lines) - 1):
                prev, cur = lines[i], lines[i + 1]
                if not prev.rstrip().endswith((".", "!", "?", '"', "'")):
                    continue
                if re.match(r"^(of|to|and|but|for|with|from|in|on|at|by|as|is|are|was|were|that|which|who|when|while|during|after|before|it|its|he|she|they|we|you|i|has|have|had|do|does|did|not|no|so|because|if|then|than|into|over|under|about|after|since|until|while|where|what|how|why|one|two|work)", cur):
                    t3 += 1
                    details.append(("T3-悬空续句", b, ai, a.get("title", ""), cur, "上一行: " + prev[-60:]))
    print(f"T1 字符交错: {t1}\nT2 句首小写: {t2}\nT3 悬空续句: {t3}\n合计: {t1+t2+t3}\n")
    for kind, b, ai, title, s, extra in details:
        print(f"[{kind}] {b} #{ai} {title[:36]}")
        print(f"    {s[:150]}")
        if extra:
            print(f"    > {extra[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
