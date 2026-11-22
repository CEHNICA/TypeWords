#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""尺子：莱芜 13 册词库 vs 课本词表（正式尺子）

查三类问题
  MISSING  课本词表里有、词库里完全没有的词 —— 漏词（真缺口）
  TRANS    两边都有，但词库首释义（trans[0].cn）与课本口径不一致
           —— 用户在复习页会看到「跟课本不一样」
  DIRTY    词库里混进了不该有的词头（含中文 / 括号 / 标点）
           —— PDF 抽取噪声写回时带进来的垃圾

判定口径和写回口径**必须一致**（都用 _textbook_wordsheet 的
heads_of / head_ok / split_entry），否则尺子会把脏值报成永久不一致。

用法
  python _tools/check_book_wordsheet.py              # 全 13 册
  python _tools/check_book_wordsheet.py --only LWCZ_8_2
  python _tools/check_book_wordsheet.py --selftest    # 尺子自检（退回验证）

退出码：有失败项 → 1
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import _textbook_wordsheet as tw

BIDS = list(tw.etw['PDFS'].keys())


# ---------------------------------------------------------------- 页面显示口径
def short(cn):
    """复习页真正显示的样子：取第一段 + 14 字截断"""
    first = (cn or '').split('；')[0].split(';')[0].strip()
    if len(first) > 14:
        first = first[:14] + '…'
    return first


def norm(cn):
    return re.sub(r'\s+', '', (cn or '')).strip('。．.！!？?')


DIRTY_HEAD = re.compile(r'[\u4e00-\u9fff（）()\[\]。，、；！？!?…]')


def check_book(bid, book, order, heads, universe_keys):
    """→ [(kind, word, detail)]；kind ∈ MISSING / TRANS / DIRTY"""
    problems = []
    dict_keys = {tw.head_key(str(w.get('word', '')).strip()).lower()
                 for w in book if isinstance(w, dict) and w.get('word')}

    # MISSING：课本有、词库没有
    for h in order:
        if tw.head_key(h).lower() in dict_keys:
            continue
        if tw.head_ok(h, dict_keys, universe_keys):
            problems.append(('MISSING', h, '课本词表有、词库没有'))

    # TRANS：释义口径不一致（按页面可见口径）
    lower_map = {}
    for k in heads:
        lower_map.setdefault(k.lower(), []).append(k)
    for w in book:
        if not isinstance(w, dict):
            continue
        word = str(w.get('word') or '').strip()
        if not word:
            continue
        key = word
        if key not in heads:
            cand = lower_map.get(word.lower()) or []
            if len(cand) == 1:
                key = cand[0]
            else:
                continue
        book_cn = tw.sanitize_cn(heads[key]) if hasattr(tw, 'sanitize_cn') \
            else heads[key]
        trans = w.get('trans') or []
        cur = trans[0].get('cn', '') if trans else ''
        if short(cur) == short(book_cn):
            continue
        # 课本值是页面值的前缀 → 课本释义被 PDF 截断，页面值更完整，不算问题
        cn_n, book_n = norm(cur), norm(book_cn)
        if cn_n and book_n and len(book_n) >= 2 and cn_n.startswith(book_n):
            continue
        problems.append(('TRANS', word, '页面=%r 课本=%r' % (cur, book_cn)))

    # DIRTY：垃圾词头
    for w in book:
        if not isinstance(w, dict):
            continue
        word = str(w.get('word') or '').strip()
        if word and DIRTY_HEAD.search(word):
            problems.append(('DIRTY', word, '词头含中文/标点'))

    return problems


def load_universe():
    keys = set()
    d = os.path.join(ROOT, 'public', 'dicts', 'en', 'word')
    for f in os.listdir(d):
        if not f.endswith('.json'):
            continue
        try:
            arr = json.load(open(os.path.join(d, f), encoding='utf-8'))
        except Exception:
            continue
        for w in arr:
            if isinstance(w, dict) and w.get('word'):
                keys.add(str(w['word']).strip().lower())
    return keys


# ---------------------------------------------------------------- 退回验证
def selftest():
    """故意造坏样本 → 尺子必须**精确**报出那一类、那一条。

    尺子崩了比尺子红更可怕，所以这一步是强制的。
    """
    universe = {'apple', 'banana', 'centre', 'center', 'program', 'wrongdef'}
    heads = {
        'apple': '苹果',
        'banana': '香蕉',
        'centre': '中心',
        'program': '节目；课程',
    }
    order = ['apple', 'banana', 'centre', 'program']

    good = [
        {'word': 'apple', 'trans': [{'pos': '', 'cn': '苹果'}]},
        {'word': 'banana', 'trans': [{'pos': '', 'cn': '香蕉'}]},
        {'word': 'centre', 'trans': [{'pos': '', 'cn': '中心'}]},
        {'word': 'program', 'trans': [{'pos': '', 'cn': '节目；课程'}]},
    ]
    cases = []

    # ① 基准：干净样本必须 0 问题
    p = check_book('X', good, order, heads, universe)
    cases.append(('基准（干净样本）', p, []))

    # ② 删掉一个词 → 精确报 MISSING centre / centre
    bad = [dict(w) for w in good if w['word'] != 'centre']
    p = check_book('X', bad, order, heads, universe)
    cases.append(('删掉 centre', p, [('MISSING', 'centre')]))

    # ③ 释义写错 → 精确报 TRANS banana
    bad = [dict(w) for w in good]
    bad[1] = {'word': 'banana', 'trans': [{'pos': '', 'cn': '芭蕉'}]}
    p = check_book('X', bad, order, heads, universe)
    cases.append(('banana 释义写错', p, [('TRANS', 'banana')]))

    # ④ 垃圾词头 → 精确报 DIRTY
    bad = [dict(w) for w in good]
    bad.append({'word': '续表', 'trans': [{'pos': '', 'cn': 'x'}]})
    p = check_book('X', bad, order, heads, universe)
    cases.append(('混入垃圾词头「续表」', p, [('DIRTY', '续表')]))

    ok = True
    for name, got, want in cases:
        got_set = [(k, w) for k, w, _ in got]
        if got_set != want:
            ok = False
            print('[FAIL] %-22s 期望 %s 实际 %s' % (name, want, got_set))
        else:
            print('[PASS] %-22s 精确报出 %s' % (name, got_set or '无'))
    print('-' * 60)
    print('尺子自检失败项合计: %d' % (0 if ok else 1))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', help='只看这些册（逗号分隔）')
    ap.add_argument('--selftest', action='store_true', help='尺子退回验证')
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    only = args.only.split(',') if args.only else None
    universe = load_universe()
    total = 0
    fail_books = 0
    for bid in BIDS:
        if only and bid not in only:
            continue
        book = tw.load_dict(bid)
        order, heads = tw.heads_of(bid)
        problems = check_book(bid, book, order, heads, universe)
        total += len(problems)
        status = 'PASS' if not problems else 'FAIL'
        if problems:
            fail_books += 1
        print('[%s] %-9s 词库 %4d 词 / 课本词表 %4d 词 / 问题 %d'
              % (status, bid, len(book), len(order), len(problems)))
        for kind, word, detail in problems[:12]:
            print('        %-8s %-28s %s' % (kind, word[:28], detail))
        if len(problems) > 12:
            print('        ...还有 %d 条' % (len(problems) - 12))
    print('-' * 60)
    print('合计：问题 %d 条，失败册数 %d' % (total, fail_books))
    print('失败项合计: %d' % total)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
