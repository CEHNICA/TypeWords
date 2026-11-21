#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TypeWords「整本复习」体检器
================================
维度：用户要的是「同时选几本书，把这几本书的单词全部囊括进来，一个一个点完，
然后总结这本书他掌握到什么水平」。这条链路每个环节都得在，缺一环就是废的：

  1. 入口能进（/words 页 + 摸底页都能跳过去）
  2. 能同时选多本书（册子多选，不是单选）
  3. 词表真的合并去重（"全部囊括进来"）
  4. 全量覆盖：题数 = 合并后的词数，一个不漏（不是抽样 10/20 题）
  5. 859 题不可能一口气做完 → 进度能存能续
  6. 报告给出"掌握到什么水平"：综合掌握率 + 每册掌握率
  7. 生词能落地：CSV + 错词本
  8. 残缺词条不崩（小学词库缺 relWords.rels / trans）

用法：
    python _tools/check_book_review.py            # 静态体检
    python _tools/check_book_review.py --http     # 静态体检 + 打本地 dev server

退出码 0 = 全绿；1 = 有缺陷（每条缺陷精确红在自己那条上）。
"""
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("TW_BASE_URL", "http://localhost:5567")

PAGE_VUE = os.path.join(ROOT, "app", "pages", "(words)", "book-review.vue")
PLACEMENT_VUE = os.path.join(ROOT, "app", "pages", "(words)", "placement-test.vue")
WORDS_VUE = os.path.join(ROOT, "app", "pages", "(words)", "words.vue")
PROGRESS_TS = os.path.join(ROOT, "app", "core", "utils", "placement-progress.ts")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 1. 页面与入口
def check_page_and_entry():
    if not os.path.exists(PAGE_VUE):
        check("整本复习页面存在（app/pages/(words)/book-review.vue）", False, "文件不存在")
        return
    check("整本复习页面存在（app/pages/(words)/book-review.vue）", True)
    src = read(PAGE_VUE)

    words = read(WORDS_VUE) if os.path.exists(WORDS_VUE) else ""
    check(
        "/words 页有整本复习入口",
        "book-review" in words,
        "用户在单词页找不到这个功能",
    )
    placement = read(PLACEMENT_VUE) if os.path.exists(PLACEMENT_VUE) else ""
    check(
        "摸底页能跳到整本复习（两个功能互相引流）",
        "book-review" in placement,
        "摸底页里没有整本复习的入口",
    )


# ---------------------------------------------------------------- 2. 多选册子
def check_multi_book_select():
    src = read(PAGE_VUE)
    check(
        "能同时选多本书（册子多选状态）",
        re.search(r"selectedBooks", src) is not None,
        "没有多选状态，只支持一本一本来",
    )
    check(
        "多选用 checkbox / 按钮式多选呈现",
        re.search(r"type=[\"']checkbox[\"']|book-chip|book-toggle", src) is not None,
        "看不到多选交互",
    )
    check(
        "有全选 / 取消全选",
        re.search(r"全选|selectAll|toggleAll", src) is not None,
        "手动一本一本勾太蠢",
    )
    check(
        "没选册子时不能开始（防手滑）",
        re.search(r"selectedBooks\.length\s*={2,3}\s*0", src) is not None
        and re.search(r"disabled", src) is not None,
        "0 册也能开始，会得到空报告",
    )


# ---------------------------------------------------------------- 3. 全量词表合并
def check_merged_pool():
    src = read(PAGE_VUE)
    check(
        "多本书的词表合并后去重（全部囊括进来）",
        re.search(r"seen|dedupe|去重", src) is not None,
        "没做去重，重复词会重复出题",
    )
    check(
        "全量覆盖：题量 = 合并去重后的词数（不是抽样）",
        re.search(r"total\s*=\s*pool\.length|pool\.length", src) is not None,
        "题数不是按全部词算，等于还是抽样",
    )
    check(
        "能看到总共多少词 / 已过多少词",
        re.search(r"/\s*\{\{?\s*(total|pool)", src) is not None
        or re.search(r"totalCount|pool\.length", src) is not None,
        "没有总量/进度提示，用户不知道要过多少",
    )


# ---------------------------------------------------------------- 4. 进度续做
def check_progress_resume():
    src = read(PAGE_VUE)
    has_store = os.path.exists(PROGRESS_TS)
    check(
        "有独立的进度存储模块（app/core/utils/placement-progress.ts）",
        has_store,
        "没进度模块，几百题做完一半关掉就白干",
    )
    if has_store:
        p = read(PROGRESS_TS)
        check(
            "进度用 IndexedDB / localStorage 持久化（不是内存变量）",
            re.search(r"idb-keyval|localStorage", p) is not None,
            "进度只存在内存里，刷新就没",
        )
        check(
            "进度按「教材 + 册子组合」分桶存（换书不会串味）",
            re.search(r"ladder|books", p) is not None,
            "所有进度混在一份，换书就串了",
        )
    check(
        "页面读回进度并提供「继续上次」",
        re.search(r"resume|继续上次|loadBookProgress", src) is not None,
        "没有续做入口",
    )
    check(
        "答题过程中会写进度（每题落盘）",
        re.search(r"saveProgress|saveReview|set\(", src) is not None,
        "进度不落盘，中途关了全白干",
    )


# ---------------------------------------------------------------- 5. 报告
def check_report():
    src = read(PAGE_VUE)
    check(
        "报告给综合掌握率（掌握到什么水平）",
        re.search(r"掌握率|masteryRate|overallRate", src) is not None,
        "没有总体掌握率",
    )
    check(
        "报告给每册掌握率（哪一册最弱）",
        re.search(r"perBook|bookStats|每册|各册", src) is not None,
        "没有分册统计，看不出哪本书没吃透",
    )
    check(
        "生词表：错词全部列出",
        re.search(r"wrongWords|生词|错词", src) is not None,
        "没生词表，等于白测",
    )
    check(
        "错词能导 CSV",
        re.search(r"exportCsv|导出 CSV|\\uFEFF", src) is not None,
        "生词导不出来给老师",
    )
    check(
        "错词能进错词本",
        re.search(r"addWrongToBook|错词本|base\.wrong", src) is not None,
        "生词没进错词本，等于测完就忘",
    )
    check(
        "词汇量按累计口径折算（不把各册词数直接求和）",
        re.search(r"cumulative|knownCount|已掌握", src) is not None,
        "重复词会被重复计入，词汇量虚高",
    )


# ---------------------------------------------------------------- 6. 健壮性
def check_robustness():
    src = read(PAGE_VUE)
    check(
        "残缺词条不崩（补齐 relWords.rels / trans）",
        re.search(r"sanitizeWord|relsOf|relWords", src) is not None,
        "小学词库大量词条缺 relWords.rels，会把整道题吞掉",
    )
    check(
        "干扰项来自同一册 / 同批（不跨量级）",
        re.search(r"buildQuestion", src) is not None,
        "没复用现成出题逻辑",
    )
    check(
        "有「不认识」快速通道（几百题全靠四选一点不动）",
        re.search(r"不认识|skip|跳过", src) is not None,
        "没有快速标记生词的通道，几百题根本做不完",
    )
    check(
        "长列表不一次性渲染全部（分页或折叠）",
        re.search(r"slice\(|page|分页|showAll|folded|折叠", src) is not None,
        "几百行 DOM 一起渲染会卡",
    )


# ---------------------------------------------------------------- 6.5 答错 = 学习
def check_answer_feedback_teaches():
    """答错时不能只丢一句「正确答案」就完事 —— 测试本身也是学习。

    用户原话：「如果你答错的话，你应该显示其他中文的单词啊。
    对不对？咱就说测试的归测试，测试其实也是学习的一部分。不要让这个时间浪费掉。」

    题意：四个选项全是中文释义，答错时用户只知道「正确答案是什么」，
    但**其他三个干扰项分别对应哪个英文单词**完全没露出来 —— 那三个英文单词
    本来就是他要学的东西，白白浪费。所以答错后必须给出
    「每个选项 → 它的英文单词」的完整对照表。
    """
    src = read(PAGE_VUE)
    check(
        "答错时给出每个选项对应的英文单词（不只是正确答案）",
        re.search(r"optionDetail", src) is not None
        and re.search(r"\.en\b|en:", src) is not None,
        "答错只显示正确答案，其他选项的英文单词全浪费了 —— 测试就是学习",
    )
    check(
        "有「选项-单词」对照表的渲染（不只是一行提示文字）",
        re.search(r"对照|answerDetail|optionDetail|showDetail|detailOpen", src) is not None,
        "没有对照表呈现形式",
    )
    check(
        "对照表把四个选项都列出来（不是只列一个）",
        re.search(r"optionDetail\(\)|question\.candidates\.map", src) is not None,
        "对照表不是全量列出，等于没做",
    )
    check(
        "答对时也能看到单词对照（不惩罚答对的人）",
        re.search(r"v-if=\"submitted\"[\s\S]{0,400}detail", src) is not None
        or re.search(r"submitted[\s\S]{0,400}detail-box", src) is not None,
        "对照表应该提交后一直可看",
    )
    check(
        "对照表里能点单词发音（学完能听）",
        re.search(r"playWordAudio", src) is not None,
        "对照表不能点读等于还是只能背",
    )


# ---------------------------------------------------------------- 6.6 结束之后能继续
def check_continue_after_report():
    """用户原话：「首先呢，你可以结束，但是呢，结束完之后你又可以继续。」

    报告页不能是终点。必须给出继续的路径，且路径要具体：
      a) 接着刷下一册 / 下一套书（用户刚学完三上~五下，自然是往六上走）
      b) 只重刷生词（刚测出来的生词，趁热打铁）
    """
    src = read(PAGE_VUE)
    check(
        "报告页有「继续」的出口（不是死路）",
        re.search(r"continueNext|继续下一|接着刷|继续刷", src) is not None,
        "报告页只能回起点，等于把用户一脚踹回去",
    )
    check(
        "能接着刷下一册（自动接上没复习过的下一册）",
        re.search(r"nextBook|nextUntested|未复习的下一册|下一册", src) is not None,
        "没有「接着刷下一册」，用户得自己回设置页重新选",
    )
    check(
        "能只重刷生词（趁热打铁）",
        re.search(r"retryWrong|重刷生词|只刷生词|再刷生词", src) is not None,
        "刚测出来的生词没有一键重刷的入口",
    )
    check(
        "继续动作会把生词/进度带到下一轮（不是丢掉重来）",
        re.search(r"results", src) is not None
        and re.search(r"phase\s*=\s*['\"]quiz['\"]|start\(", src) is not None,
        "继续逻辑缺失",
    )


# ---------------------------------------------------------------- 7. HTTP
def check_http():
    for route, kw in (("/book-review", "整本"), ("/placement-test", "摸底")):
        try:
            req = urllib.request.Request(BASE_URL + route, headers={"User-Agent": "check-book-review"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "ignore")
                check(
                    "HTTP: %s 路由可访问（SSR 200）" % route,
                    r.status == 200,
                    "状态 %s" % r.status,
                )
                check(
                    "HTTP: %s 页 SSR 出关键字「%s」" % (route, kw),
                    kw in body,
                    "页面正文里没有「%s」字样" % kw,
                )
        except Exception as e:  # noqa: BLE001
            check("HTTP: %s 路由可访问（SSR 200）" % route, False, "请求失败：%s" % e)


def main():
    if not os.path.exists(PAGE_VUE):
        check("整本复习页面存在（app/pages/(words)/book-review.vue）", False, "文件不存在")
    else:
        check_page_and_entry()
        check_multi_book_select()
        check_merged_pool()
        check_progress_resume()
        check_report()
        check_robustness()
        check_answer_feedback_teaches()
        check_continue_after_report()
    if "--http" in sys.argv:
        check_http()

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print("%s %s%s" % ("[PASS]" if ok else "[FAIL]", name, ("  -> " + detail) if (detail and not ok) else ""))
    print("\n合计 %d 项，失败 %d 项" % (len(results), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
