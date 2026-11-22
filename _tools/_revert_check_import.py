#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本轮（词表导入）退回验证

往源码里注入坏样本，跑浏览器尺子，确认尺子**红在正确的那条判据**上，然后还原。

用法：python _tools/_revert_check_import.py
"""
import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "_tools")
UI_RULER = os.path.join(TOOLS, "_check_custom_import_ui.js")

COMP = os.path.join(ROOT, "app", "components", "word", "ImportWordList.vue")
PAGE = os.path.join(ROOT, "app", "pages", "import.vue")


def read(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def run_ruler():
    proc = subprocess.run(
        ["node", UI_RULER], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    out = proc.stdout or ""
    fails = [ln for ln in out.splitlines() if ln.startswith("[FAIL]")]
    return out, fails


def case(name, path, old, new, expect_keys):
    orig = read(path)
    assert old in orig, "注入点没找到：%s" % old[:60]
    backup = orig
    try:
        write(path, orig.replace(old, new, 1))
        out, fails = run_ruler()
    finally:
        write(path, backup)

    print("")
    print("=" * 60)
    print("退回用例：%s" % name)
    print("-" * 60)
    print("尺子 FAIL 条数：%d" % len(fails))
    for ln in fails:
        print("  " + ln)
    hit = [k for k in expect_keys if any(k in ln for ln in fails)]
    ok = bool(hit) and len(fails) > 0
    print("判定：%s（期望红在：%s）" % ("PASS" if ok else "FAIL", " / ".join(expect_keys)))
    return ok


def main():
    ok = True

    # 用例 1：把 isMergeMode.value 改回裸 isMergeMode（重现本轮真踩的坑）
    ok &= case(
        "computed 在 script 里漏写 .value → 词书名自动填失效",
        COMP,
        "if (!isMergeMode.value && !bookName.value) {",
        "if (!isMergeMode && !bookName.value) {",
        ["词书名自动填成文件名", "导入成功", "store 里多了一本自定义词典"],
    )

    # 用例 2：/import 薄壳页挂载时直接给 true（上游 Dialog 靠 watch 变化才开 → 弹窗不出现）
    ok &= case(
        "/import 薄壳页挂载即 open → 弹窗不出现",
        PAGE,
        "let show = ref(false)\n\nonMounted(() => {\n  show.value = true\n})",
        "let show = ref(true)\n\nonMounted(() => {})",
        ["合并模式按钮文案", "合并模式没有词书名输入框"],
    )

    print("")
    print("=" * 60)
    print("退回验证：%s" % ("全部通过" if ok else "有用例没红在正确判据上"))
    print("失败项合计: %d" % (0 if ok else 1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
