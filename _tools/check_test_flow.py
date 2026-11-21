#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TypeWords「单词测试」可用性体检器
================================
维度：单词 / 随机单词测试 这条链路的「能不能用 + 点了有没有反馈」。

用法：
    python _tools/check_test_flow.py            # 只跑静态体检
    python _tools/check_test_flow.py --http     # 静态体检 + 打本地 dev server

退出码 0 = 全绿；1 = 有缺陷（每条缺陷精确红在自己那条上）。
"""
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("TW_BASE_URL", "http://localhost:5567")

BASE_BUTTON = os.path.join(ROOT, "app", "base", "BaseButton.vue")
BASE_TYPES = os.path.join(ROOT, "app", "base", "types.ts")
WORDS_VUE = os.path.join(ROOT, "app", "pages", "(words)", "words.vue")
TEST_VUE = os.path.join(ROOT, "app", "pages", "(words)", "words-test", "[id].vue")
SHUFFLE_DIALOG = os.path.join(ROOT, "app", "components", "word", "ShufflePracticeSettingDialog.vue")
NUXT_CONFIG = os.path.join(ROOT, "nuxt.config.ts")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 1. BaseButton
def check_base_button():
    src = read(BASE_BUTTON)
    types = read(BASE_TYPES)

    check(
        "BaseButton 支持 disabledReason 属性",
        "disabledReason" in types and "disabledReason" in src,
        "types.ts / BaseButton.vue 里找不到 disabledReason",
    )

    # 灰按钮必须还能被 hover，否则 tooltip 永远弹不出来
    disabled_block = ""
    m = re.search(r"&\.disabled\s*\{(.*?)\}", src, re.S)
    if m:
        disabled_block = m.group(1)
    check(
        "灰按钮不禁用 pointer-events（否则提示永远触发不了）",
        "pointer-events" not in disabled_block,
        "`.disabled` 里仍有 pointer-events，hover 提示无法生效",
    )

    check(
        "BaseButton 在 disabled 时仍把 disabledReason 传给 Tooltip",
        re.search(r"disabledReason", src) is not None
        and "Tooltip" in src,
        "Tooltip 没有接上 disabledReason",
    )


# ---------------------------------------------------------------- 2. words.vue
def check_words_page():
    src = read(WORDS_VUE)

    # 每个带 :disabled 的 BaseButton 都必须同时给 :disabled-reason
    buttons = re.findall(r"<BaseButton\b.*?</BaseButton>", src, re.S)
    missing = []
    for b in buttons:
        if ":disabled" in b and ":disabled-reason" not in b:
            m = re.search(r"{{([^}]*)\}\}", b)
            label = (m.group(1).strip() if m else b[:60].replace("\n", " "))
            missing.append(label)
    check(
        "所有禁用态按钮都带原因说明（disabled-reason）",
        not missing,
        "缺少说明的按钮：" + "; ".join(missing) if missing else "",
    )

    # 随机单词测试不该再被「学过 10 个词」卡死
    shuffle_test_btn = re.search(
        r"<BaseButton\b(?:(?!</BaseButton>).)*?random_words_test(?:(?!</BaseButton>).)*?</BaseButton>",
        src,
        re.S,
    )
    ok = bool(shuffle_test_btn) and "lastLearnIndex < 10" not in shuffle_test_btn.group(0)
    check(
        "随机单词测试不再要求「先学 10 个词」",
        ok,
        "随机单词测试仍被 lastLearnIndex < 10 挡住，新用户点不动",
    )

    check(
        "单词测试入口带「为什么禁用」的文案",
        re.search(r"disabled-reason", src) is not None and "至少" in src,
        "找不到解释禁用门槛的中文文案",
    )


# ---------------------------------------------------------------- 3. 随机设置对话框
def check_shuffle_dialog():
    src = read(SHUFFLE_DIALOG)
    # progressNo == 0 时，范围要退回整本词典，否则「随机单词测试」永远提示区间不足
    ok = re.search(r"progressNo\s*>\s*0\s*\?", src) is None or "wordCount" in src
    check(
        "随机设置：0 进度时默认范围退回整本词典",
        "endNo = progressNo" not in src or "progressNo > 0" in src,
        "progressNo 为 0 时默认区间仍是空的",
    )
    check(
        "随机设置：默认题量不为 0（getDefaultTotal 有兜底）",
        "getDefaultTotal" in src and "Math.max" in src,
        "getDefaultTotal 缺失",
    )


# ---------------------------------------------------------------- 4. 测试页
def check_test_page():
    src = read(TEST_VUE)

    check(
        "测试页有单轮题量上限（不再一次出 2607 道）",
        re.search(r"ROUND_SIZE|TEST_SIZE|MAX_QUESTIONS", src) is not None,
        "找不到题量上限常量",
    )

    check(
        "测试页有成绩小结状态",
        re.search(r"finished|summary|result", src, re.I) is not None
        and re.search(r"正确|答对|correctCount", src) is not None,
        "没有成绩统计/小结",
    )

    check(
        "测试页把路由 id 转成数字再查词典",
        re.search(r"Number\(\s*(route\.params\.id|dictId)", src) is not None,
        "route.params.id 是字符串，直接 find 会找不到词典而被踢回 /words",
    )

    check(
        "测试页按模式区分出题（顺序 / 随机）",
        re.search(r"wordPracticeMode", src) is not None,
        "没有区分 WordPracticeMode",
    )

    # 没作答直接跳下一题：必须记成没答对，否则小结会出现「答对 0/2」却写「全对」
    check(
        "测试页：未作答的题要计为没答对（记进错词表）",
        re.search(r"skippedCount", src) is not None
        and re.search(r"if\s*\(\s*!\s*submitted", src) is not None,
        "跳过的题没被计数，成绩小结会自相矛盾",
    )

    check(
        "测试页：成绩小结的「全对」要跟答对数挂钩",
        re.search(r"correctCount\s*===\s*testWords\.length", src) is not None,
        "「全对，一个都没错」是无条件显示的，会和答对数打架",
    )


# ---------------------------------------------------------------- 5. nuxt.config
def check_nuxt_config():
    src = read(NUXT_CONFIG)
    ok = re.search(r"devtools\s*:\s*\{\s*enabled\s*:\s*false", src) is not None
    check(
        "关闭 Nuxt DevTools 浮动按钮（会盖住页面主按钮）",
        ok,
        "devtools 仍然开启，浮动按钮会挡住落地页的「立即开始练习」",
    )


# ---------------------------------------------------------------- 6. HTTP
def check_http():
    def get(path):
        req = urllib.request.Request(BASE_URL + path, headers={"User-Agent": "check-test-flow"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "ignore")

    try:
        st, body = get("/words-test/1")
        check(
            "HTTP: /words-test/1 路由可访问（SSR 200）",
            st == 200 and "测试：" in body,
            "状态 %s，正文里没有「测试：」" % st,
        )
    except Exception as e:  # noqa: BLE001
        check("HTTP: /words-test/1 路由可访问（SSR 200）", False, "请求失败：%s" % e)

    try:
        st, body = get("/")
        check(
            "HTTP: 落地页不含 DevTools 挂载标记",
            st == 200 and "__nuxt_devtools__" not in body,
            "落地页仍然挂载了 DevTools",
        )
    except Exception as e:  # noqa: BLE001
        check("HTTP: 落地页不含 DevTools 挂载标记", False, "请求失败：%s" % e)


def main():
    check_base_button()
    check_words_page()
    check_shuffle_dialog()
    check_test_page()
    check_nuxt_config()
    if "--http" in sys.argv:
        check_http()

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print("%s %s%s" % ("[PASS]" if ok else "[FAIL]", name, ("  -> " + detail) if (detail and not ok) else ""))
    print("\n合计 %d 项，失败 %d 项" % (len(results), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
