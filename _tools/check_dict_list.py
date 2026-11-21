#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
词典列表体检器（尺子）
=================================================
检查 `public/list/word.json` 这份「本地补全的词库索引」有没有毛病，
重点是「六年级到九年级」的单词课本册能不能被一眼看到。

背景（2026-11-21 实测）：
  * 词库数据本身是全的 —— 207 册，一册不缺。
  * 但 `/dict-list` 的分组组件 `DictGroup.vue` 默认只显示第一个 tag 页签
    （`currentTag = tagList[0]`），于是「青少年英语」分类默认停在「通用」，
    只露 4 本高考/中考词，六到九年级的 PEP/外研/冀教课本册全藏在别的页签后面。
    → 用户以为「六到九年级的单词没弄上」。

修法走数据层：给六~九年级课本册打上专属 tag「六~九年级」，并让它成为
该分类的第一个 tag 页签，组内按 (年级, 册序, 教材) 排序。

怎么跑：
    python _tools/check_dict_list.py
    python _tools/check_dict_list.py --http     # 顺便校验本地服务能取到同一份文件
    python _tools/check_dict_list.py --json     # 机器可读输出
"""
import argparse
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD_JSON = os.path.join(ROOT, 'public', 'list', 'word.json')
DICT_DIR = os.path.join(ROOT, 'public', 'dicts', 'en', 'word')

TAG = '六~九年级'          # 本轮新增的分类 tag
CAT_YOUNG = '青少年英语'
CAT_LAIWU = '莱芜五·四制课本'

# 教材归类：靠 name 里的关键词，别靠 id 硬编码
TEXTBOOK_RULES = [
    # (判定函数名, 教材序, 教材名)
    ('新外研', 4, '新外研版'),
    ('外研新起点', 3, '外研新起点'),
    ('外研', 2, '外研版'),
    ('新起点', 1, '人教版新起点'),
    ('人教版', 0, '人教版PEP'),
    ('冀教', 5, '冀教版'),
    ('牛津', 7, '牛津版'),   # 「上海初中牛津词汇」先认牛津，别让「上海」截胡
    ('上海', 6, '上海版'),
]

CN_NUM = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9}

PEP_EN_NAMES = {'san1', 'san2', 'si1', 'si2', 'wu1', 'wu2',
                'liu1', 'liu2', 'qi1', 'qi2', 'ba1', 'ba2', 'jiu'}

RE_CN_GRADE = re.compile(r'([一二三四五六七八九])\s*年级\s*(全一册|上|下)?')
RE_JJ_GRADE = re.compile(r'冀教\s*([1-9])\s*(上|下)')
RE_DIGIT_GRADE = re.compile(r'([1-9])\s*年级\s*(上|下)')

# 小学 / 初中 / 高中划分用的「不属于六~九年级」黑名单关键词
HIGH_SCHOOL = '高中'
NON_TEXTBOOK_TAGS = {'通用', '新概念英语', '其他'}


class Checker:
    def __init__(self):
        self.results = []          # (ok, name, detail)

    def check(self, ok, name, detail=''):
        self.results.append((bool(ok), name, detail))
        return bool(ok)

    @property
    def failed(self):
        return [r for r in self.results if not r[0]]

    def report(self):
        for ok, name, detail in self.results:
            mark = 'PASS' if ok else 'FAIL'
            line = '[%s] %s' % (mark, name)
            if detail and not ok:
                line += '  ->  ' + detail
            print(line)
        print('-' * 60)
        print('共 %d 项，通过 %d，失败 %d' %
              (len(self.results), len(self.results) - len(self.failed), len(self.failed)))
        return len(self.failed)


def parse_grade(name):
    """从册子名里解析 (年级, 册序)。册序：上=1 下=2 全一册/单册=0。"""
    m = RE_JJ_GRADE.search(name)
    if m:
        return int(m.group(1)), (1 if m.group(2) == '上' else 2)
    m = RE_CN_GRADE.search(name)
    if m:
        vol = {'上': 1, '下': 2}.get(m.group(2), 0)
        return CN_NUM[m.group(1)], vol
    m = RE_DIGIT_GRADE.search(name)
    if m:
        return int(m.group(1)), (1 if m.group(2) == '上' else 2)
    return None


def parse_textbook(name, en_name=''):
    """从册子名/缩写里解析教材 (教材序, 教材名)，认不出来返回 None。

    人教 PEP 的册子名只有「六年级上」这种光秃秃的名字，认不出「人教版」三个字，
    只能靠 enName 认。
    """
    if en_name in PEP_EN_NAMES:
        return 0, '人教版PEP'
    if isinstance(en_name, str) and en_name.startswith('pep-sl-'):
        return 1, '人教版新起点'
    for keyword, order, label in TEXTBOOK_RULES:
        if keyword in name:
            return order, label
    return None


def group_by_tags(books):
    """复刻 app/pages/(words)/dict-list.vue 的 groupByDictTags：
    按数组顺序遍历，每册 push 进它『所有』tag 的桶里；桶的 key 顺序 = 首次出现顺序。"""
    result = {}
    for b in books:
        for t in b.get('tags') or []:
            result.setdefault(t, []).append(b)
    return result


def load_word_json(path):
    with open(path, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8')
    return json.loads(text), raw, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--http', action='store_true', help='顺便校验本地服务返回同一份文件')
    ap.add_argument('--json', action='store_true', help='机器可读输出')
    args = ap.parse_args()

    c = Checker()

    # ---------- 0. 文件基本形态 ----------
    if not os.path.exists(WORD_JSON):
        print('[FAIL] word.json 存在  ->  找不到 %s' % WORD_JSON)
        print('共 1 项，通过 0，失败 1')
        return 1
    try:
        data, raw, text = load_word_json(WORD_JSON)
    except Exception as e:
        print('[FAIL] word.json 可解析为 JSON  ->  %s' % e)
        print('共 1 项，通过 0，失败 1')
        return 1
    c.check(True, 'word.json 存在且可解析为 JSON 数组')
    c.check(isinstance(data, list), 'word.json 是数组', '实际类型 %s' % type(data).__name__)

    # 格式：2 空格缩进 / 无 BOM / 末尾换行
    # 行尾：仓库没钉 eol，Windows 上 git checkout 会把工作区变成 CRLF（core.autocrlf=true），
    # 那不是缺陷，所以按「行尾统一」查，而不是硬钉 LF；内容比对前先归一化。
    c.check(not raw.startswith(b'\xef\xbb\xbf'), 'word.json 无 BOM')
    mixed = (b'\r\n' in raw) and (raw.replace(b'\r\n', b'').count(b'\n') > 0)
    c.check(not mixed, 'word.json 行尾统一（不混用 CRLF/LF）',
            '同时出现 CRLF 和裸 LF')
    norm = text.replace('\r\n', '\n')
    c.check(norm.endswith('\n'), 'word.json 末尾有换行')
    expect = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    c.check(norm == expect, 'word.json 格式 = 2 空格缩进 JSON',
            '与 json.dumps(indent=2) 不一致（可能是被别的工具重写过）')

    # ---------- 1. 册子总量 / 完整性 ----------
    ids = [b.get('id') for b in data]
    c.check(len(ids) == len(set(ids)), '词库 id 无重复', '重复 id: %s' %
            sorted({i for i in ids if ids.count(i) > 1}))
    by_cat = {}
    for b in data:
        by_cat.setdefault(b.get('category'), []).append(b)
    c.check(len(data) == 207, '词库总册数 = 207', '实际 %d' % len(data))
    c.check(len(by_cat.get(CAT_YOUNG, [])) == 106, '青少年英语分类 106 册',
            '实际 %d' % len(by_cat.get(CAT_YOUNG, [])))
    c.check(len(by_cat.get(CAT_LAIWU, [])) == 13, '莱芜课本分类 13 册',
            '实际 %d' % len(by_cat.get(CAT_LAIWU, [])))

    # 每个册子的词库文件都在盘且非空
    missing, empty = [], []
    for b in data:
        url = b.get('url') or ''
        fname = url.rsplit('/', 1)[-1]
        p = os.path.join(DICT_DIR, fname)
        if not os.path.exists(p):
            missing.append('%s(%s)' % (b.get('name'), fname))
        elif os.path.getsize(p) == 0:
            empty.append('%s(%s)' % (b.get('name'), fname))
    c.check(not missing, '207 册词库文件全部存在', '缺: %s' % ', '.join(missing[:8]))
    c.check(not empty, '207 册词库文件全部非空', '空: %s' % ', '.join(empty[:8]))

    # ---------- 2. 青少年英语：六~九年级课本册 ----------
    young = by_cat.get(CAT_YOUNG, [])
    grouped = group_by_tags(young)
    tag_keys = list(grouped.keys())

    c.check(TAG in grouped, '青少年英语分类存在 tag「%s」' % TAG,
            '现有 tag: %s' % ', '.join(tag_keys))
    c.check(bool(tag_keys) and tag_keys[0] == TAG,
            '「%s」是青少年英语的第一个 tag 页签（默认可见）' % TAG,
            '第一个页签是「%s」' % (tag_keys[0] if tag_keys else '(无)'))

    tagged = grouped.get(TAG, [])
    c.check(len(tagged) == 30, '「%s」组共 30 册' % TAG, '实际 %d' % len(tagged))

    # 组内顺序：按 (年级, 册序, 教材序) 严格递增
    def sort_key(b):
        name = b.get('name') or ''
        g = parse_grade(name)
        tb = parse_textbook(name, b.get('enName'))
        if b.get('enName') == 'SHjuniormiddleOxford':      # 上海初中牛津词汇 = 初中通用
            g = (6, 0)
        if g is None or tb is None:
            return (99, 99, 99)
        return (g[0], g[1], tb[0])

    keys = [sort_key(b) for b in tagged]
    c.check(keys == sorted(keys), '「%s」组内按 年级→册序→教材 排好序' % TAG,
            '实际顺序: %s' % ', '.join('%s(%s)' % (b.get('name'), sort_key(b)) for b in tagged))

    # 六~九年级覆盖：每年级至少 3 册、至少 3 种教材
    grades = {}
    for b in tagged:
        g = parse_grade(b.get('name') or '')
        if g is None and b.get('enName') == 'SHjuniormiddleOxford':
            g = (6, 0)
        if g:
            grades.setdefault(g[0], []).append(b)
    for gi in (6, 7, 8, 9):
        books = grades.get(gi, [])
        c.check(len(books) >= 3, '六~九年级课本册覆盖 %d 年级（≥3 册）' % gi,
                '实际 %d 册' % len(books))
        tbs = {parse_textbook(b.get('name') or '', b.get('enName'))[1] for b in books
               if parse_textbook(b.get('name') or '', b.get('enName'))}
        c.check(len(tbs) >= 2, '%d 年级覆盖 ≥2 种教材' % gi,
                '实际教材: %s' % ', '.join(sorted(tbs)))

    # 每一册确实带 tag，且 tag 在数组第 0 位（否则不是第一个页签）
    bad_pos = [b.get('name') for b in tagged if not b.get('tags') or b['tags'][0] != TAG]
    c.check(not bad_pos, '每册「%s」tag 都排在 tags[0]' % TAG, '异常: %s' % ', '.join(bad_pos[:6]))

    # 不该被打标的册子
    for b in young:
        name = b.get('name') or ''
        tags = b.get('tags') or []
        if TAG in tags:
            g = parse_grade(name)
            tb = parse_textbook(name, b.get('enName'))
            ok = (g is not None and 6 <= g[0] <= 9) or b.get('enName') == 'SHjuniormiddleOxford'
            c.check(ok, '「%s」不该被打 tag：%s' % (TAG, name), '实际打了')
    high = [b.get('name') for b in young if HIGH_SCHOOL in (b.get('name') or '') and TAG in (b.get('tags') or [])]
    c.check(not high, '高中课本册没有被误打进「%s」' % TAG, ', '.join(high[:6]))
    nontext = [b.get('name') for b in young
               if set(b.get('tags') or []) & NON_TEXTBOOK_TAGS and TAG in (b.get('tags') or [])]
    c.check(not nontext, '通用/新概念/其他 册没有被误打进「%s」' % TAG, ', '.join(nontext[:6]))
    other_cat = [b.get('name') for b in data
                 if b.get('category') != CAT_YOUNG and TAG in (b.get('tags') or [])]
    c.check(not other_cat, '其它分类没有被误打「%s」' % TAG, ', '.join(other_cat[:6]))

    # tags 自身无重复
    dup = [b.get('name') for b in data if len(set(b.get('tags') or [])) != len(b.get('tags') or [])]
    c.check(not dup, '每册 tags 内部无重复', ', '.join(dup[:6]))

    # ---------- 3. 莱芜课本：六~九年级 7 册 ----------
    laiwu = by_cat.get(CAT_LAIWU, [])
    lw_grouped = group_by_tags(laiwu)
    c.check('课本词汇' in lw_grouped, '莱芜分类存在「课本词汇」tag')
    lw_all = lw_grouped.get('课本词汇', [])
    c.check(len(lw_all) == 13, '莱芜「课本词汇」组 13 册', '实际 %d' % len(lw_all))
    lw_junior = [b for b in lw_all if parse_grade(b.get('name') or '')
                 and parse_grade(b.get('name') or '')[0] >= 6]
    c.check(len(lw_junior) == 7, '莱芜六年级到九年级 7 册齐备', '实际 %d' % len(lw_junior))
    lw_keys = [sort_key(b) for b in lw_all]
    c.check(lw_keys == sorted(lw_keys), '莱芜「课本词汇」组内按年级排好序',
            ', '.join(b.get('name') for b in lw_all))

    # ---------- 4. 线上/本地服务一致性（可选） ----------
    if args.http:
        try:
            with urllib.request.urlopen('http://localhost:5567/list/word.json', timeout=15) as resp:
                served = json.loads(resp.read().decode('utf-8'))
            c.check(served == data, '本地服务 /list/word.json 与磁盘一致')
            s_grouped = group_by_tags([b for b in served if b.get('category') == CAT_YOUNG])
            sk = list(s_grouped.keys())
            c.check(bool(sk) and sk[0] == TAG, '本地服务返回的青少年英语首个页签是「%s」' % TAG,
                    '实际「%s」' % (sk[0] if sk else '(无)'))
        except Exception as e:
            c.check(False, '本地服务 /list/word.json 可取且一致', str(e))

    if args.json:
        print(json.dumps({
            'total': len(data),
            'young': len(young),
            'tag': TAG,
            'tagged_count': len(tagged),
            'tag_order': [b.get('name') for b in tagged],
            'failed': len(c.failed),
        }, ensure_ascii=False, indent=2))

    return 1 if c.report() else 0


if __name__ == '__main__':
    sys.exit(main())
