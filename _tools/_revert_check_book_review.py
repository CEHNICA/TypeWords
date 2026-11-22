"""退回验证：故意把一个词的释义改坏，看浏览器尺子能不能红；然后原样恢复。

用法：
  python _tools/_revert_check_book_review.py break   # 改坏
  python _tools/_revert_check_book_review.py restore # 恢复
"""
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DICT = os.path.join(ROOT, 'public', 'dicts', 'en', 'word', 'LWXX-5-1.json')
SAVE = DICT + '.revertsave'
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from json_io import dump_like  # noqa: E402

TARGET = 'Teachers’ Day'
BAD = '教师节【故意改坏】'


def load():
    with open(DICT, 'rb') as f:
        raw = f.read()
    return raw, json.loads(raw.decode('utf-8-sig'))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'break':
        raw, arr = load()
        hit = 0
        for w in arr:
            if w.get('word') == TARGET:
                if not w.get('trans'):
                    w['trans'] = [{}]
                w['trans'][0]['cn'] = BAD
                hit += 1
        assert hit == 1, '目标词条命中 %d 次' % hit
        with open(SAVE, 'wb') as f:
            f.write(raw)
        with open(DICT, 'wb') as f:
            f.write(dump_like(raw, arr))
        print('已改坏 %s → %s（原文件备份在 %s）' % (TARGET, BAD, SAVE))
    elif mode == 'restore':
        shutil.copyfile(SAVE, DICT)
        os.remove(SAVE)
        print('已恢复')
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
