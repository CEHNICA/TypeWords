#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TypeWords「本地导入文章」体检器
================================
维度：用户问「这个文章怎么用？我能不能自己导入文章？」——
上游 master 的文章链路有两个断点，必须补上，否则「自己导入」根本走不通：

  断点 1：文章页「创建个人书籍」点下去跳 /book/new → 该路由不存在（实际匹配 [id]='new'），
          useGetDict 找不到这本书就 router.push('/articles') → 点了等于没点。
  断点 2：就算硬建成一本「个人书」，上游**没有「新增文章」的 UI**，
          书是空的 → 一进练习页就是「没有文章可学习！」→ 死路。
  断点 3：useGetDict.loadDict() 只在「需要远程 fetch」分支里赋值 runtimeStore.editDict，
          本地导入的书自带 articles（不需要 fetch）→ editDict 不被赋值 →
          书籍详情页拿不到自己的文章 → 看到的是空书。

所以本地导入必须自己把这一整条补齐：入口 → 选文件 → 解析分句 → 生成 Article
→ 建一本 custom 书塞进书架 → 持久化 → 能进书籍详情/练习页。

用法：
    python _tools/check_article_import.py            # 静态体检
    python _tools/check_article_import.py --http     # 静态体检 + 打本地 dev server

退出码 0 = 全绿；1 = 有缺陷（每条缺陷精确红在自己那条上）。
"""
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_URL = os.environ.get("TW_BASE_URL", "http://localhost:5567")

ARTICLES_VUE = os.path.join(ROOT, "app", "pages", "(articles)", "articles.vue")
DICT_HOOK_TS = os.path.join(ROOT, "app", "core", "hooks", "dict.ts")
ARTICLE_HOOK_TS = os.path.join(ROOT, "app", "core", "hooks", "article.ts")
IMPORT_VUE = os.path.join(ROOT, "app", "components", "article", "ImportArticle.vue")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def exists(path):
    return os.path.exists(path)


def strip_comments(src):
    """去掉 // 和 /* */ 注释，避免「代码里提到某文案」被当成「界面上有某文案」。

    这条尺子第一版就栽在这儿：articles.vue 的注释里写着
    「上游『创建个人书籍』是死链」，结果被判成「入口没删干净」。
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    return src


# ---------------------------------------------------------------- 1. 入口
def check_entry():
    if not exists(ARTICLES_VUE):
        check("文章页存在（app/pages/(articles)/articles.vue）", False, "文件不存在")
        return
    src = read(ARTICLES_VUE)
    check("文章页存在（app/pages/(articles)/articles.vue）", True)

    check(
        "文章页有「导入文章」入口（用户能找到自己导入的地方）",
        re.search(r"导入文章|import_article|ImportArticle", src) is not None,
        "文章页没有任何导入入口",
    )
    check(
        "导入入口接上了真正的组件（不是只写了个文字）",
        re.search(r"ImportArticle", src) is not None,
        "入口只是个壳，没 import 导入组件",
    )
    check(
        "死链修掉了：不再跳不存在的 /book/new",
        re.search(r"['\"]/book/new", src) is None,
        "「创建个人书籍」点了会被踢回 /articles（useGetDict 找不到 'new'）",
    )
    check(
        "「创建个人书籍」这个空壳入口被换掉了",
        "创建个人书籍" not in strip_comments(src),
        "上游只能建空书（没有新增文章的 UI），留着只会让用户以为能用",
    )
    check(
        "「导入文章」入口是能点的（不是死文案）",
        re.search(r"showImport\s*=\s*true", src) is not None
        and re.search(r"<ImportArticle", src) is not None,
        "入口没接 showImport / <ImportArticle>",
    )


# ---------------------------------------------------------------- 2. 导入组件
def check_import_component():
    if not exists(IMPORT_VUE):
        check("导入文章组件存在（app/components/article/ImportArticle.vue）", False, "文件不存在")
        return
    check("导入文章组件存在（app/components/article/ImportArticle.vue）", True)
    src = read(IMPORT_VUE)

    check(
        "能选本地文件（input type=file）",
        re.search(r'type=["\']file["\']', src) is not None,
        "没法从电脑上选文章文件",
    )
    check(
        "支持 txt / md 文本",
        re.search(r"\.txt|\.md", src) is not None,
        "只认一种扩展名，用户手里的文件多半对不上",
    )
    check(
        "有书籍名输入（导入后得有地方放）",
        re.search(r"bookName|book_name", src) is not None,
        "导入完不知道归到哪本书下",
    )
    check(
        "有文章标题输入",
        re.search(r"articleTitle|title.*输入|标题", src) is not None,
        "文章没标题，进书架是一坨",
    )
    check(
        "译文可选（中文对照能填）",
        re.search(r"textTranslate|译文|translate", src, re.IGNORECASE) is not None,
        "只能导原文，没法做中文对照",
    )
    check(
        "用 FileReader 读本地文本",
        re.search(r"FileReader|\.text\(\)", src) is not None,
        "没真正读取文件内容",
    )


# ---------------------------------------------------------------- 3. 解析：复用上游分句器
def check_parsing():
    src = read(IMPORT_VUE) if exists(IMPORT_VUE) else ""

    check(
        "英文原文复用上游 splitEnArticle2（自动断句）",
        "splitEnArticle2" in src,
        "自己手搓断句 = 缩写/数字/引号全错",
    )
    check(
        "中文译文复用上游 splitCNArticle2",
        "splitCNArticle2" in src,
        "中文断句没走上游的 Intl.Segmenter",
    )
    check(
        "译文按行和英文句子数对齐（一句一行）",
        re.search(r"zhLines\.length\s*===?\s*enSentences\.length", src) is not None,
        "译文没按句对齐，英文 9 句中文 16 句 → 译文整片错位",
    )
    check(
        "原文和译文统一成「一句一段」（上游结构，段落数一致）",
        r"enSentences.join('\n\n')" in src and r"zhSentences.join('\n\n')" in src,
        "genArticleSectionData 是按段落号+句号配对的译文，结构不一致就对不上",
    )
    check(
        "生成 sections（不生成就没法逐句跟打）",
        "genArticleSectionData" in src,
        "只有原文没有 sections，练习页逐句高亮/打点全废",
    )
    check(
        "用 getDefaultArticle 兜底字段（不裸造对象）",
        "getDefaultArticle" in src,
        "裸造对象会缺 audioSrc/lrcPosition/question 等字段，渲染报错",
    )
    check(
        "空原文要拦下来（不许导空书）",
        re.search(r"!.*text.*trim|trim\(\).*length|请.*原文|不能为空", src) is not None,
        "空文件也能导入，导出一本空书",
    )


# ---------------------------------------------------------------- 4. 入书架 + 持久化
def check_into_bookshelf():
    src = read(IMPORT_VUE) if exists(IMPORT_VUE) else ""

    check(
        "导入后推进书架（base.article.bookList）",
        "article.bookList" in src,
        "文章导进来了但书架上没有，等于没导",
    )
    check(
        "标记为个人书（custom: true）",
        re.search(r"custom\s*:\s*true", src) is not None,
        "不标 custom 会被「恢复默认」冲掉，也走不了编辑",
    )
    check(
        "书和文章数量对齐（length = articles.length）",
        re.search(r"length\s*:\s*articles\.length|length\s*=\s*articles\.length", src) is not None,
        "数量对不上，进度条和篇数全是错的",
    )
    check(
        "落盘持久化（saveDictState）",
        "saveDictState" in src,
        "刷新就没了，导入白干",
    )
    check(
        "导入完把当前书切到新书（用户马上能看到）",
        re.search(r"studyIndex", src) is not None,
        "导完了首页还是老书，用户不知道去哪找",
    )


# ---------------------------------------------------------------- 5. 上游断点修复
def check_upstream_fixes():
    if not exists(DICT_HOOK_TS):
        check("useGetDict 的 loadDict 存在（app/core/hooks/dict.ts）", False, "文件不存在")
        return
    src = read(DICT_HOOK_TS)

    check(
        "断点 3 已修：自带 articles 的书（本地导入的）也会赋 runtimeStore.editDict",
        re.search(
            r"runtimeStore\.editDict\s*=\s*(r|dict)\b", src
        ) is not None
        and re.search(r"editDict\s*=\s*dict", src) is not None,
        "loadDict 只在远程 fetch 分支赋 editDict → 本地导入的书在详情页是空的",
    )
    check(
        "找不到书时不要把用户踢回列表（loadDict 有兜底）",
        re.search(r"router\.push\('/articles'\)", src) is not None,
        "行为变了但没兜底",
    )


def check_book_detail_route():
    """本地导入的书要能在书籍详情页打开（custom 书 + articles 自带）。"""
    page = os.path.join(ROOT, "app", "pages", "(articles)", "book", "[id].vue")
    if not exists(page):
        check("书籍详情页存在（app/pages/(articles)/book/[id].vue）", False, "文件不存在")
        return
    src = read(page)
    check(
        "书籍详情页用 useGetDict 加载（本地导入的书要能打开）",
        "useGetDict" in src,
        "详情页不加载书，导入的书点不开",
    )
    check(
        "详情页对 custom 书有编辑/学习分支",
        "custom" in src,
        "custom 书（导入的书）没有对应处理",
    )


# ---------------------------------------------------------------- 6. 文章数据格式自洽
def check_article_format():
    """导入生成的 Article 必须和上游 _getDictDataByUrl 读出来的结构一致。"""
    path = os.path.join(ROOT, "public", "dicts", "en", "article", "NCE_1.json")
    if not exists(path):
        check("本地文章词库存在（public/dicts/en/article/NCE_1.json）", False, "文件不存在")
        return
    import json

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    ok = isinstance(data, list) and len(data) > 0
    check("本地文章词库存在且是文章数组（public/dicts/en/article/NCE_1.json）", ok)
    if not ok:
        return
    fields = set(data[0].keys())
    for f in ("title", "text", "textTranslate"):
        check(f"文章数据带 {f} 字段（导入生成的也得有）", f in fields, f"官方文章都没有 {f}")


# ---------------------------------------------------------------- 7. 语言包
def check_locale():
    """「导入文章」入口得每个语言包都有 key，且中文有中文文案。

    第一版这里用 SSR 抓关键字，结果全是红的 —— /articles 是客户端渲染，
    SSR 只吐 9KB 空壳，页面正文根本不在 HTML 里。改成查语言包，靠谱。
    """
    import json
    import glob

    locale_dir = os.path.join(ROOT, "i18n", "locales")
    files = sorted(glob.glob(os.path.join(locale_dir, "*.json")))
    check("语言包目录有文件", len(files) > 0, f"{locale_dir} 下没找到 json")
    if not files:
        return

    missing = []
    empty = []
    for path in files:
        name = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:  # noqa: BLE001
            missing.append(f"{name}(解析失败:{e})")
            continue
        val = data.get("import_article")
        if val is None:
            missing.append(name)
        elif not str(val).strip():
            empty.append(name)

    check(
        "所有语言包都有 import_article（不漏译）",
        not missing,
        "缺 key：" + ", ".join(missing),
    )
    check(
        "没有空文案（界面会显示空白按钮）",
        not empty,
        "空文案：" + ", ".join(empty),
    )

    zh_path = os.path.join(locale_dir, "zh.json")
    if exists(zh_path):
        with open(zh_path, "r", encoding="utf-8") as f:
            zh = json.load(f)
        check(
            "中文文案是「导入文章」",
            zh.get("import_article") == "导入文章",
            f"实际是 {zh.get('import_article')!r}",
        )
    else:
        check("中文文案是「导入文章」", False, "i18n/locales/zh.json 不存在")


# ---------------------------------------------------------------- 8. HTTP
def check_http():
    for path in ("/articles", "/book-list"):
        try:
            with urllib.request.urlopen(BASE_URL + path, timeout=10) as r:
                r.read()
                ok = r.status == 200
                check(f"HTTP: {path} 路由可访问（SSR {r.status}）", ok)
        except Exception as e:  # noqa: BLE001
            check(f"HTTP: {path} 路由可访问", False, str(e))


def main():
    print("=" * 68)
    print("TypeWords「本地导入文章」体检器")
    print("=" * 68)

    check_entry()
    check_import_component()
    check_parsing()
    check_into_bookshelf()
    check_upstream_fixes()
    check_book_detail_route()
    check_article_format()
    check_locale()
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
