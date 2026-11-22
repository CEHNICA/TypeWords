#!/usr/bin/env python
"""补齐莱芜 13 册词库：把课本词表里有、词库没有的词**导入**词库。

用法:
  python _tools/fix_book_wordsheet_gaps.py            # 只看计划，不写
  python _tools/fix_book_wordsheet_gaps.py --apply    # 写回

规则
  · 权威源 = 课本 PDF 书末的词表章节（单元词表 + A—Z 索引）
  · 词条来源优先级：
      1) 全库 207 册里找现成条目 → 搬过来（保留音标/词性/同反义词），
         只把 trans[0].cn 换成课本释义
      2) 找不到 → 新建最小条目（id / word / trans / synos / relWords …）
  · 覆盖 trans[0] 前**先剔除与新值重复的旧行**（否则撞出重复释义）
  · 插入位置：按**课本词表顺序**（词库是单元序，不是字母序）——
    找该词在课本词表里的前一个词（且已在词库），插到它后面
  · 写回保持原文件格式（compact 单行 / LF / 无 BOM / 无末尾换行）
"""
import argparse
import copy
import json
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, '_tools'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

import _textbook_wordsheet as tw
from json_io import dump_like, load_preserve

BACKUP = r'C:\Users\17321\Documents\破甲\_dict_backup_20261122c'


def build_universe():
    """全库词头 → (文件名, 词条)，用于复用现成条目"""
    D = os.path.join(ROOT, 'public', 'dicts', 'en', 'word')
    uni = {}
    for fn in sorted(os.listdir(D)):
        if not fn.endswith('.json'):
            continue
        try:
            arr = json.load(open(os.path.join(D, fn), encoding='utf-8'))
        except Exception:
            continue
        for w in arr:
            if isinstance(w, dict) and w.get('word'):
                uni.setdefault(tw.head_key(str(w['word'])).lower(), (fn, w))
    return uni


def build_entry(word, cn, src, new_id):
    """造一条词条：复用源条目 or 新建"""
    if src is not None:
        e = copy.deepcopy(src)
        e['id'] = new_id
        e['word'] = word
        trans = e.get('trans') or []
        kept = [t for t in trans if (t.get('cn') or '').strip() != cn]
        pos = ''
        for t in kept:
            if (t.get('pos') or '').strip():
                pos = t['pos'].strip()
                break
        e['trans'] = [{'pos': pos, 'cn': cn}] + kept
        if not e.get('synos'):
            e['synos'] = [{'pos': pos, 'cn': cn, 'ws': []}]
        return e
    return {
        'id': new_id,
        'word': word,
        'phonetic0': '',
        'phonetic1': '',
        'synos': [{'pos': '', 'cn': cn, 'ws': []}],
        'etymology': None,
        'inflections': None,
        'e2e': None,
        'examsSrc': None,
        'relWords': {'rels': []},
        'langType': 'en',
        'trans': [{'pos': '', 'cn': cn}],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='真正写回词库')
    ap.add_argument('--only', help='只处理某册（逗号分隔）')
    args = ap.parse_args()

    only = args.only.split(',') if args.only else None
    uni = build_universe()
    universe_keys = set(uni.keys())
    print(f'全库索引：{len(uni)} 个唯一词头')

    # 全库最大 id
    D = os.path.join(ROOT, 'public', 'dicts', 'en', 'word')
    max_id = 0
    for fn in os.listdir(D):
        if not fn.endswith('.json'):
            continue
        try:
            arr = json.load(open(os.path.join(D, fn), encoding='utf-8'))
        except Exception:
            continue
        for w in arr:
            if isinstance(w, dict) and isinstance(w.get('id'), int):
                max_id = max(max_id, w['id'])
    next_id = max_id + 1
    print('起始 id:', next_id)

    if args.apply and os.path.isdir(BACKUP):
        shutil.rmtree(BACKUP)
    os.makedirs(BACKUP, exist_ok=True)

    total_new = 0
    for bid in tw.etw['DICT_FILES']:
        if only and bid not in only:
            continue
        path = tw.dict_path(bid)
        arr, raw = load_preserve(path)
        book_keys = {tw.head_key(str(w.get('word', '')).strip()).lower()
                     for w in arr if isinstance(w, dict) and w.get('word')}
        gaps = tw.gaps_of(bid, book=arr, dict_keys=book_keys, universe_keys=universe_keys)
        if not gaps:
            print(f'{bid}: 无缺口')
            continue

        # 复用全库条目
        entries = []
        for h, cn in gaps:
            src = uni.get(tw.head_key(h).lower())
            e = build_entry(h, cn, src[1] if src else None, next_id)
            next_id += 1
            entries.append((h, cn, e, src[0] if src else None))

        # 插入位置：按课本词表顺序，找该词的前一个词（且已在词库）
        order, _heads = tw.heads_of(bid)
        pos_in_order = {h: i for i, h in enumerate(order)}
        book_index = {}
        for i, w in enumerate(arr):
            if isinstance(w, dict) and w.get('word'):
                book_index.setdefault(tw.head_key(str(w['word'])).lower(), i)

        pending = {}   # anchor_index -> [entry]
        orphan = []
        for h, cn, e, srcfn in entries:
            k = tw.head_key(h).lower()
            anchor = None
            for j in range(pos_in_order.get(h, 0) - 1, -1, -1):
                pj = tw.head_key(order[j]).lower()
                if pj in book_index:
                    anchor = book_index[pj]
                    break
            if anchor is None:
                orphan.append(e)
            else:
                pending.setdefault(anchor, []).append(e)

        new_arr = []
        for i, w in enumerate(arr):
            new_arr.append(w)
            for e in pending.get(i, []):
                new_arr.append(e)
        new_arr.extend(orphan)

        if args.apply:
            shutil.copy2(path, os.path.join(BACKUP, os.path.basename(path)))
            data = dump_like(raw, new_arr)
            with open(path, 'wb') as f:
                f.write(data)
        reuse = sum(1 for e in entries if e[3])
        print(f'{bid}: 补 {len(entries)} 条（复用 {reuse} / 新建 {len(entries)-reuse}）'
              f' → 词库 {len(arr)} → {len(new_arr)}'
              + ('' if args.apply else '  [未写回]'))
        for h, cn, e, srcfn in entries[:6]:
            print(f'    + {h:26s} {cn[:26]:28s} ← {srcfn or "新建"}')
        if len(entries) > 6:
            print(f'    ... 共 {len(entries)} 条')
        total_new += len(entries)

    print('-' * 60)
    print(f'合计补 {total_new} 条' + ('（已写回）' if args.apply else '（未写回，加 --apply 才写）'))


if __name__ == '__main__':
    main()
