#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
莱芜课本课文体检器 —— 句粒度 + 译文（2026-11-21 新增）
=================================================
两条硬指标：

1) **句粒度**：跟打页里「一行 = 一句 = 一次朗读单元」
   （`genArticleSectionData` 按 `\\n` 切句，`playSentenceAudio` 用整行文本去发音）。
   所以一行里塞了 N 个英文句子 → 朗读就"一次性说到底"。
   → 判据：句内不得出现「句末标点 + 空白 + 大写/引号开头」的第二次切分点。

2) **译文**：课文 textTranslate 必须与句子一一对应（段落用 `\\n\\n`、句间用 `\\n`）。
   缺译文 → 跟打页整块译文区不显示。

怎么跑：
    python _tools/check_article_sentences.py            # 静态查文件
    python _tools/check_article_sentences.py --http     # 顺便校验本地服务能取到
"""
import argparse
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLE_DIR = os.path.join(ROOT, 'public', 'dicts', 'en', 'article')
DICT_DIR = os.path.join(ROOT, 'public', 'dicts', 'en', 'word')

BOOKS = [
    ('LWXX_3_1', 37), ('LWXX_3_2', 32), ('LWXX_4_1', 30), ('LWXX_4_2', 26),
    ('LWXX_5_1', 30), ('LWXX_5_2', 25),
    ('LWCZ_6_1', 20), ('LWCZ_6_2', 22), ('LWCZ_7_1', 24), ('LWCZ_7_2', 24),
    ('LWCZ_8_1', 27), ('LWCZ_8_2', 11), ('LWCZ_9_1', 45),
]

# 句内二次切分点：句末标点 + 空白 + 下一句开头（大写字母 / 引号 / 说话人冒号）
RE_SPLIT = re.compile(r'[.!?]["\')\]]*\s+([A-Z"\'])')
# 缩写：这些点后面不能切
ABBR = re.compile(
    r'\b(?:Mr|Mrs|Ms|Dr|Prof|St|Jr|Sr|vs|etc|e\.g|i\.e|U\.S|U\.K|U\.S\.A|No)\.$',
    re.I)

# 说话人冒号（对话体）：`Fu Xing: What do you think...`
RE_SPEAKER = re.compile(r'(?:^|(?<=[.!?]\s)|(?<=\n))\s*[A-Z][A-Za-z.\' ]{0,18}:\s')


class Checker:
    def __init__(self):
        self.results = []

    def check(self, ok, name, detail=''):
        self.results.append((bool(ok), name, detail))
        return bool(ok)

    @property
    def failed(self):
        return [r for r in self.results if not r[0]]

    def report(self):
        for ok, name, detail in self.results:
            line = '[%s] %s' % ('PASS' if ok else 'FAIL', name)
            if detail and not ok:
                line += '  ->  ' + detail
            print(line)
        print('-' * 60)
        print('共 %d 项，通过 %d，失败 %d' %
              (len(self.results), len(self.results) - len(self.failed), len(self.failed)))
        return len(self.failed)


def count_splits(line: str):
    """返回一行里的「英文句子数」（至少 1）。"""
    n = 1
    for m in RE_SPLIT.finditer(line):
        head = line[:m.start() + 1]
        if ABBR.search(head):
            continue
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--http', action='store_true')
    args = ap.parse_args()

    c = Checker()
    total_sent = 0
    total_multi = 0
    total_articles = 0
    total_no_trans = 0

    for book, expect_articles in BOOKS:
        path = os.path.join(ARTICLE_DIR, book + '.json')
        if not os.path.exists(path):
            c.check(False, '%s 词库文件存在' % book, path)
            continue
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        arts = data if isinstance(data, list) else [data]
        total_articles += len(arts)
        c.check(len(arts) == expect_articles, '%s 篇数 = %d' % (book, expect_articles),
                '实际 %d' % len(arts))

        multi = []
        no_trans = []
        sent_total = 0
        mismatch = []
        for a in arts:
            text = a.get('text') or ''
            trans = a.get('textTranslate') or ''
            paras = [p for p in text.split('\n\n') if p.strip()]
            sents = []
            for p in paras:
                for s in p.split('\n'):
                    if s.strip():
                        sents.append(s)
            sent_total += len(sents)
            # 句粒度
            for s in sents:
                if count_splits(s) > 1:
                    multi.append('%s / %s' % (a.get('title', '?')[:16], s[:60]))
            # 译文
            if not trans.strip():
                no_trans.append(a.get('title', '?'))
            else:
                t_paras = [p for p in trans.split('\n\n') if p.strip()]
                t_sents = []
                for p in t_paras:
                    t_sents.extend([x for x in p.split('\n') if x.strip()])
                if len(t_sents) != len(sents):
                    mismatch.append('%s 句=%d 译文行=%d' % (a.get('title', '?')[:16],
                                                           len(sents), len(t_sents)))

        total_sent += sent_total
        total_multi += len(multi)
        total_no_trans += len(no_trans)

        c.check(not multi, '%s 每「句」只含 1 个英文句子' % book,
                '%d 句多句合并，例: %s' % (len(multi), ' | '.join(multi[:2])))
        c.check(not no_trans, '%s 每篇都有中文译文' % book,
                '%d 篇缺译文' % len(no_trans))
        c.check(not mismatch, '%s 译文行数与句数一一对应' % book,
                '%d 篇对不上，例: %s' % (len(mismatch), ' | '.join(mismatch[:2])))

    c.check(total_articles == 353, '课文总篇数 = 353', '实际 %d' % total_articles)
    c.check(total_multi == 0, '全库没有多句合并的「句」', '还有 %d 句' % total_multi)
    c.check(total_no_trans == 0, '全库没有缺译文的篇', '还有 %d 篇' % total_no_trans)
    print('句总数 = %d' % total_sent)

    if args.http:
        try:
            with urllib.request.urlopen('http://localhost:5567/list/article.json', timeout=15) as resp:
                served = json.loads(resp.read().decode('utf-8'))
            ids = {int(x['id']) for x in served}
            ok = True
            for book, _ in BOOKS:
                url = '/dicts/en/article/%s.json' % book
                try:
                    with urllib.request.urlopen('http://localhost:5567' + url, timeout=15) as r2:
                        d2 = json.loads(r2.read().decode('utf-8'))
                    if not d2:
                        ok = False
                except Exception:
                    ok = False
            c.check(ok, '本地服务能取到 13 册课文')
            c.check(len(ids) >= 250, '本地服务 list/article.json 册数 >= 250', '实际 %d' % len(ids))
        except Exception as e:
            c.check(False, '本地服务可访问', str(e))

    return 1 if c.report() else 0


if __name__ == '__main__':
    sys.exit(main())
