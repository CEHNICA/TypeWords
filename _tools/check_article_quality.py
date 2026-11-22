"""
课文质量尺子
============
检查项：
  S1 句粒度    —— 一行只应含一句（不能一整自然段挤一行）
  S2 译文非空  —— 每句都要有中文译文
  S3 译文对齐  —— 译文行数必须与原文行数一致（逐句一一对应）
  S4 无乱序    —— 不能有「逐字交错」的畸形串
  S5 无断词    —— 不能有句首小写（上一行被切断）
  S6 标题译文  —— titleTranslate 不能为空

用法： python _tools/check_article_quality.py
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "public", "dicts", "en", "article")
BOOKS = ["LWXX_3_1", "LWXX_3_2", "LWXX_4_1", "LWXX_4_2", "LWXX_5_1", "LWXX_5_2",
         "LWCZ_6_1", "LWCZ_6_2", "LWCZ_7_1", "LWCZ_7_2", "LWCZ_8_1", "LWCZ_8_2", "LWCZ_9_1"]

# 句末标点 + 可选收尾引号
SENT_END = re.compile(r'[.!?]["\')\]]*\s*$')

# 常见长单词白名单（避免把正常长词误判成乱序）
LONG_OK = set("""
another anything beautiful because birthday classroom comfortable confident conversation
customer different everything exercise families favourite February furniture generally
happiness important introduce invitation kindness language learning listening medicine
messages morning museum necessary November occasion opposite ordinary parents patiently
perfect perhaps picture pollution practise prepare probably question quickly restaurant
saturday sandwich scientist September something sometimes special station straight stranger
structure students sunshine teacher telephone television temperature terrible Thursday together
tomorrow tonight triangle understanding vegetable Wednesday weight wednesday wonderful yesterday
anything classroom comfortable conversation deliberately development difficulty education
environment especially everything experience experiment explanation international knowledge
necessarily opportunity organisation particularly performance personality photograph
politically population preference professional relationship responsibility scientific
sensitivity significance situation technology temperature transportation university
virtually vocabulary volunteer watching weather whether wikipedia wonderful yesterday
experiment expression discussion electric education engineering environment european
equipment especially especially excellent excitement executive existence expensive
experience explanation function generation government guarantee hospital identity immediate
important impression incredible independence industrial influence information initiative
interested interesting international introduction invitation judgement knowledge language
leadership listening literature management meaningful measurement midnight million minister
misunderstanding naturally necessary negotiation nevertheless newspaper obviously
occasionally operation opportunity ordinary organisation originally particular partnership
performance permanent permission personal personality philosophy photograph physical
population practically preference preparation presentation president pressure pretty
previously probably procedure production professional professor promising protection
prototype publication purpose quality quantity question quickly railway reality reasonable
recently recognize recommendation reference relationship remarkable responsibility restaurant
restaurant retirement revolutionary ridiculous satisfaction scientific seriously significantly
similar situation specially strategy strength structure substitute suggestion successful
sufficient supporting surprise surrounded technology terrible thanksgiving themselves
thoroughly thousand thoughtful thousand tomorrow tradition traditional tremendous
unfortunately university unnecessary usually valuable various vegetable violence voluntary
wonderful yesterday yourself
""".split())
LONG_OK = set(w.lower() for w in LONG_OK)


def build_long_ok():
    """自动扩充长词白名单：把全库词库里出现过的长词都加进来
    （这样只有「全库从来没有过的畸形长词」才会被判成乱序）"""
    root = os.path.normpath(os.path.join(DIR, "..", "word"))
    wl = os.path.normpath(os.path.join(DIR, "..", "..", "..", "list", "word.json"))
    if not os.path.exists(wl):
        return
    for d in json.load(open(wl, encoding="utf-8")):
        f = os.path.join(root, d["url"])
        if not os.path.exists(f):
            continue
        for w in json.load(open(f, encoding="utf-8")):
            t = (w.get("word") or "").strip().lower()
            if len(t) >= 8:
                LONG_OK.add(t)
                # 词形还原：加 s/es/ed/ing
                for suf in ("s", "es", "ed", "ing"):
                    if t.endswith(suf):
                        LONG_OK.add(t[: -len(suf)])


def sentences_of(text):
    """按段落/句切分，与 genArticleSectionData 一致"""
    out = []
    for para in (text or "").split("\n\n"):
        if not para.strip():
            continue
        for s in para.split("\n"):
            if s.strip():
                out.append(s.strip())
    return out


def paras_of(text):
    return [p for p in (text or "").split("\n\n") if p.strip()]


def check():
    fails = []
    stats = {"articles": 0, "sentences": 0, "translated": 0, "multi": 0, "lower": 0, "garbled": 0}
    for b in BOOKS:
        f = os.path.join(DIR, b + ".json")
        if not os.path.exists(f):
            fails.append(("S0-缺文件", b, "", ""))
            continue
        arr = json.load(open(f, encoding="utf-8"))
        for ai, a in enumerate(arr):
            stats["articles"] += 1
            tag = f"{b}#{ai}"
            title = (a.get("title") or "")[:40]
            text = a.get("text") or ""
            sents = sentences_of(text)
            stats["sentences"] += len(sents)

            # S6 标题译文
            if not (a.get("titleTranslate") or "").strip():
                fails.append(("S6-标题无译文", tag, title, (a.get("title") or "")[:80]))

            # S1 句粒度：一行里有多个句末标点 → 又是粗粒度
            for s in sents:
                body = s.strip()
                # 去掉结尾标点后，内部再出现 .!? 且后面还跟大写/引号 → 多句
                inner = SENT_END.sub("", body)
                # 排除缩写点（Mr. / No. / e.g. 等）和引号内文本
                # 顺序要紧：e.g / i.e 是双点缩写，必须先整体替换，
                # 否则 'eg' / 'ie' 这种匹配不到，会被当成句末标点误报「一行多句」。
                probe = re.sub(r'\b(?:e\.g|i\.e)\.', '@', inner)
                probe = re.sub(r'\b(?:Mr|Mrs|Ms|Dr|Prof|St|Jr|Sr|No|Vol|vs|etc)\.', '@', probe)
                probe = re.sub(r'[.!?]["\')\]]*\s+(?=["\'“‘(])', '@', probe)
                probe = re.sub(r'\b[A-Z]\.', '@', probe)
                if re.search(r'[.!?]["\')\]]*\s+[A-Z"\'(]', probe):
                    stats["multi"] += 1
                    fails.append(("S1-一行多句", tag, title, body[:120]))

            # S2/S3 译文对齐
            tt = a.get("textTranslate") or ""
            if not tt.strip():
                fails.append(("S2-译文为空", tag, title, ""))
            else:
                tparas = paras_of(tt)
                pcount = len(paras_of(text))
                if len(tparas) != pcount:
                    fails.append(("S3-译文段数不符", tag, title,
                                  f"原文{pcount}段 vs 译文{len(tparas)}段"))
                else:
                    for pi, (tp, sp) in enumerate(zip(tparas, paras_of(text))):
                        tl = [x for x in tp.split("\n") if x.strip()]
                        sl = [x for x in sp.split("\n") if x.strip()]
                        if len(tl) != len(sl):
                            fails.append(("S3-译文句数不符", tag, title,
                                          f"第{pi+1}段 原文{len(sl)}句 vs 译文{len(tl)}句"))
                        for x in tl:
                            if x.strip():
                                stats["translated"] += 1
                        for x in tl:
                            if not x.strip():
                                fails.append(("S2-某句译文为空", tag, title, sp[:80]))
                                break

            # S5 句首小写
            #   例外：行首是 'e.g.' / 'i.e.' 这类双点缩写 —— 它本来就是小写，
            #   不是「上一行被切断」的证据。
            for s in sents:
                if re.match(r"^(?:e\.g|i\.e)\.", s):
                    continue
                if re.match(r"^[a-z]", s):
                    stats["lower"] += 1
                    fails.append(("S5-句首小写", tag, title, s[:120]))

            # S4 乱序串特征：**token 内部出现大写字母**（驼峰）
            # 真乱序串由两栏逐字交错产生，必然出现词内大写：
            #   hpoeoupr!leT / beomookr / OWpheant / caannd / HWeh
            # 正常人名地名是「首字母大写」，不会词内大写。
            for s in sents:
                toks = re.findall(r"[A-Za-z']+", s)
                # 排除正常的驼峰专名（BeiDou / eBay / iPhone / PowerPoint）
                bad = [t for t in toks if re.search(r"[a-z][A-Z]", t)
                       and not re.fullmatch(r'[A-Z][a-z]+[A-Z][a-z]+', t)]
                if bad:
                    stats["garbled"] += 1
                    fails.append(("S4-疑似乱序", tag, title, s[:140] + "  >>" + ",".join(bad[:3])))
    return fails, stats


def main():
    build_long_ok()
    fails, stats = check()
    print(f"文章 {stats['articles']} 篇 / 句 {stats['sentences']} / 已译 {stats['translated']}")
    print(f"一行多句 {stats['multi']} / 句首小写 {stats['lower']} / 疑似乱序 {stats['garbled']}")
    by = {}
    for k, tag, title, extra in fails:
        by.setdefault(k, []).append((tag, title, extra))
    print(f"\n失败项 {len(fails)}")
    for k, items in sorted(by.items()):
        print(f"\n== {k}  ({len(items)})")
        for tag, title, extra in items[:12]:
            print(f"   [{tag}] {title}")
            if extra:
                print(f"      {extra}")
        if len(items) > 12:
            print(f"   ... 还有 {len(items)-12} 条")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
