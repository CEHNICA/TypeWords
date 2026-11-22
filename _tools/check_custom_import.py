#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本地词表导入：静态体检器

查什么：
  1. 解析层 / 组件 / 落地页 三个文件都在
  2. 上游死链 /import 有人接了
  3. 词典列表页有「导入词表」入口，且真的挂了组件
  4. **不新增 IndexedDB schema** —— 词书走既有 bookList 持久化，
     不许出现新的 idb-keyval key、不许出现原生 indexedDB.open
  5. 词书 id 用 custom- 前缀，不跟内置词库 id（1..265）撞号
  6. 表头别名覆盖 word / trans / phonetic / note 四类
  7. 组件里不打云端（本地优先）

退出码 0 = 全过；非 0 = 有问题项。
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

F_PARSER = os.path.join(ROOT, "app", "core", "utils", "custom-word-import.ts")
F_COMP = os.path.join(ROOT, "app", "components", "word", "ImportWordList.vue")
F_PAGE = os.path.join(ROOT, "app", "pages", "import.vue")
F_LIST = os.path.join(ROOT, "app", "pages", "(words)", "dict-list.vue")

failed = 0


def check(name, ok, detail=""):
    global failed
    if not ok:
        failed += 1
    print(("[PASS] " if ok else "[FAIL] ") + name + ("" if ok else "  —— " + str(detail)))


def read(path):
    if not os.path.exists(path):
        return None
    return io.open(path, encoding="utf-8").read()


# ---- 1. 文件存在 ----
for label, path in [("解析层", F_PARSER), ("导入组件", F_COMP), ("落地页 /import", F_PAGE), ("词典列表页", F_LIST)]:
    check(label + " 文件存在", os.path.exists(path), path)

parser = read(F_PARSER) or ""
comp = read(F_COMP) or ""
page = read(F_PAGE) or ""
lst = read(F_LIST) or ""

# ---- 2. 解析层导出齐全 ----
for fn in ["parseDelimited", "detectColumns", "buildWords", "decodeBuffer", "matchField", "normalizeHeader"]:
    check("解析层导出 " + fn, re.search(r"export\s+(?:async\s+)?function\s+" + fn + r"\b", parser) is not None)

# ---- 3. 上游死链有人接 ----
check("/import 落地页存在（上游 dict.vue 的 nav('/import') 死链）", os.path.exists(F_PAGE))
check("落地页挂载 ImportWordList", "ImportWordList" in page)
check("落地页认 type=word 的 query", "targetId" in page and "type" in page)

# ---- 4. 入口 ----
check("词典列表页引入 ImportWordList", "ImportWordList" in lst)
check("词典列表页有「导入词表」入口", "导入词表" in lst)
check("词典列表页挂了组件", re.search(r"<ImportWordList[^>]*v-model", lst) is not None)

# ---- 5. 不新增 IndexedDB schema ----
check("组件不新建 IndexedDB（无 indexedDB.open）", "indexedDB.open" not in comp)
check("组件不新建 idb-keyval key", not re.search(r"\bset\s*\(\s*['\"]typing-word", comp))
check("组件走既有 saveDictState 持久化", "saveDictState" in comp)
check("解析层不碰存储", "indexedDB" not in parser and "idb-keyval" not in parser)

# ---- 6. id 不撞内置词库 ----
check("新词书 id 用 custom- 前缀", re.search(r"id:\s*'custom-(?:dict-)?'\s*\+", comp) is not None)
check("合并模式用 targetId 找目标词典", "props.targetId" in comp)

# ---- 7. 表头别名覆盖 ----
# 注意：别名表的 key 是中文/英文表头文本，值才是字段名（'word'/'trans'/...），
# 所以只能按「值 == 字段名」来判，不能按「key == 字段名」判。
for field in ["word", "trans", "phonetic0", "phonetic1", "note"]:
    hits = re.findall(r"['\"]?[\w\u4e00-\u9fff①-⑳]+['\"]?\s*:\s*'" + field + r"'", parser)
    check("表头别名映射到 " + field, len(hits) >= 1, "命中 %d 个" % len(hits))
check("表头别名含中文「单词」", re.search(r"单词\s*:\s*'word'", parser) is not None)
check("表头别名含中文「翻译」", re.search(r"翻译\s*:\s*'trans'", parser) is not None)
check("表头别名含中文「音标」", re.search(r"音标\s*:\s*'phonetic0'", parser) is not None)

# ---- 8. 本地优先：不打云端 ----
for bad in ["supabase", "ENV.API", "https://typewords.cc"]:
    check("组件不含云端依赖 " + bad, bad not in comp)

# ---- 9. 坏数据要有提示，不能静默吞 ----
check("解析失败有提示", "Toast.error" in comp)
check("无单词列时明确报错", "没找到「单词」列" in comp)
# 文件内重复：计数在解析层（duplicates++ + seen 集合 + 「重复单词，已跳过」）
# 判据要卡具体语句，不能只查 "duplicates" 字样（声明里也有这个词，会假绿）
check(
    "文件内重复单词会被计数",
    "duplicates++" in parser and "seen.has(key)" in parser and "重复单词" in parser,
)
# 合并模式同名单词：跳过逻辑在组件层（exist 集合 + skipped 计数 + 提示文案）
check(
    "合并模式同名单词跳过并计数",
    "exist.has(k)" in comp and "skipped++" in comp and "跳过" in comp,
)

# ---- 10. 解析层语法自检：块注释不能被 */ 提前闭合 ----
# （本轮真踩过：注释里写 **/import 把块注释提前闭合 → 整页 Vite Error）
# 真判据：剥掉字符串与行注释后，块注释的 /* 与 */ 必须成对；
# 再加一条字面量防御：源码里不该出现 **/ 这种「提前闭合」写法。


def strip_code(src):
    """剥掉字符串字面量与行注释，只留结构代码（够用来数注释配对）。"""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            q = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                i += 1
            out.append('""')
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


_code = strip_code(parser)
check(
    "解析层块注释成对闭合",
    _code.count("/*") == _code.count("*/") and _code.count("/*") > 0,
)
check("解析层无 **/ 提前闭合写法", "**/" not in parser)

print("")
print("-" * 60)
print("失败项合计: %d" % failed)
sys.exit(1 if failed else 0)
