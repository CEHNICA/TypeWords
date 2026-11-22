import os, json, sys
ROOT = r'C:\Users\17321\Documents\破甲\typewords-src'
BK = r'C:\Users\17321\Documents\破甲\_dict_backup_20261122'
FILES = ['LWXX-3-1','LWXX-3-2','LWXX-4-1','LWXX-4-2','LWXX-5-1','LWXX-5-2',
         'LWCZ-6-1','LWCZ-6-2','LWCZ-7-1','LWCZ-7-2','LWCZ-8-1','LWCZ-8-2','LWCZ-9-1']
bad = 0
for f in FILES:
    old = open(os.path.join(BK, f + '.json'), 'rb').read()
    new = open(os.path.join(ROOT, 'public', 'dicts', 'en', 'word', f + '.json'), 'rb').read()
    def feat(b):
        bom = b[:3] == b'\xef\xbb\xbf'
        body = b[3:] if bom else b
        crlf = b'\r\n' in b[:4000]
        compact = body[:1] != b'\n'
        return dict(bom=bom, crlf=crlf, compact=compact,
                    tail_nl=b.endswith(b'\n'), nlines=b.count(b'\n'))
    fo, fn = feat(old), feat(new)
    ok = (fo['bom'] == fn['bom'] and fo['crlf'] == fn['crlf'] and
          fo['compact'] == fn['compact'] and fo['tail_nl'] == fn['tail_nl'])
    try:
        a = json.loads(old.decode('utf-8-sig'))
        b = json.loads(new.decode('utf-8-sig'))
        same_n = len(a) == len(b)
        changed = sum(1 for x, y in zip(a, b) if x != y)
        # 词头顺序必须完全一致
        same_order = all(x.get('word') == y.get('word') for x, y in zip(a, b))
    except Exception as e:
        same_n = same_order = False
        changed = -1
        print('PARSE FAIL', f, e)
    if not (ok and same_n and same_order):
        bad += 1
    print(f'{f}: 格式{"OK" if ok else "变了!"} 旧{fo} 新{fn} 条数{len(a) if same_n else "?"} '
          f'改动词条 {changed} 词头顺序{"一致" if same_order else "不一致!"}')
print('-' * 40)
print('格式破坏册数:', bad)
sys.exit(1 if bad else 0)
