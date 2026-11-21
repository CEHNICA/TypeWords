#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TypeWords「水平摸底测试」体检器
================================
维度：这个功能是不是真的能用（阶梯数据有效 / 自适应逻辑在 / 报告能出 / 入口在）。

用法：
    python _tools/check_placement.py            # 静态体检
    python _tools/check_placement.py --http     # 静态体检 + 打本地 dev server

退出码 0 = 全绿；1 = 有缺陷（每条缺陷精确红在自己那条上）。
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("TW_BASE_URL", "http://localhost:5567")

PLACEMENT_DATA = os.path.join(ROOT, "app", "core", "data", "placement.ts")
PAGE_VUE = os.path.join(ROOT, "app", "pages", "(words)", "placement-test.vue")
WORDS_VUE = os.path.join(ROOT, "app", "pages", "(words)", "words.vue")
WORD_LIST = os.path.join(ROOT, "public", "list", "word.json")
DICT_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def parse_ladder_steps(src):
    """从 placement.ts 里抽出所有 { label: 'xxx', ids: [..] } 块"""
    steps = []
    for m in re.finditer(r"label:\s*'([^']+)'\s*,\s*ids:\s*\[([^\]]*)\]", src):
        ids = [int(x) for x in re.findall(r"\d+", m.group(2))]
        steps.append((m.group(1), ids))
    return steps


def parse_ladder_names(src):
    return re.findall(r"key:\s*'([^']+)'\s*,\s*\n\s*name:\s*'([^']+)'", src)


def split_ladder_blocks(src):
    """按顶层 ladder 块（两空格缩进的 '{'）切分"""
    return re.split(r"\n  \{\n", src)[1:]


# ---------------------------------------------------------------- 1. 阶梯数据
def check_ladder_data():
    if not os.path.exists(PLACEMENT_DATA):
        check("阶梯数据文件存在（app/core/data/placement.ts）", False, "文件不存在")
        return
    src = read(PLACEMENT_DATA)

    ladders = parse_ladder_names(src)
    check(
        "至少准备了 4 套教材阶梯",
        len(ladders) >= 4,
        "现在只有 %d 套：%s" % (len(ladders), [n for _, n in ladders]),
    )

    steps = parse_ladder_steps(src)
    check(
        "阶梯级别数量足够（>=8 级才能定位到具体年级）",
        len(steps) >= 8,
        "只解析出 %d 级" % len(steps),
    )

    # 每个 id 都必须在 /list/word.json 里存在
    if not os.path.exists(WORD_LIST):
        check("词库清单存在（public/list/word.json）", False, "文件不存在")
        return
    with open(WORD_LIST, "r", encoding="utf-8") as f:
        word_list = json.load(f)
    known = {int(it.get("id")): it for it in word_list}

    missing = []
    for label, ids in steps:
        for i in ids:
            if i not in known:
                missing.append("%s -> id %s" % (label, i))
    check(
        "阶梯引用的词库 id 全部真实存在",
        not missing,
        "不存在的 id：" + "; ".join(missing),
    )

    # 词库文件本身也得在磁盘上
    missing_files = []
    for label, ids in steps:
        for i in ids:
            info = known.get(i)
            if not info:
                continue
            p = os.path.join(DICT_DIR, info.get("url") or "")
            if not os.path.exists(p):
                missing_files.append("%s(%s)" % (label, info.get("url")))
    check(
        "阶梯引用的词库文件都在磁盘上",
        not missing_files,
        "缺文件：" + "; ".join(missing_files),
    )

    # 阶梯必须按 id 递增（年级越高越难）
    bad_order = []
    for block in split_ladder_blocks(src):
        key_m = re.search(r"key:\s*'([^']+)'", block)
        if not key_m:
            continue
        key = key_m.group(1)
        ids_in_step = [
            [int(x) for x in re.findall(r"\d+", g)]
            for g in re.findall(r"ids:\s*\[([^\]]*)\]", block)
        ]
        # 同一级可能合并多本词表（如「新起点 + PEP」），按每级最大 id 判定难度递进
        level_max = [max(g) for g in ids_in_step if g]
        if level_max != sorted(level_max):
            bad_order.append(key)
    check(
        "同一套阶梯的难度逐级递进（每级最大词库 id 递增）",
        not bad_order,
        "顺序乱的阶梯：" + ", ".join(bad_order),
    )


# ---------------------------------------------------------------- 2. 页面
def check_page():
    if not os.path.exists(PAGE_VUE):
        check("摸底页面存在（app/pages/(words)/placement-test.vue）", False, "文件不存在")
        return
    src = read(PAGE_VUE)

    check(
        "页面接上了阶梯数据",
        "PLACEMENT_LADDERS" in src,
        "没引用 PLACEMENT_LADDERS",
    )

    check(
        "题型复用现成的 buildQuestion（英文选中文释义）",
        "buildQuestion" in src,
        "没用 buildQuestion，题型会和别处不一致",
    )

    check(
        "自适应升降级逻辑在（答对升级 / 答错降级）",
        re.search(r"level\s*\+\s*PLACEMENT_STEP_JUMP", src) is not None
        and re.search(r"level\s*-\s*PLACEMENT_STEP_JUMP", src) is not None,
        "找不到升降级逻辑",
    )

    check(
        "有词汇量估计",
        re.search(r"estimate|词汇量", src) is not None,
        "报告里没有词汇量估计",
    )

    check(
        "有成绩报告（定位结论 + 明细）",
        re.search(r"report|定位|水平", src, re.I) is not None,
        "没有报告页",
    )

    check(
        "错词可以导出 CSV（给老师看）",
        re.search(r"csv", src, re.I) is not None and "download" in src,
        "没有 CSV 导出",
    )

    check(
        "错词能进错词本",
        re.search(r"wrong\.words", src) is not None,
        "错词没进错词本",
    )

    check(
        "题目释义做了精简（小学词库释义太长，读不完）",
        re.search(r"shortTrans|shortMeaning|trimTrans", src) is not None,
        "释义没精简，低年级孩子读不动",
    )

    check(
        "未作答不许跳题（跳过去这题就不算成绩了）",
        re.search(r"if\s*\(\s*submitted\s*\)\s*advance\(\)", src) is not None,
        "下一题快捷键在没作答时也会跳，会漏记一题",
    )

    check(
        "一题未答的报告有兜底文案",
        "没有作答记录" in src,
        "空报告会出现「约 三年级上 水平」这种胡说八道",
    )


# ---------------------------------------------------------------- 2b. 逐级诊断 + 本地教材
def check_sweep_and_local_ladders():
    """新增需求：① 用户自己那套本地课本（莱芜/鲁教版）要能用
    ② 要能「每个年级都摸一遍」（逐级诊断）"""
    data = read(PLACEMENT_DATA) if os.path.exists(PLACEMENT_DATA) else ""
    page = read(PAGE_VUE) if os.path.exists(PAGE_VUE) else ""

    # ① 莱芜（山东五四制，俗称鲁教版）必须有，且级数够
    lw_ids = []
    for block in split_ladder_blocks(data):
        if re.search(r"key:\s*'lw'", block):
            for g in re.findall(r"ids:\s*\[([^\]]*)\]", block):
                lw_ids.append([int(x) for x in re.findall(r"\d+", g)])
    check(
        "本地教材阶梯「莱芜小学五四」在（用户自己录的那套课本）",
        len(lw_ids) >= 6,
        "没找到 key='lw' 的阶梯",
    )
    check(
        "莱芜阶梯覆盖三上→六下（每学段都在）",
        len(lw_ids) >= 8 and all(len(g) > 0 for g in lw_ids),
        "级数只有 %d 级" % len(lw_ids),
    )

    # ② 逐级诊断
    check(
        "有「逐级诊断」测法（每个年级都测一遍）",
        "sweep" in page,
        "页面里找不到 sweep 模式",
    )
    check(
        "逐级诊断能设置每级题量",
        re.search(r"perLevel", page) is not None and re.search(r"题/级", page) is not None,
        "没有每级题量的选项",
    )
    check(
        "逐级诊断出年表（每个年级一行 + 掌握率）",
        re.search(r"sweepReport", page) is not None
        and re.search(r"rows", page) is not None
        and re.search(r"rate", page) is not None,
        "没有年表报告",
    )
    check(
        "年表能指出断层（掌握率低于 60% 的那一级）",
        re.search(r"weak", page) is not None and re.search(r"60", page) is not None,
        "没有断层判断",
    )
    check(
        "逐级诊断不会降级（升到下一级就回不去了）",
        re.search(r"isSweep\(\)", page) is not None,
        "逐级模式没有独立分支",
    )
    check(
        "没有断层时报告显示「无断层」而不是「全过」（跟「断层在这一级」标题不打架）",
        re.search(r"weak\?\.label \|\| '无断层'", page) is not None,
        "断层那一格显示「全过」，和标题「断层在这一级」语义矛盾",
    )


# ---------------------------------------------------------------- 2c. 残缺词条防御
def check_broken_word_guard():
    """小学词库里有一批词条缺 relWords.rels（如 I'm / Harbin），
    上游 buildQuestion 直接访问会崩 → 整道题渲染不出来。必须有防御。"""
    wt = os.path.join(ROOT, "app", "core", "utils", "word-test.ts")
    page = read(PAGE_VUE) if os.path.exists(PAGE_VUE) else ""
    if not os.path.exists(wt):
        check("出题工具存在（app/core/utils/word-test.ts）", False, "文件不存在")
        return
    src = read(wt)
    check(
        "buildQuestion 对残缺词条有防御（relWords.rels 缺失不崩）",
        re.search(r"relsOf|relWords\?\.rels", src) is not None,
        "词条缺 relWords.rels 时会 TypeError，整道题渲染不出来",
    )
    check(
        "buildQuestion 对缺失 trans 有防御",
        re.search(r"Array\.isArray\([^)]*trans", src) is not None,
        "词条缺 trans 时会崩",
    )
    check(
        "摸底页清洗词条结构（trans / relWords.rels 补齐）",
        re.search(r"sanitizeWord", page) is not None,
        "没清洗，进错词本后词条详情页也会崩",
    )


# ---------------------------------------------------------------- 2d. 逐级诊断词汇量口径
def check_sweep_estimate():
    """逐级诊断的「估算词汇量」必须走累计口径：
    不能把各级词表词数直接求和——小学各册之间大量重复词会被重复计入，虚高。
    另外 total/right 必须在 estimate 之前声明（const 有 TDZ，否则报告页直接 ReferenceError）。"""
    page = read(PAGE_VUE) if os.path.exists(PAGE_VUE) else ""
    if not page:
        check("摸底页面存在（app/pages/(words)/placement-test.vue）", False, "文件不存在")
        return
    m = re.search(r"function sweepReport\(\)\s*\{(.*?)\n\}", page, re.S)
    body = m.group(1) if m else ""
    check(
        "逐级诊断词汇量按累计口径折算（用 levels[].cumulative）",
        "cumulative" in body and "levels[weak.index" in body,
        "还在按各级词数直接求和，小学各册重复词会被重复计入，估算偏高",
    )
    check(
        "逐级诊断不再用 rows.reduce 直接累加各级词数",
        re.search(r"rows\.reduce\([^)]*words", body) is None,
        "还有 rows.reduce(... words ...) 这种重复计数写法",
    )
    if body:
        ti = body.find("const total")
        ei = body.find("let estimate")
        check(
            "sweepReport 里 total 先于 estimate 声明（避免 const TDZ 报错）",
            ti != -1 and ei != -1 and ti < ei,
            "estimate 用到了后面才声明的 total，报告页会 ReferenceError",
        )
    else:
        check("sweepReport 里 total 先于 estimate 声明（避免 const TDZ 报错）", False, "找不到 sweepReport 函数体")


# ---------------------------------------------------------------- 3. 入口
def check_entry():
    if not os.path.exists(WORDS_VUE):
        check("单词页存在", False, "文件不存在")
        return
    src = read(WORDS_VUE)
    check(
        "/words 页有摸底测试入口",
        "placement-test" in src,
        "找不到摸底测试入口，用户不知道这个功能存在",
    )


# ---------------------------------------------------------------- 4. HTTP
def check_http():
    try:
        req = urllib.request.Request(BASE_URL + "/placement-test", headers={"User-Agent": "check-placement"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "ignore")
            check(
                "HTTP: /placement-test 路由可访问（SSR 200）",
                r.status == 200,
                "状态 %s" % r.status,
            )
            check(
                "HTTP: 摸底页 SSR 出标题",
                "摸底" in body,
                "页面正文里没有「摸底」字样",
            )
    except Exception as e:  # noqa: BLE001
        check("HTTP: /placement-test 路由可访问（SSR 200）", False, "请求失败：%s" % e)


def main():
    check_ladder_data()
    check_page()
    check_sweep_and_local_ladders()
    check_broken_word_guard()
    check_sweep_estimate()
    check_entry()
    if "--http" in sys.argv:
        check_http()

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print("%s %s%s" % ("[PASS]" if ok else "[FAIL]", name, ("  -> " + detail) if (detail and not ok) else ""))
    print("\n合计 %d 项，失败 %d 项" % (len(results), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
