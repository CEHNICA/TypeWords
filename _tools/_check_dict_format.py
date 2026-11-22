#!/usr/bin/env python
"""词库文件格式 / 结构校验（莱芜 13 册）

对每册检查两件事：
  1) **格式没被破坏** —— BOM / CRLF / compact 单行 / 末尾换行 与基线一致
     （基线 = 破甲\\_dict_backup_20261122，本项目开始动词库之前的原件）
  2) **只增不换序** —— 新词头序列里，旧词头必须原样按序出现
     （补词是「往里插」，不是重排；重排会让课本单元顺序丢掉）

词库 json 不进 git（.gitignore 排除 public/dicts/**），所以这个尺子是唯一的
结构护栏。写回后必跑。

用法: python _tools/_check_dict_format.py
退出码 0 = 全过。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 旧版词库备份目录（写盘前的手动备份）：可用环境变量 TW_DICT_BACKUP 覆盖
BK = os.environ.get('TW_DICT_BACKUP') or os.path.join(
    os.path.dirname(ROOT), '_dict_backup_20261122')
FILES = ['LWXX-3-1', 'LWXX-3-2', 'LWXX-4-1', 'LWXX-4-2', 'LWXX-5-1', 'LWXX-5-2',
         'LWCZ-6-1', 'LWCZ-6-2', 'LWCZ-7-1', 'LWCZ-7-2', 'LWCZ-8-1', 'LWCZ-8-2',
         'LWCZ-9-1']


def feat(b):
    bom = b[:3] == b'\xef\xbb\xbf'
    body = b[3:] if bom else b
    crlf = b'\r\n' in b[:4000]
    compact = body[:1] != b'\n'
    return dict(bom=bom, crlf=crlf, compact=compact, tail_nl=b.endswith(b'\n'))


def is_subsequence(small, big):
    """small 是否是 big 的子序列（保序）"""
    it = iter(big)
    return all(x in it for x in small)


bad = 0
for f in FILES:
    old = open(os.path.join(BK, f + '.json'), 'rb').read()
    new = open(os.path.join(ROOT, 'public', 'dicts', 'en', 'word', f + '.json'), 'rb').read()
    fo, fn = feat(old), feat(new)
    fmt_ok = (fo['bom'] == fn['bom'] and fo['crlf'] == fn['crlf']
              and fo['compact'] == fn['compact'] and fo['tail_nl'] == fn['tail_nl'])
    try:
        a = json.loads(old.decode('utf-8-sig'))
        b = json.loads(new.decode('utf-8-sig'))
        ow = [str(x.get('word')) for x in a]
        nw = [str(x.get('word')) for x in b]
        order_ok = is_subsequence(ow, nw)
        dup = len(nw) != len(set(nw))
        added = len(nw) - len(ow)
        lost = [w for w in ow if w not in set(nw)]
    except Exception as e:
        order_ok = dup = False
        added = -1
        lost = ['PARSE FAIL: %s' % e]
        print('PARSE FAIL', f, e)
    ok = fmt_ok and order_ok and not dup and not lost
    if not ok:
        bad += 1
    print(f'{f}: 格式{"OK" if fmt_ok else "变了!"} {fo["compact"]=} {fo["tail_nl"]=} '
          f'条数 {len(ow)} → {len(nw)}（新增 {added}）'
          f' 旧序保序{"是" if order_ok else "否!"}'
          f'{" 有重复词头!" if dup else ""}'
          f'{" 丢失:" + ",".join(lost[:5]) if lost else ""}')
print('-' * 40)
print('结构破坏册数:', bad)
sys.exit(1 if bad else 0)
