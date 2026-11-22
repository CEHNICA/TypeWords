#!/usr/bin/env python
"""
课本释义 vs 词库首释义 对账尺子
================================
复习页显示的中文 = shortTrans(word) = trans[0].cn 按 '；' 取第一段、截 14 字；
课本词表自带一套中文（教辅口径）。两者不一致 → 用户看到「跟课本不一样」。

本尺子做两件事
  1) 对账：逐册逐词比「页面显示」与「课本口径」，列出不一致
  2) --apply：把课本口径写回该册词条的 trans[0]（通用词典释义保留在 trans 后面）

用法
  python _tools/check_textbook_trans.py            # 全 13 册对账
  python _tools/check_textbook_trans.py --apply    # 写回词库
  python _tools/check_textbook_trans.py --dump LWCZ_6_1
"""
import argparse
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

DICT_FILES = {
    'LWXX_3_1': 'LWXX-3-1.json', 'LWXX_3_2': 'LWXX-3-2.json',
    'LWXX_4_1': 'LWXX-4-1.json', 'LWXX_4_2': 'LWXX-4-2.json',
    'LWXX_5_1': 'LWXX-5-1.json', 'LWXX_5_2': 'LWXX-5-2.json',
    'LWCZ_6_1': 'LWCZ-6-1.json', 'LWCZ_6_2': 'LWCZ-6-2.json',
    'LWCZ_7_1': 'LWCZ-7-1.json', 'LWCZ_7_2': 'LWCZ-7-2.json',
    'LWCZ_8_1': 'LWCZ-8-1.json', 'LWCZ_8_2': 'LWCZ-8-2.json',
    'LWCZ_9_1': 'LWCZ-9-1.json',
}
WL_FILE = os.path.join(ROOT, 'data', 'textbook-wordlists.json')

# 页面渲染规则（app/pages/(words)/book-review.vue 的 shortTrans）
def short(cn: str) -> str:
    """取第一段并按 14 字截断 —— 页面真正显示的就是这个"""
    first = (cn or '').split('；')[0].split(';')[0].strip()
    if len(first) > 14:
        first = first[:14] + '…'
    return first


def page_display(trans):
    return short((trans[0].get('cn', '') if trans else '') or '')


def norm(cn: str) -> str:
    return re.sub(r'\s+', '', (cn or '')).strip('。．.！!？?')


def sanitize_cn(cn: str) -> str:
    """PDF 里混进来的定位控制字符（如 \\x08 退格符）不能进词库。

    LWCZ_6_1 有 33 条课本释义被 \\x08 粘在末尾（'泰山\\x08'），
    写回后被 check_dict_data.py 的 CTRL 项判为脏数据。
    对账和写回都走这一个函数 → 两边口径一致，不会假阳性。
    """
    return ''.join(ch for ch in (cn or '') if ord(ch) >= 32 or ch in '\t\n\r').strip()


def brackets_broken(cn: str) -> bool:
    """括号不闭合 → 释义残缺，不能写回"""
    return cn.count('（') != cn.count('）') or cn.count('(') != cn.count(')')


def load_wl():
    if not os.path.exists(WL_FILE):
        print('缺课本词表缓存，先跑 scripts/extract-textbook-wordlists.py --apply')
        return {}
    return json.load(open(WL_FILE, encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='把课本释义写回词库 trans[0]')
    ap.add_argument('--dump', help='只看这一册')
    args = ap.parse_args()

    wl = load_wl()
    if not wl:
        sys.exit(1)

    total_diff = 0
    total_words = 0
    total_hit = 0
    total_write = 0
    total_skip = 0
    per_book = []
    for bid, fname in DICT_FILES.items():
        if args.dump and bid != args.dump:
            continue
        path = os.path.join(ROOT, 'public', 'dicts', 'en', 'word', fname)
        raw = open(path, 'rb').read()
        arr = json.loads(raw.decode('utf-8'))
        book = wl.get(bid, {})
        diffs = []
        hit = 0
        wrote = 0
        skipped = 0
        for w in arr:
            word = (w.get('word') or '').strip()
            book_cn = book.get(word)
            if not book_cn:
                # 课本词表 key 是词库原样词头；找不到就按忽略大小写唯一匹配
                cand = [k for k in book if k.lower() == word.lower()]
                if len(cand) == 1:
                    book_cn = book[cand[0]]
            if not book_cn:
                continue
            book_cn = sanitize_cn(book_cn)
            if not book_cn:
                continue
            hit += 1
            trans = w.get('trans') or []
            cur = trans[0].get('cn', '') if trans else ''
            if short(cur) == short(book_cn):
                continue
            diffs.append((word, cur, book_cn))
            if args.apply:
                if brackets_broken(book_cn):
                    skipped += 1
                    continue
                if not trans:
                    skipped += 1
                    continue
                old = dict(trans[0])
                bn = book_cn.strip()
                # 写回前先剔除「与课本释义完全相同」的旧行。
                # 不剔就会撞出重复：
                #   'green'  课本'绿色，绿色的' vs 旧 {pos:'', cn:'绿色，绿色的'}
                #   'See you tomorrow' 课本'明天见' vs 旧 {pos:'', cn:'明天见'}
                # → check_dict_data.py 的 D2/D3 会立刻报红。
                # 通用词典那层释义本来就在 kept 里（信息不丢），不用额外追加。
                kept = [t for t in trans if (t.get('cn') or '').strip() != bn]
                w['trans'] = [{'pos': old.get('pos', ''), 'cn': book_cn}] + kept
                wrote += 1
        total_words += len(arr)
        total_hit += hit
        total_diff += len(diffs)
        total_write += wrote
        total_skip += skipped
        per_book.append((bid, len(arr), hit, len(diffs)))
        print(f'{bid}: 词库 {len(arr)} 词，课本词表命中 {hit}，释义不一致 {len(diffs)}'
              + (f'（写回 {wrote}，跳过残缺 {skipped}）' if args.apply else ''))
        for word, cur, book_cn in diffs[:8]:
            print(f'    {word!r}: 页面显示={cur!r} 课本={book_cn!r}')
        if len(diffs) > 8:
            print(f'    ...还有 {len(diffs) - 8} 条')
        if args.apply and wrote:
            from json_io import dump_like
            with open(path, 'wb') as f:
                f.write(dump_like(raw, arr))

    print('-' * 60)
    print(f'合计：词库 {total_words} 词，课本词表命中 {total_hit}，释义不一致 {total_diff}')
    if args.apply:
        print(f'写回 {total_write} 条，跳过（课本释义括号不闭合）{total_skip} 条')


if __name__ == '__main__':
    main()
