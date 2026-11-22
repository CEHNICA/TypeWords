#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""新旧 merge_continuations 对拍：改抽取逻辑后有没有漏掉真词 / 多出垃圾词。

**必须用模块自己的 entry_alts**（之前诊断脚本自己抄了一份词头抽取逻辑，
  模块改了剥括号/剥私用区字符的规则，尺子却没跟上 → 对拍结论全是假的）。

基线口径 = v2（old_merge）；当前口径 = 模块里的 merge_continuations。
判读：小学册 lost 必须为 0；初中 LOST 只允许是页眉/附录裸词/PDF 残片；
GAIN 必须是真词。

用法：python _tools/_check_wordsheet_diff.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

import pymupdf
import _textbook_wordsheet as tw


def old_merge(lines):
    """v2 口径（原样复制）"""
    out = []
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if tw.NOISE_LINE.match(s):
            continue
        if tw.CJK.match(s) or (tw.CONT_POS.match(s) and tw.CJK.search(s)):
            if tw.HEADING_CN.match(s):
                continue
            if out:
                out[-1] += s
            continue
        out.append(s)
    return out


def heads_from_merged(mode, merged):
    order, heads = [], {}
    for line in merged:
        pieces = [line] if mode == 'primary' else \
            [x.strip() for x in re.split(r'p\.?\s*\d+', line) if x.strip()]
        for piece in pieces:
            for alt, cn2 in tw.entry_alts(piece):
                if alt not in heads:
                    heads[alt] = cn2
                    order.append(alt)
    return order, heads


for bid in sorted(tw.etw['PDFS']):
    doc = pymupdf.open(os.path.join(tw.etw['PDF_DIR'], tw.etw['PDFS'][bid]))
    start = tw.find_wordlist_start(doc)
    stream = []
    for i in range(start, doc.page_count):
        stream.extend(doc[i].get_text().splitlines())
    doc.close()
    mode = 'primary' if bid.startswith('LWXX') else 'junior'
    o_old, h_old = heads_from_merged(mode, old_merge(stream))
    o_new, h_new = heads_from_merged(mode, tw.merge_continuations(stream))
    lost = [x for x in o_old if x not in h_new]
    gained = [x for x in o_new if x not in h_old]
    print("===== %s  old=%d new=%d  lost=%d gained=%d"
          % (bid, len(h_old), len(h_new), len(lost), len(gained)))
    if lost:
        print("   LOST :", lost[:40])
    if gained:
        print("   GAIN :", gained[:40])
