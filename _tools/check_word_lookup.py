#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TypeWords「点词查义」体检器
==========================
维度：用户点一个单词查释义 —— 「它会弹出一个有道的界面」「反应速度太慢」「有多少界面啊」。

根因（2026-11-21 定位，三层）：
  1. 查词走 `queryWord()` → `http('public.word/query')` → baseURL = ENV.API = 'http://localhost/'
     → 本地没配 Supabase → **必然失败** → 走 notFound 分支 → 弹 **有道整页 iframe**
     → 加载外网广告页，慢；浮层里还塞了有道/金山两个 tab + 「在新窗口打开」。
  2. 本地 404（词没收录）被当成「没查到」→ 继续打云端 → 本机 80 端口直接拒连
     → **实测 4.1 秒**，浮层卡在「查询中...」这就是「反应速度太慢」的真凶。
  3. `server/utils/wordIndex.ts` 的 `cache` 变量**从没被赋值** → 每个请求都重新解析
     20MB JSON → 实测每次多 **250ms**（dev.log 里「已加载 31748 个词条」刷十几遍）。

修法：
  1. 本地 207 份词库离线合并成索引 data/word-index.json（scripts/build-word-index.mjs）；
  2. 服务端 `GET /api/word-query` 读索引（内存 Map，O(1)、零网络）；
  3. **三态语义**：200 命中 / 404 确定性未收录（别打云端）/ 503 服务不可用（才走云端）；
  4. 索引缓存挂 globalThis（跨 HMR 有效）+ 启动时预热 → 查词 250ms → **11ms**；
  5. 前端查词**先打本地**，本地 404 直接给外链，不打云端；
  6. 浮层：命中直接显示释义（词性/例句/短语/近义）；未命中**只给两个外链**，
     不再自动 iframe 加载外网页面。

用法：
    python _tools/check_word_lookup.py            # 静态体检
    python _tools/check_word_lookup.py --http     # 静态体检 + 打本地 dev server

退出码 0 = 全绿；1 = 有缺陷。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("TW_BASE_URL", "http://localhost:5567")

POPOVER = os.path.join(ROOT, "app", "components", "word", "WordLookupPopover.vue")
LOOKUP_UTIL = os.path.join(ROOT, "app", "core", "utils", "wordLookup.ts")
LOOKUP_HOOK = os.path.join(ROOT, "app", "core", "hooks", "useWordLookup.ts")
ENV_TS = os.path.join(ROOT, "app", "core", "config", "env.ts")
INDEX_UTIL = os.path.join(ROOT, "server", "utils", "wordIndex.ts")
API_GET = os.path.join(ROOT, "server", "api", "word-query.get.ts")
WARMUP = os.path.join(ROOT, "server", "plugins", "word-index-warmup.ts")
BUILD_SCRIPT = os.path.join(ROOT, "scripts", "build-word-index.mjs")
INDEX_FILE = os.path.join(ROOT, "data", "word-index.json")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def exists(path):
    return os.path.exists(path)


# ---------------------------------------------------------------- 1. 服务端
def check_server():
    for rel, label in ((API_GET, "GET /api/word-query"), (INDEX_UTIL, "词库索引工具"),
                       (WARMUP, "索引预热插件")):
        check(f"服务端: {label} 文件存在", exists(rel), f"{rel} 不存在")

    if not exists(API_GET) or not exists(INDEX_UTIL):
        return

    api = read(API_GET)
    util = read(INDEX_UTIL)

    check("服务端: 接口引用 utils 路径正确", "../utils/wordIndex" in api and "../../utils" not in api,
          "写 ../../utils 会 RollupError「Could not resolve」且首屏卡死")
    check("服务端: 索引走内存 Map（O(1) 查词）", "new Map" in util and "lookupLocalWord" in util)
    check("服务端: 索引读磁盘文件", "word-index.json" in util)
    check("服务端: 索引文件缺失时静默降级（不抛错）", "catch" in util and "new Map()" in util,
          "索引没构建就 500 → 前端查词整条链断")

    # 缓存必须真的写回 —— 这就是「每个请求重解析 20MB」那个 bug
    check("服务端: 索引缓存真的写回（cache = map）",
          "cache = map" in util or "store.cache = map" in util,
          "只 return map 不赋值 → 每次请求重解析 20MB，实测多 250ms")
    check("服务端: 索引缓存挂 globalThis（跨 HMR 有效）",
          "globalThis" in util,
          "模块级变量会被 Nuxt dev 的 HMR 重置 → 每次热更新都重解析")

    # 三态语义
    check("服务端: 命中返回 200", "statusCode: 200" in api or "return { success: true, data }" in api)
    check("服务端: 未收录返回 404（确定性 miss）", "404" in api,
          "404 = 词典在但没这个词 → 前端直接给外链，别打云端")
    check("服务端: 服务不可用返回 503（前端才走云端）", "503" in api,
          "没有 503 → 前端分不清「没这个词」和「服务挂了」")
    check("服务端: 首次请求会 await 加载索引",
          "await ensureIndex()" in api,
          "只看 isIndexReady() 的话，第一个查词请求永远 503")

    if exists(WARMUP):
        warm = read(WARMUP)
        check("服务端: 启动时预热索引（首个查词不用等 400ms）", "loadIndex" in warm)


# ---------------------------------------------------------------- 2. 索引构建
def check_index_builder():
    check("索引: 构建脚本存在（Node 版，跟着仓库走）", exists(BUILD_SCRIPT))
    if not exists(BUILD_SCRIPT):
        return
    src = read(BUILD_SCRIPT)
    check("索引: 读 public/dicts/en/word 词库目录", "dicts" in src and "en" in src and "word" in src)
    check("索引: 同一词按优先级取一条（高频教辅优先）", "PRIORITY" in src)
    # 只看代码，不看注释（注释里提到 etymology 是为了说明「故意不收」）
    code_only = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith(("*", "//", "/*"))
    )
    check("索引: 收录的字段里没有词源长文（否则索引爆炸）", "etymology" not in code_only,
          "etymology 是词源长文，收了索引会爆到几百 MB")
    check("索引: 输出到 data/word-index.json", "word-index.json" in src)
    check("索引: 写文件用 UTF-8", "utf-8" in src)

    check("索引: data/word-index.json 已生成（否则查词永远落空）", exists(INDEX_FILE),
          "跑 node scripts/build-word-index.mjs 生成")
    if exists(INDEX_FILE):
        size = os.path.getsize(INDEX_FILE)
        check("索引: 体积在合理范围（< 80 MB）", size < 80 * 1024 * 1024, f"{size/1024/1024:.1f} MB")


# ---------------------------------------------------------------- 3. 前端查词
def check_frontend():
    if not exists(LOOKUP_UTIL):
        check("前端: 查词工具存在", False, f"{LOOKUP_UTIL} 不存在")
        return
    src = read(LOOKUP_UTIL)

    check("前端: 有本地查词分支", "/api/word-query" in src)
    check("前端: 本地优先（先本地后云端）",
          src.index("/api/word-query") < src.index("queryWord({ word: query })"),
          "本地查词必须排在云端前面，否则还是慢")
    check("前端: 本地查词失败静默降级（不抛错打断用户）", "catch" in src)
    check("前端: 查词结果有缓存（同一词不重复查）", "lookupCache" in src)

    # 三态
    check("前端: 区分「命中 / 未收录 / 服务不可用」三态",
          "status: 'hit'" in src and "status: 'miss'" in src and "status: 'unavailable'" in src,
          "不区分 → 未收录也会去打云端，等 4 秒连接被拒")
    check("前端: 404 判为确定性 miss（不打云端）", "404" in src,
          "404 必须单独识别，否则 miss 也会走云端兜底")
    check("前端: 只有服务不可用才走云端",
          "unavailable' && CLOUD_WORD_QUERY_ENABLED" in src,
          "云端兜底必须被 unavailable 门控")

    if exists(ENV_TS):
        env = read(ENV_TS)
        check("前端: 本地自动关闭云端查词兜底",
              "CLOUD_WORD_QUERY_ENABLED" in env,
              "ENV.API 指向 localhost = 本机没跑 Supabase，打过去必然连接被拒")

    if exists(LOOKUP_HOOK):
        hook = read(LOOKUP_HOOK)
        check("前端: 查词有竞态守卫（连点不同词不串结果）",
              "requestSeq" in hook,
              "连点两个词，后到的旧请求会覆盖新结果")


# ---------------------------------------------------------------- 4. 浮层界面
def check_popover():
    if not exists(POPOVER):
        check("浮层: 组件存在", False, f"{POPOVER} 不存在")
        return
    src = read(POPOVER)

    check("浮层: 不再有 iframe（外网整页是慢的根本原因）",
          "<iframe" not in src, "iframe 加载有道整页 → 慢")
    check("浮层: 不再有词典 tab 切换（有道/金山）",
          "dictionary-tab" not in src and "activeDictionary" not in src,
          "两个 tab 是用户说的「好多界面」")
    check("浮层: 本地未收录时给外链（新标签页）",
          "target=\"_blank\"" in src and "youdao" in src.lower())
    check("浮层: 命中时显示释义（TranslationList）", "TranslationList" in src)
    check("浮层: 命中时显示例句", "sentences" in src)
    check("浮层: 命中时显示短语", "phrases" in src)
    check("浮层: 命中时显示近义词", "synos" in src)
    check("浮层: 未收录时明确说「本地词典未收录」", "本地词典未收录" in src)
    check("浮层: 保留发音按钮", "playWordAudio" in src)
    check("浮层: 保留收藏入口", "openWordCollect" in src or "openCollect" in src)
    check("浮层: Escape 可关闭", "Escape" in src)


# ------------------------------------------------- 4.5 词典扩充（CC-CEDICT + 词形）
AUGMENT_SCRIPT = os.path.join(ROOT, "scripts", "augment-word-index.mjs")
FORMS_FILE = os.path.join(ROOT, "data", "word-forms.txt")


def check_dictionary_expansion():
    """用户：「很多单词本地词典没有收录，有没有办法预加载上」

    两条补法：
      A. 词形映射表（asks → ask）：教辅词书只收原形，用户文章里全是变形
      B. CC-CEDICT 公共领域中英词典：补专有名词、派生词、缩写
    """
    check("扩充: 扩充脚本存在", exists(AUGMENT_SCRIPT))
    if not exists(AUGMENT_SCRIPT):
        return
    src = read(AUGMENT_SCRIPT)

    check("扩充: 从 mdbg.net 取 CC-CEDICT（公共领域中英词典）",
          "mdbg.net" in src and "cedict" in src.lower())
    check("扩充: 缺词典时自动下载（换机器也能一条命令重建）",
          "fetch(" in src and "CEDICT_URL" in src)
    check("扩充: 生成词形映射表", "generateForms" in src and "word-forms" in src)
    check("扩充: 词形表用 TAB 分隔（base 可能是短语，按空格切会切错）",
          "\\t${b}" in src or "'\\t'" in src or "\\t" in src)
    check("扩充: 有不规则动词表（begin→began、take→taken 规则生成不出）",
          "IRREGULAR" in src and "began" in src and "taken" in src)
    check("扩充: 词形表按 TAB 解析（服务端）", "indexOf('\\t')" in read(INDEX_UTIL))
    check("扩充: 服务端有词形回退（miss → 查 forms 表）",
          "forms.get" in read(INDEX_UTIL))
    check("扩充: CC-CEDICT 同形词让位给教辅释义（guiding 不能译成「贵定县」）",
          "'CC-CEDICT'" in read(INDEX_UTIL))
    check("扩充: 浮层标注原形（查 asks 命中 ask 时要说明）",
          "baseWord" in read(POPOVER))

    # 产物断言
    check("扩充: data/word-forms.txt 已生成", exists(FORMS_FILE))
    if exists(FORMS_FILE):
        size = os.path.getsize(FORMS_FILE)
        with open(FORMS_FILE, "r", encoding="utf-8") as f:
            lines = [ln for ln in f.read().split("\n") if ln]
        check("扩充: 词形映射条目数 > 20 万", len(lines) > 200000, f"{len(lines)} 条")
        check("扩充: 词形表体积合理（< 30 MB）", size < 30 * 1024 * 1024, f"{size/1024/1024:.1f} MB")
        has_tab = any("\t" in ln for ln in lines[:50])
        check("扩充: 词形表确实是 TAB 分隔", has_tab)
        mapping = {}
        for ln in lines:
            if "\t" in ln:
                k, v = ln.split("\t", 1)
                mapping[k] = v
        for form, base in (("asks", "ask"), ("seeing", "see"), ("began", "begin"),
                           ("taken", "take"), ("led", "lead"), ("mimicking", "mimic"),
                           ("months", "month"), ("simplified", "simplify")):
            check(f"扩充: 词形映射 {form} → {base}", mapping.get(form) == base,
                  f"实际 {mapping.get(form)}")

    check("扩充: data/word-index.json 已生成", exists(INDEX_FILE))
    if exists(INDEX_FILE):
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            idx = json.load(f)
        n = len(idx)
        check("扩充: 索引词数 > 5 万（扩充后）", n > 50000, f"{n} 词")
        check("扩充: 索引含 CC-CEDICT 来源的词条",
              any(v.get("src") == "CC-CEDICT" for v in idx.values()))
        check("扩充: 索引含专有名词（riemann / claude）",
              "riemann" in idx and "claude" in idx)


# ---------------------------------------------------------------- 5. HTTP
def check_http():
    # 命中
    try:
        with urllib.request.urlopen(BASE_URL + "/api/word-query?word=cancel", timeout=15) as r:
            data = json.loads(r.read().decode())
            ok = r.status == 200 and data.get("success") and data["data"].get("word")
            check("HTTP: 查已知词返回释义", ok, str(data)[:120])
            if ok:
                d = data["data"]
                check("HTTP: 释义带词性", bool(d.get("trans")) and bool(d["trans"][0].get("pos")),
                      "trans 为空 → 浮层没东西显示")
                check("HTTP: 释义带中文", bool(d["trans"][0].get("cn")))
                check("HTTP: 释义带音标", bool(d.get("phonetic0") or d.get("phonetic1")))
                check("HTTP: 释义带例句", bool(d.get("sentences")))
                check("HTTP: 释义带来源词库名", bool(d.get("src")))
    except Exception as e:  # noqa: BLE001
        check("HTTP: 查已知词返回释义", False, str(e))

    # 大小写不敏感
    try:
        with urllib.request.urlopen(BASE_URL + "/api/word-query?word=CANCEL", timeout=15) as r:
            check("HTTP: 查词不区分大小写", r.status == 200)
    except Exception as e:  # noqa: BLE001
        check("HTTP: 查词不区分大小写", False, str(e))

    # 未收录 → 404
    try:
        with urllib.request.urlopen(BASE_URL + "/api/word-query?word=zzqqxxnotaword", timeout=15) as r:
            check("HTTP: 未收录的词返回 404", False, f"status={r.status}")
    except urllib.error.HTTPError as e:
        check("HTTP: 未收录的词返回 404", e.code == 404, f"code={e.code}")
    except Exception as e:  # noqa: BLE001
        check("HTTP: 未收录的词返回 404", False, str(e))

    # 空词 → 400
    try:
        with urllib.request.urlopen(BASE_URL + "/api/word-query?word=", timeout=15) as r:
            check("HTTP: 空词返回 400", False, f"status={r.status}")
    except urllib.error.HTTPError as e:
        check("HTTP: 空词返回 400", e.code == 400, f"code={e.code}")
    except Exception as e:  # noqa: BLE001
        check("HTTP: 空词返回 400", False, str(e))

    # 性能：预热后必须毫秒级（这是用户「反应速度太慢」的直接指标）
    try:
        t0 = time.time()
        with urllib.request.urlopen(BASE_URL + "/api/word-query?word=classic", timeout=15) as r:
            r.read()
        first = (time.time() - t0) * 1000
        t0 = time.time()
        for _ in range(5):
            with urllib.request.urlopen(BASE_URL + "/api/word-query?word=learn", timeout=15) as r:
                r.read()
        avg = (time.time() - t0) * 1000 / 5
        check(f"HTTP: 查词响应 < 200ms（实测 {avg:.0f}ms / 首请求 {first:.0f}ms）",
              avg < 200, f"平均 {avg:.0f}ms —— 慢就是索引没缓存住")
    except Exception as e:  # noqa: BLE001
        check("HTTP: 查词响应 < 200ms", False, str(e))

    # ---- 扩充维度：词形回退 ----
    for form, base in (("asks", "ask"), ("seeing", "see"), ("began", "begin"),
                       ("taken", "take"), ("led", "lead"), ("mimicking", "mimic"),
                       ("months", "month"), ("simplified", "simplify")):
        try:
            with urllib.request.urlopen(BASE_URL + f"/api/word-query?word={form}", timeout=15) as r:
                d = json.loads(r.read().decode())["data"]
                check(f"HTTP: 变形词 {form} 能查到（回退到 {base}）",
                      bool(d.get("trans")) and d.get("baseWord") == base,
                      f"baseWord={d.get('baseWord')} src={d.get('src')}")
        except Exception as e:  # noqa: BLE001
            check(f"HTTP: 变形词 {form} 能查到（回退到 {base}）", False, str(e))

    # ---- 扩充维度：专名（CC-CEDICT） ----
    for proper in ("riemann", "claude"):
        try:
            with urllib.request.urlopen(BASE_URL + f"/api/word-query?word={proper}", timeout=15) as r:
                d = json.loads(r.read().decode())["data"]
                check(f"HTTP: 专名 {proper} 收录了（CC-CEDICT）", bool(d.get("trans")),
                      str(d)[:100])
        except Exception as e:  # noqa: BLE001
            check(f"HTTP: 专名 {proper} 收录了（CC-CEDICT）", False, str(e))

    # ---- CC-CEDICT 同形词不能让位给地名（guiding 在 CC-CEDICT 里是「贵定县」） ----
    try:
        with urllib.request.urlopen(BASE_URL + "/api/word-query?word=guiding", timeout=15) as r:
            d = json.loads(r.read().decode())["data"]
            check("HTTP: guiding 取教辅释义而非 CC-CEDICT 地名",
                  d.get("src") != "CC-CEDICT" and d.get("baseWord") == "guide",
                  f"src={d.get('src')} base={d.get('baseWord')}")
    except Exception as e:  # noqa: BLE001
        check("HTTP: guiding 取教辅释义而非 CC-CEDICT 地名", False, str(e))


def main():
    print("=" * 68)
    print("TypeWords「点词查义」体检器")
    print("=" * 68)

    check_server()
    check_index_builder()
    check_dictionary_expansion()
    check_frontend()
    check_popover()
    if "--http" in sys.argv:
        check_http()

    failed = 0
    for name, ok, detail in results:
        if ok:
            print(f"[PASS] {name}")
        else:
            failed += 1
            print(f"[FAIL] {name}" + (f"  —— {detail}" if detail else ""))

    print("-" * 68)
    print(f"合计 {len(results)} 项，失败 {failed} 项")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
