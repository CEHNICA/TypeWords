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
- 查词索引（**都不进版本库**，`data/` 已 gitignore）：
  - `data/word-index.json` —— 教辅词库索引（207 份 → 31,748 词）+ CC-CEDICT 补缺（→ **65,655 词**，25.4 MB）
  - `data/word-forms.txt` —— 词形映射（形变 → 原形，**33.3 万条**，TAB 分隔，6.4 MB）
  - `data/cedict.txt.gz` —— CC-CEDICT 原始词典（3.9 MB，CC BY-SA 4.0，`augment-word-index.mjs` 会自动下载）
  - 重建：`node scripts\build-word-index.mjs` → `node scripts\augment-word-index.mjs`（`启动.cmd` 首次运行会自动跑）

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
| `app/core/data/placement.ts` | 新增：**8 套教材阶梯**（**莱芜五四制（山东版）** / PEP / 新起点 / 外研小学 / **外研社（初中）** / 冀教 / JOIN IN / KET），难度轴 = 年级。莱芜放第一位 = 默认教材。后扩：**一路铺到九年级**（PEP/冀教/莱芜加初中 7~9 年级册、外研初中独立成阶梯）+ `afterTop` 字段（摸到顶后往哪走） |
| `app/pages/(words)/placement-test.vue` | 新增：`/placement-test` 水平摸底测试页（**自适应定位 + 逐级诊断两种测法**、年表报告、导 CSV、错词进错词本）；后补 **答错信息完整性**（提示区「你选的是：英文（中文）」+ 选项提交后显示带底色块的英文单词 + 报告明细红色「误选：英文（中文）」+ CSV 加误选两列） |
| `app/pages/(words)/words.vue` | 「统计」与「我的词典」卡片之间插入「水平摸底测试」卡片 |
| `app/core/utils/word-test.ts` | 加固：`relsOf()` + `trans` 兜底，小学词库残缺词条不再把整道题吞掉 |
| `_tools/check_placement.py` | 新增：摸底链路体检器 32 项；后扩到 **45 项**（新增「答错信息完整性」维度：提示区 / 选项英文 / 明细误选 / CSV 误选列 / 红绿语义 / 撇号收紧 / 列宽不截断）；再扩到 **72 项**（新增「阶梯铺到九年级」维度：分年级阶梯末级必须是九年级 / PEP·冀教·莱芜必须挂对初中册 / 外研初中独立成阶梯 / 莱芜名字说清含初中 / `afterTop` 指路正确） |
| `_tools/_check_placement_ui.js` | 新增：摸底**浏览器实测** 14 项（答错提示 / 选项英文 / 明细误选 / CSV 下载内容 / 撇号无断词 / 无 JS 报错，音频噪音报错豁免） |
| `_tools/_shot_placement.js` | 新增：摸底「答错后」+「报告页」截图（给视觉模型验收） |
| `_tools/_check_placement_ladders.js` | 新增：**8 套阶梯浏览器实测**（逐套加载出题 + **抓网络请求证明新增九年级册子真被下载** + 加载耗时） |
| `_tools/_check_placement_advice.js` | 新增：报告页文案实测（8 套按钮齐全 / 「共 N 个年级」对得上 / 没摸到顶时不瞎喊「摸到顶了」） |
| `_tools/_shot_setup.js` | 新增：setup 页桌面 + 窄屏截图（给视觉模型验收 8 个教材按钮排布） |
| `_tools/_diag_textbooks.mjs` | 新增：词库课本盘点诊断（本地 207 册 vs 线上 241 册，差的是雅思词汇/听力，**本地没有孤儿也没有 404**） |
| `app/pages/(words)/book-review.vue` | 新增：`/book-review` 整本复习页（**册子多选 + 全词逐个过 + 中断续做 + 每册掌握率报告 + 生词进错词本**）；后补 **选项↔单词对照表**（答错也给出四个选项的英文，默认展开、可点发音）+ **报告页「接着来」区**（接着刷下一册 / 只重刷生词） |
| `app/core/utils/placement-progress.ts` | 新增：整本复习进度持久化（**localStorage**，按「教材+册子组合」分桶 + `tw-book-review:last` 指针） |
| `_tools/check_book_review.py` | 新增：整本复习链路体检器 38 项 |
| `app/components/article/ImportArticle.vue` | 新增：本地导入文章弹窗（书籍名/标题/标题翻译 + 原文/译文 Textarea + 选文件 + 导入） |
| `app/pages/(articles)/articles.vue` | 死链「创建个人书籍」换成「导入文章」入口；导入成功切当前书 |
| `app/core/hooks/dict.ts` | 修断点：`loadDict()` 原来只在远程 fetch 分支赋 `runtimeStore.editDict`，本地导入的书自带 articles → 详情页显示空书。补 else 分支 |
| `i18n/locales/*.json` | 14 个语言包各加 `import_article`（zh=导入文章 / tw=匯入文章 / 其余=Import Article） |
| `_tools/check_article_import.py` | 新增：文章导入链路体检器 **81 项**（39 导入 + 12 自动翻译 + 9 弹窗界面布局 + 21 服务端副本/跨浏览器） |
| `_tools/samples/my_article_en.txt` / `_tools/samples/my_article_zh.txt` | 导入功能的测试样本（9 行英文 / 9 行中文，一一对应） |
| `server/utils/localArticles.ts` | 新增：服务端副本读写 `data/local-articles.json`（**IndexedDB 按浏览器 profile 隔离 → 换个浏览器书架是空的**，靠这个解决） |
| `server/api/local-articles.get.ts` / `.post.ts` / `.delete.ts` | 新增：服务端副本的 GET / POST / DELETE 接口 |
| `app/core/hooks/localArticles.ts` | 新增：`mergeServerArticles` 拉取合并 + `syncArticleToServer` 导入后推送 + `pushLocalArticlesToServer` 本机旧书补推 + `removeArticleFromServer` 删书同步 |
| `_tools/_check_cross_browser.js` | 新增：跨浏览器闭环验收脚本（干净 profile 模拟另一个浏览器，10 项） |
| `server/utils/wordIndex.ts` | 新增：本地离线词典索引（207 份词库 → 31748 唯一词），缓存挂 `globalThis` + 启动预热 |
| `server/api/word-query.get.ts` | 新增：`/api/word-query` **三态**接口（200 命中 / 404 确定性未收录 / 503 服务不可用） |
| `server/plugins/word-index-warmup.ts` | 新增：Nitro 启动预热索引（286ms 载入 31748 词条） |
| `scripts/build-word-index.mjs` | 新增：Node 版索引构建（`pnpm index:word`，5.2s / 19.8MB；替代已删的 `_tools/build_word_index.py`） |
| `app/core/config/env.ts` | 新增 `CLOUD_WORD_QUERY_ENABLED`：API 指向 localhost 时自动关掉云端查词兜底 |
| `app/core/utils/wordLookup.ts` | 改：本地三态优先，只有 `unavailable` 才走云端；404 = 确定性 miss |
| `app/core/hooks/useWordLookup.ts` | 改：`requestSeq` 竞态守卫（连点不同词不串结果） |
| `app/core/hooks/sound.ts` | 改：发音加 1.5s 超时回退浏览器 TTS（dictvoice 挂起时不卡） |
| `app/components/word/WordLookupPopover.vue` | 改：砍掉有道整页 iframe 与词典 tab，只留释义/例句/短语/近义词；未收录才给外链 |
| `启动.cmd` | 改：首次运行若缺 `data/word-index.json` 自动构建（**必须保持纯 ASCII**） |
| `_tools/check_word_lookup.py` | 新增：查词链路体检器 **52 项**（服务端三态 / cache 写回 / globalThis / ensureIndex / 预热 / HTTP <200ms） |
| `_tools/_check_lookup_ui.js` | 新增：浏览器实测（0 iframe / 0 tab / 端到端 <500ms / **全程无云端查词请求** / **全程无外网词典页请求**） |
| `_tools/_shot_lookup.js` | 新增：查词浮层截图（供视觉模型验收） |
| `scripts/augment-word-index.mjs` | 新增：**词典扩充**（CC-CEDICT 补专名/派生词 + 预生成词形映射表 `data/word-forms.txt`） |
| `server/utils/wordIndex.ts` | 改：加 `loadForms()` 词形映射（miss → 回退原形）+ CC-CEDICT 同形词让位给教辅释义 |
| `app/core/types/types.ts` | 改：`Word` 加 `baseWord?`（命中的是原形时标注） |
| `app/components/word/WordLookupPopover.vue` | 改：命中变形词时显示「原形 xxx」小节 |
| `_tools/_diag_coverage.mjs` / `_diag_coverage2.mjs` | 新增：词典覆盖率诊断（文章词 vs 索引） |

## 体检器（改测试链路必跑）

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
python _tools\check_test_flow.py --http     # 17 项，全绿 exit 0
python _tools\check_placement.py --http    # 72 项，全绿 exit 0
python _tools\check_book_review.py --http  # 38 项，全绿 exit 0
python _tools\check_article_import.py --http # 81 项，全绿 exit 0
python _tools\check_word_lookup.py --http     # 89 项（查词），全绿 exit 0
```

`node _tools\_check_lookup_ui.js` 走 Playwright 实测点词（查词链路每次改动必跑），
`node _tools\_check_cross_browser.js` 跑跨浏览器闭环。
`node _tools\_check_placement_ui.js` 跑摸底答题实测（摸底页每次改动必跑），
`node _tools\_check_placement_ladders.js` 跑 8 套阶梯加载实测（改了阶梯/词库就必跑），
`node _tools\_check_placement_advice.js` 跑报告页文案实测，
`node _tools\_shot_placement.js` 出「答错后 / 报告页」两张截图给视觉模型验收，
`node _tools\_shot_setup.js` 出 setup 页桌面 + 窄屏截图给视觉模型验收。

词典扩充（改了词库/查词就重跑）：

```powershell
node scripts\build-word-index.mjs     # 重建教辅词库索引
node scripts\augment-word-index.mjs   # 再灌 CC-CEDICT + 词形映射（缺词典会自动下载）
node _tools\_diag_coverage2.mjs       # 看文章词覆盖率
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
19. **Playwright 独立上下文是干净 profile，没有 IndexedDB**：只能用来验样式和跑「临时导一篇」
    的功能闭环，**不能用它判断用户书架里有没有某本书**（用户数据在浏览器真实 profile 的 IndexedDB
    `keyval-store` → `keyval` 里）。截图脚本：`_tools/_shot_dialog.js`。
20. **新增/修改 `server/` 目录下的文件后必须重启 dev server**（Nitro 才会重新加载路由），
    热更新不管用；重启命令见 README「启动」小节。
21. **`server/api/*.ts` 引用 `server/utils/*` 必须写 `../utils/xxx`**：写成 `../../utils/xxx`
    会 RollupError「Could not resolve」，而且 **dev server 会卡住首屏**（接口请求全超时，
    表现为「整页打不开」，不是报错）。
22. **本地导入文章的跨浏览器可见靠服务端副本**（`data/local-articles.json`）：
    - 合并时**不覆盖**本地同 id 的书 → 学习进度不能被冲掉；
    - `sections` 不落盘，运行时用 `genArticleSectionData` 重算；
    - 删书必须同步 `DELETE /api/local-articles`，否则换浏览器还看得见幽灵书；
    - 静态部署没 server runtime → 接口 404，**前端必须静默降级**成「只存本浏览器」，不报错。
23. **`mcp_browser` 的 `run_script` 在本环境不回传返回值**（`pageEvaluate.calls` 恒为 0），
    `page.evaluate` 实际没执行 → **别指望用它读写页面数据**。要在页面里取数据，走
    `_tools/` 下的 Playwright 脚本；要在页面里执行动作，走 `inspect` + `click`/`fill`。
24. **查词接口必须三态，缓存必须真写回**（2026-11-21 查词慢 4 秒的根因）：
    - `404` = 词典在但没这个词（前端直接给外链，**不打云端**）；`503` = 服务不可用（才走云端）。
      混成一种 → 本地 404 被当「没查到」→ 去打 `http://localhost:80`（本机没 Supabase）
      → 连接被拒，等 **4114ms** 才返回。
    - 缓存变量必须真的 `store.cache = map` 写回，只 `return map` 等于没缓存
      （每个请求重读磁盘重解析 20MB JSON，稳定多耗 250ms）。
    - 缓存挂 `globalThis` —— Nuxt dev 的 HMR 会重置模块级变量。
    - `isIndexReady()` 在首次加载前恒为 false → 接口必须 `await ensureIndex()`，
      否则第一个查词请求永远 503。
    - 发音仍走上游有道 `dictvoice`（外网音频，本地没有），**别让它阻塞释义渲染**。
25. **点词查义的老入口还有三处没动**（用户嫌界面多，本轮只砍了浮层里的）：
    `TypingArticle.vue:680-692`、`TypingSentence.vue:112-123` 的右键「有道翻译」，
    以及 `app/core/utils/index.ts:818 goYoudao()`（**当前无调用方**，是死代码）。
26. **词典扩充的坑（2026-11-21，CC-CEDICT + 词形映射）**：
    - CC-CEDICT 下载源 `https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz`
      （**GitHub raw 那份 404，mdbg.net 这份可用**），许可 CC BY-SA 4.0，放在 `data/cedict.txt.gz`（不进版本库）。
    - **CRLF 坑**：该文件是 CRLF，`split('\n')` 后行尾还带 `\r`，而 **JS 正则的 `.` 不匹配 `\r`**
      → `...$` 整行匹配失败，一条都解析不出来。先 `replace(/\r\n/g,'\n')`。
    - **词形表必须用 TAB 分隔**（`form\tbase`）：base 里可能有含空格的短语（CC-CEDICT 混着
      `according to` / `guided tour`），按空格切会切错并**覆盖别的单词的正确映射**
      （实测 `months` 被 `months and years` 的行顶掉）。
    - **形态规则只对单词做**：对短语生成形态会产出 `guided tourred` 这种垃圾。
    - **`ic` 结尾的词走 ic→ck**：`mimic → mimicking / mimicked`（别用双写规则，会变成 `mimicking`）。
    - **不规则动词表优先写入**：词库里有脏条目（`le` 的释义其实是 `lead`）会抢 `led` 的映射。
    - **CC-CEDICT 有同形污染**：`guiding` 在词典里是贵州地名「贵定县」。服务端命中 CC-CEDICT 条目时，
      若存在**教辅词书**的原形映射（guiding → guide），优先给教辅释义。
    - 实测覆盖率（用户那篇导入文章 226 个词）：扩充前 73.0% → 扩充后 **96.9%**。
      剩下的 3.1% 是冷僻专名（stepanov / mangoldt / fourier-analytic）。
27. **摸底页「答错信息」的坑（2026-11-21）**：
    - 小学词库里撇号是 **ASCII 且紧贴字母**（`they're` / `what's`，共 277 个带撇号词条），
      **没有** `what' s` 这种写法。视觉模型会把 `they're` OCR 读成 `they' re` ——
      那是**假阳性**，别跟着改代码；用 DOM 断言（`/\s'\s|\s'|'\s/`）证伪，别信模型的眼睛。
    - **红绿语义必须统一**：绿色 = 正确答案，红色 = 你选错的那条。
      提示区「正确答案」原来用红色、选项列表里正确项用绿色 → 同一个东西两种颜色，视觉模型判为缺陷。
    - **长释义别 truncate**：固定宽度 + `truncate` 会把「help yourself（请自...」切一半，
      等于信息丢失。改 `flex-1 min-w-0 break-words`，级别列 `ml-auto shrink-0` 固定在右侧。
    - 小学词库的单词可能是**短语**（`Good morning` / `help yourself`），显示/断言的正则要允许空格，
      只写 `[a-zA-Z'-]+` 会误判成「没显示英文」。
    - 词库 JSON 顶层是**数组**（不是 `{words:[...]}`），探查脚本别按后者写。
    - 浏览器实测脚本选择器别依赖 UnoCSS 类名（`gap-1`→`gap-2` 就废了）→ 明细行加 `data-placement-row`。
28. **阶梯铺到九年级后的坑（2026-11-21）**：
    - **本地词库一直就有八/九年级课本词表**（`PEPChuZhong8_1/8_2/9_1`、`jiJiao8-1/8-2/9`、
      `LWCZ-7~9`、`WaiYanSheChuZhong_4~6`），只是阶梯没挂上去 → 摸底测不到初三。
      用户说「要导入九年级课本」时先查 `public/list/word.json`，**别急着去下载数据源**。
    - **外研初中必须独立成一套阶梯**：外研初中词库 id 177~184 **小于**外研小学 id 187~206，
      塞进小学阶梯会破坏「每级最大 id 递增」的难度递进。
    - **`afterTop` 字段是必须的**：小学阶梯（人教新起点 / 外研小学 / KET）摸到顶**不能**喊
      「可以上高中词汇表了」，得指路去初中那套；只有含初中册的阶梯才谈高中。
    - **阶梯 id 是「每级最大 id 递增」**：体检器靠这条断言难度递进，改阶梯顺序会红。
    - **本地 207 册 vs 线上 241 册**：差的那 34 册全是雅思词汇/听力，**没有任何课本**；
      线上 `list/article.json` 只有 NCE_1~4，**没有 1~9 年级课本课文数据源**（要课文就没辙）。
    - 尺子假阳性坑：**逐级诊断**模式的报告文案是「断层在这一级」，**自适应定位**模式才是
      「定位到这一级」。测文案前先切对模式，否则尺子自己给自己判红。


## 已知缺口（master 分支本来就没有，别以为是改坏的）

- `/import`、`/nce`、`/fsrs`、`/practice-sentences`、`/login` 等页面不存在 → 404。
  `app/pages/(words)/dict.vue` 里的 `goImportPage()` 会跳 `/import`，那是**云端功能**，本地纯离线模式用不到。
- 自定义词典/个人词库依赖 Supabase（`runtimeConfig.public.apiBase`），本地没填就不可用。
- 线上站比 master 新，`dev` 分支页面多但资源走 CDN，不能直接混用。

