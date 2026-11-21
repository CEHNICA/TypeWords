# AGENTS.md — typewords-src（本地源码版）

给以后在这台机器上改这个项目的人/Agent 看。**先读 `README-本地部署.md`。**

## 这是什么

`typewords.cc` 上游 `zyronon/TypeWords`（Nuxt 4 + Vue 3 + TS + UnoCSS）的本地源码版，
master 分支。跑在 http://localhost:5567（`pnpm run dev`）。

## 硬规矩

1. **必须用 `http://localhost:5567`，不能用 `127.0.0.1`** —— 埋点按 hostname 判断，
   用 127.0.0.1 会多打外网请求。
2. **dev server 必须独立进程常驻**，不能挂在会话后台任务上（任务到时限进程被杀、端口失效）：
   ```powershell
   Start-Process -FilePath "$env:APPDATA\npm\pnpm.cmd" -ArgumentList 'run','dev' `
     -WorkingDirectory 'C:\Users\17321\Documents\破甲\typewords-src' `
     -WindowStyle Hidden -RedirectStandardOutput '_dev.log' -RedirectStandardError '_dev.err.log'
   ```
3. **`$ref` / `$computed` 在 script 里不能写 `.value`** —— `@vue-macros/nuxt` 的 reactivity
   transform 默认开启，变量在 script 里直接用。写了 `.value` 会静默变 undefined（列表全空、
   不报错）。模板里仍自动解包。
4. **图标只能用已安装的集合**（`app/components.d.ts` 里那一堆 `IconFluent*` / `IconBx*` …）。
   换新图标名可能触发联网下载；不确定就先查 `components.d.ts`。
5. **样式变量用 `main.scss` 里的主题变量**（`--color-main-text` / `--color-font-2` /
   `--color-select-bg` / `--bg-card-primary` / `--bg-card-secend` / `--color-item-border` /
   `--color-reverse-white`），这样浅色/深色自动适配，不要写死颜色。
6. **scoped 样式里 `@use '@/assets/css/xxx.scss'` 可用**（已验证编译产物带 `[data-v-*]`）。

## 资源在哪

- 词库：`public/dicts/en/word/*.json`（207）+ `article`（4），从镜像版灌的，别重新下载。
- 词库索引：`public/list/*.json`（word 207 / article 4 / recommend_* ）—— 上游 master 只带 1 条，
  已修好。**改词库清单要同步 `public/list/*.json`。**
- 音标资源：`public/sound/phonetics/*.mp3`（48）、`public/video/phonetics/*.mp4`（48）。
- 单词发音走外网 `https://dict.youdao.com/dictvoice?audio=`，失败回退浏览器 TTS。

## 本地已改的东西（跟上游 master 不同的地方）

| 位置 | 改动 |
|---|---|
| `package.json` | 加了 `-D pathe`（上游漏写，重装依赖报 `Cannot find module 'pathe'`） |
| `public/list/*.json` | 补全完整索引（上游只有 1 条 CET-4） |
| `public/sound/phonetics`、`public/video/phonetics`、`public/libs`、`public/imgs` | 从镜像灌入 |
| `app/pages/phonetics.vue` + `app/core/data/phonetics.ts` + `app/assets/css/phonetics.scss` | 新增音标教学页（上游没有） |
| `app/layouts/default.vue` | 侧边栏/移动端加「音标」入口 |
| `app/base/types.ts` + `app/base/BaseButton.vue` | BaseButton 新增 `disabledReason`，`.disabled` 去掉 `pointer-events: none`（灰按钮要能 hover 出原因） |
| `app/pages/(words)/words.vue` | 每个禁用按钮补 `disabled-reason`；「随机单词测试」解除「先学 10 词」门槛 |
| `app/components/word/ShufflePracticeSettingDialog.vue` | 0 进度时随机范围退回整本词典 |
| `app/pages/(words)/words-test/[id].vue` | 测试页大改：单轮 20 题上限、成绩小结卡、顺序/随机分流、未作答计错 |
| `nuxt.config.ts` | `devtools.enabled = false`（浮动按钮盖住落地页主按钮） |
| `app/core/data/placement.ts` | 新增：7 套教材阶梯（**莱芜小学五四（山东版）** / PEP / 新起点 / 外研 / 冀教 / JOIN IN / KET），难度轴 = 年级。莱芜放第一位 = 默认教材 |
| `app/pages/(words)/placement-test.vue` | 新增：`/placement-test` 水平摸底测试页（**自适应定位 + 逐级诊断两种测法**、年表报告、导 CSV、错词进错词本） |
| `app/pages/(words)/words.vue` | 「统计」与「我的词典」卡片之间插入「水平摸底测试」卡片 |
| `app/core/utils/word-test.ts` | 加固：`relsOf()` + `trans` 兜底，小学词库残缺词条不再把整道题吞掉 |
| `_tools/check_placement.py` | 新增：摸底链路体检器 32 项 |
| `app/pages/(words)/book-review.vue` | 新增：`/book-review` 整本复习页（**册子多选 + 全词逐个过 + 中断续做 + 每册掌握率报告 + 生词进错词本**）；后补 **选项↔单词对照表**（答错也给出四个选项的英文，默认展开、可点发音）+ **报告页「接着来」区**（接着刷下一册 / 只重刷生词） |
| `app/core/utils/placement-progress.ts` | 新增：整本复习进度持久化（**localStorage**，按「教材+册子组合」分桶 + `tw-book-review:last` 指针） |
| `_tools/check_book_review.py` | 新增：整本复习链路体检器 38 项 |
| `app/components/article/ImportArticle.vue` | 新增：本地导入文章弹窗（书籍名/标题/标题翻译 + 原文/译文 Textarea + 选文件 + 导入） |
| `app/pages/(articles)/articles.vue` | 死链「创建个人书籍」换成「导入文章」入口；导入成功切当前书 |
| `app/core/hooks/dict.ts` | 修断点：`loadDict()` 原来只在远程 fetch 分支赋 `runtimeStore.editDict`，本地导入的书自带 articles → 详情页显示空书。补 else 分支 |
| `i18n/locales/*.json` | 14 个语言包各加 `import_article`（zh=导入文章 / tw=匯入文章 / 其余=Import Article） |
| `_tools/check_article_import.py` | 新增：文章导入链路体检器 60 项（39 导入 + 12 自动翻译 + 9 弹窗界面布局） |
| `_tools/samples/my_article_en.txt` / `_tools/samples/my_article_zh.txt` | 导入功能的测试样本（9 行英文 / 9 行中文，一一对应） |

## 体检器（改测试链路必跑）

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
python _tools\check_test_flow.py --http     # 17 项，全绿 exit 0
python _tools\check_placement.py --http    # 32 项，全绿 exit 0
python _tools\check_book_review.py --http  # 38 项，全绿 exit 0
python _tools\check_article_import.py --http # 60 项，全绿 exit 0
```

## 硬规矩（补）

7. **灰按钮必须说清为什么灰**：任何 `:disabled` 的 BaseButton 都要同时给 `:disabled-reason`，
   否则用户只看到「点了没反应」。
8. **改 `nuxt.config.ts` 后必须重启 dev server**，热更新不生效。
9. **整本复习「接着刷下一册」必须继承内存里的 `results`**：册子组合变 → 桶 key 变
   （`lw:0,1` → `lw:0,1,2`）→ 直接 `start(false)` 读空桶 → 已测的词全被逼着重测。
10. **重刷生词（`mode === 'wrong'`）时 `persist()` 直接 return**，不写全量桶：
    重刷结果记在独立 `retryResults`，写全量桶会把生词在全套里的 0 分冲掉、误判「已掌握」。
11. **断句一律复用上游 `splitEnArticle2` / `splitCNArticle2` / `genArticleSectionData`**：
    上游已处理缩写（Mr./U.S.）、数字千分位、智能引号、中文 Intl.Segmenter 断句，手搓必错。
12. **文章正文结构 = 一句一段**：`text` / `textTranslate` 用 `\n\n` 分段，段落一一对应。
    上游 NCE 数据就是这结构；写成 `\n` 分句 → 跟打页译文跟英文错位。
13. **i18n 语言包是 Tab 缩进**：`json.dumps(indent=2)` 重写会造成上千行 diff。
    加 key 要用**文本插入**（`head + ',\n\t"key": "value"\n' + tail`）再 `json.load()` 校验。
14. **本项目 `BaseButton` 渲染出来是 `<span>`，不是 `<button>`**：浏览器自动化里
    `querySelectorAll('button')` 找不到，得按文本找 `span` 再 `.click()`。
15. **本机模型读不了图片**：截图/图片内容要用
    `mcode-tools upload_temp_url <path>` → `mcode-tools connector call connector__matrix__describe_images --args-file <f>`，
    提示词里让它「逐字转录，英文/中文分段标记」，不要让它总结。
16. **命令行直连谷歌翻译接口会被 429，浏览器里却通**：`translate.googleapis.com` 从
    PowerShell 打是 429（出口 IP 被限），但 localhost 页面里 `fetch` 同一个地址返回 200 且 CORS 放行。
    **别在终端里试完就说接口挂了。**
17. **翻译必须逐句串行 + 句间 120ms 间隔**：并发打过去会被限流 429；
    而且翻译和入库必须用**同一个** `toSentences()` 切分函数，否则译文与英文句子整片错位。
18. **弹窗/表单的布局规矩**（2026-11-21 导入弹窗重做后立的）：
    - Header / Body / Footer 三段式；间距走 8px 栅格，弹窗内边距 24px；
    - 多个同类区块放进**同一个 CSS Grid 容器**（列宽共享）才能保证按钮纵向对齐；
      各自 flex 行各写各的，列宽不共享 → 按钮永远对不齐；
    - 同级操作统一成同款按钮；主按钮用品牌蓝 `#409eff`（`--btn-primary` 默认的蓝灰显脏）；
    - 低频高级项默认 `<details>` 折叠收起；
    - 弹窗必须 `max-height` + 内容区 `overflow-y: auto`，否则长内容把底部按钮顶出屏幕。


## 已知缺口（master 分支本来就没有，别以为是改坏的）

- `/import`、`/nce`、`/fsrs`、`/practice-sentences`、`/login` 等页面不存在 → 404。
  `app/pages/(words)/dict.vue` 里的 `goImportPage()` 会跳 `/import`，那是**云端功能**，本地纯离线模式用不到。
- 自定义词典/个人词库依赖 Supabase（`runtimeConfig.public.apiBase`），本地没填就不可用。
- 线上站比 master 新，`dev` 分支页面多但资源走 CDN，不能直接混用。
