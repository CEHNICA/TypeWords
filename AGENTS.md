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

- 词库：`public/dicts/en/word/*.json`（207）+ `article`（**17** = NCE 4 + **莱芜课本 13**），从镜像版/课本 PDF 灌的，别重新下载。
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
| `public/list/*.json` | 补全完整索引（上游只有 1 条 CET-4）；后加：**「青少年英语」六~九年级课本册打 tag「六~九年级」并按年级重排**（见下面专门一节） |
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
| `_tools/_check_placement_ui.js` | 新增：摸底**浏览器实测** 14 项（答错提示 / 选项英文 / 明细误选 / CSV 下载内容 / 撇号无断词 / 无 JS 报错，音频噪音报错豁免）；后**重写为确定性版**（2026-11-22）：正确项从 **Vue 组件状态** 读 `correctIndex`（`.option` 元素的 `__vueParentComponent.parent.setupState.question`），第 1 题故意答错造误选样本、其余题全答对 —— 不再赌随机；英文词从提交后追加的 `.bg-third` 芯片 span 取，不解析拼接文本；英文正则放行 U+2019 弯撇号 |
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
| `scripts/extract-textbook-articles.py` | 新增：**莱芜五四制课本 PDF → 课文 article 提取器**（13 册 → 13 个 `public/dicts/en/article/LWXX_*/LWCZ_*.json` + `public/list/article.json` 13 条） |
| `scripts/textbook_text_repair.py` | 新增：课文文本清洗 + **断词修复判据 R1~R5**（尺子与修法共用同一套，`find_broken()`） |
| `_tools/check_textbook_articles.py` | 新增：课本课文体检器 **280 项**（含 HTTP） |
| `_tools/_tb_revert_check.py` | 新增：体检器**退回验证**（6 个坏样本各精确红在自己那条 + 1 个负对照） |
| `_tools/_tb_browse.js` / `_tb_layout.js` | 新增：跟打页 Playwright 实测 + 截图（书单 → 进书 → 跟打） |
| `scripts/split-article-sentences.js` | 新增：**课文切句器**（一个自然段 = 一行 → 一行 = 一句，跟打页和朗读都靠这个粒度）；缩写表分 `ABBR_ANY` / `ABBR_CAP`（大小写是语义的一部分） |
| `scripts/translate_via_llm.py` | 新增：**MiniMax 逐句翻译**（逐句串行 + 句间 120ms，缓存 `data/article-translations-llm.json`） |
| `scripts/fix_article_units.py` | 新增：课文 **unit 前缀修正**（只修「前缀错」，不补「缺前缀」）+ `sync_title_translate()` 同步中文译文编号 |
| `scripts/json_io.py` | 新增：**保持原格式写回 json**（197 册 compact 单行 / 10 册 indent=2+CRLF，写回必须用 `dump_like()`） |
| `_tools/fix_article_apostrophes.py` | 新增：英文课文撇号归一（只动 `text`/`title`，中文译文里的中文引号不动） |
| `_tools/fix_dict_clean.py` | 新增：词库清洗（控制字符 / `null` 标记 / 重复释义合并 / 已知错位修复） |
| `_tools/dedupe_dict_trans.py` / `fix_dict_relwords.py` / `fix_dict_last.py` | 新增：词库去重 9664 条 / 清空错配 relWords 16838 条 / 最后 5 条（laurel×4 + problemn） |
| `_tools/check_article_quality.py` / `check_title_unit.py` | 新增：课文质量尺子 + 中英 unit 号一致性尺子 |
| `_tools/check_dict_data.py` / `check_dict_family.py` | 新增：词库 5 类脏数据尺子 + relWords 归属尺子 |
| `_tools/check_dict_glue.py` | 改：粘连词判据加严（原判据把 greece 拆成 gree+ce，全是假阳性） |

## 莱芜课本课文（2026-11-21 新增）

PDF 源：`C:\Users\17321\WPSDrive\403466883\WPS云盘\莱芜英语课本\压缩版\*.pdf`（13 册：
小学三上~五下 6 册 + 初中六上~九上 7 册）。**山东版（莱芜五四制）**，八下整册课文客观少（11 篇）。

产物（**都不改任何前端代码**，书单页 `book-list.vue` 直接读 `public/list/article.json`）：

| 册 | 文件 | 篇数 | 字符数 |
|---|---|---|---|
| 小学三四 | `LWXX_3_1 / 3_2` | 37 / 32 | 8067 / 9030 |
| 小学四上四下 | `LWXX_4_1 / 4_2` | 30 / 26 | 12562 / 13068 |
| 小学五上五下 | `LWXX_5_1 / 5_2` | 30 / 25 | 20888 / 16372 |
| 初中六上六下 | `LWCZ_6_1 / 6_2` | 20 / 22 | 13596 / 16386 |
| 初中七上七下 | `LWCZ_7_1 / 7_2` | 24 / 24 | 23010 / 28538 |
| 初中八上八下 | `LWCZ_8_1 / 8_2` | 27 / 11 | 44329 / 18111 |
| 初中九上 | `LWCZ_9_1` | 44 | 79193 |

合计 353 篇 / 约 31 万字符 / **7108 句**（2026-11-22 切句 + 补译后）。`public/list/article.json` 里 id **250~262**，
`enName` = `lwxx_3_1`…`lwcz_9_1`，`url` = `<KEY>.json`，`length` 与实际篇数一致。

```powershell
# 提取（调试期一律先 --dump，不写文件；--full 打印全部段落；--only 只跑一册）
python scripts\extract-textbook-articles.py --dump
python scripts\extract-textbook-articles.py --dump --full --only '小学五四-三年级上册.pdf'
python scripts\extract-textbook-articles.py                # 写入模式（会改 public/）

# A/B 开关（默认全开 = 过滤生效）
$env:TTB_REJECT_ELLIPSIS='1'; $env:TTB_REJECT_LOWER='1'; $env:TTB_MIN_WORDS='4'
```

**课文有逐句中文翻译**（2026-11-22 补齐，MiniMax API 翻译）：353 篇 / 7108 句 / 已译 7108，失败 0。
翻译流水线见下面「课文数据修复流水线」。

### 提取 PDF 的坑（别再犯）

- `has_cjk()` 一刀切会误杀夹带汉字的英文行 → 用「以中文为主」比例判据（≥2 汉字且占比 ≥15%）。
- 括号动词正则太宽会吃掉课文 → 用**动词白名单**。
- 同一基线的两个 span 会拼成一行（页脚 `'Unit 1'` + 页码 `'3'` → `'Unit 13'`）→ 页脚类识别必须走 **span 列表**。
- 扫描页轻微倾斜会按基线聚行把词劈开 → 改**垂直重叠聚行**；且聚行还要卡高度比
  **min/max ≥ 0.55**（巨型装饰字母会「桥接」两行）。
- MuPDF 会给出退化 bbox（零宽）的重复字形，还会在字形内部塞真空格 char。
- 描边叠印层是同一字形画两遍（字符相同、bbox 重合 ≥70%、origin 偏移 0.3~1.1pt）→ 按 bbox 重合度去重。
- 课本有特殊字体给单词里的**单个字母**做造型（HeinemannSpecial-Bold）→ **span 边界补空格必须用几何间距**
  （gap > 0.18×size）+ 冒号后必补；按字符类别补会把 "same" 变成 "s a me"。
- 小学 "Read and enjoy" 韵文是**左右并排两栏** → 必须按列读。
  判据是「**列内存在硬折行**」（上一行没结句 + 行距 ≤1.8×字号），
  **不能**用「上一行没结句的比例」——对话气泡里只要有一句以逗号结尾，比例就超阈值，整页对话会被误当两栏。
- 小学一课 = 结构化标题行 → 下一个结构化标题行 - 1；**Unit 扉页（38pt, x≈199）是硬边界**；
  页面外侧 x≈403 的 32pt "UNIT n" 是页眉标记不是扉页。
- 小学切分点**只认结构化标题**（Lesson N / Try yourself / Review N / Read and enjoy）；
  课名/故事标题只在**同一页 head** 里找，候选需 size≥15、len≥3、首字母大写，
  并排除「上一行没结句且行距 ≤1.8×字号」的续行。
- 段跨页时排序必须按 **(页号, y, x)**；只按 y 排会把上一页的行插进当前页 → 真标题被当续行丢掉。
- 附录在书末 → 见到附录起点标记后面整段丢弃；「Grammar」用字号（≤13pt）区分正文 18pt。
- 初中不能「一页一篇」：同一课阅读材料跨页 → 改**按锚点切**。
- **PDF 撇号是 U+2019** → 课文撇号必须归一成 ASCII `'`（跟打页逐字符比对，弯撇号永远打不出来）。
- 个别字体（HVDComicSerifPro）缺 ToUnicode → 撇号变 **U+FFFD**。
- 词典有缺词（`couplets`/`phones` 不在 65k 里）→ 不能只靠词典判断词。
- PowerShell 管道缓冲：`python ... | Select-Object -First N` 输出会丢，必须重定向到文件再 `Get-Content`。

### 课文产物的字段约定

- `public/dicts/en/article/LWXX_3_1.json` = **数组**，每篇
  `{id, title, titleTranslate, text, textTranslate, audioSrc, lrcPosition, question, nameList, quote, userId}`，篇内 id 从 10000 起。
- **一句一段**：段落用 `\n\n` 分隔（上游 `genArticleSectionData` 靠这个断句；写成 `\n` → 译文错位）。
- 跟打页路由 `/practice-articles/{bookId}`，**bookId 是书 id**，篇内定位靠数组下标。
- 标题格式：`Unit N · Lesson N 课名`（小学）/ 纯话题标题（初中）。

## 课文数据修复流水线（2026-11-22 新增）

用户报「英文的翻译好像还没有放进去」+「他竟然一次性就说到底了」→ 两个问题同源：
课文导入只做了 PDF 提取和断词修复，**句子粒度太粗**（一个自然段被挤成一行），
于是朗读（`playSentenceAudio` 拿整行去发音）像「一次性读完」，译文也没地方挂。

修法走**数据层**（改 article json，**不动前端代码**）。

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
node scripts\split-article-sentences.js                            # 切句
py -3 scripts\translate_via_llm.py --batch 40 --model MiniMax-M2.7-highspeed --apply   # 翻译
py -3 scripts\fix_article_units.py --pages LWCZ_6_1,...,LWCZ_9_1 --apply              # unit 前缀
python _tools\fix_title_translate_unit.py --apply                  # 中文译文里的 unit 前缀
```

### 关键坑

1. **切句器必须区分缩写的大小写**（`scripts/split-article-sentences.js`）：
   - `ABBR_ANY`（大小写不敏感）：e.g / i.e / u.s / u.k / etc / vs
   - `ABBR_CAP`（**必须原文首字母大写**）：mr / mrs / ms / dr / prof / st / jr / sr / fig / inc / ltd / co / dept / est
   - 混在一起就会把 `They said no. Then…` 整句不切（`no.` 被当 no. 缩写）。
   → 重跑后 7107 → **7108 句**（LWCZ_7_1 +1）。
2. **切句会清空该文章的 `textTranslate`** → 改完课文**必须重跑翻译**，否则译文没了。
3. **翻译必须逐句串行 + 句间 120ms 间隔**（见硬规矩 17）；走 MiniMax API，
   上游 `translate.ts` 的百度翻译需要 appid/key，本地没有 → 前端译文只能走**预置数据 `textTranslate`**。
4. **译文回填格式**：段用 `\n\n`、句用 `\n`，与 `genArticleSectionData` 的切分**完全对齐**。
5. **翻译缓存**在 `data/article-translations-llm.json`（6698 条），重跑不会重复花钱。
6. **unit 前缀只修「前缀错」，不补「缺前缀」** —— 缺前缀 = 课本正文本来就没写 Unit 标记，
   补上去是**编造课本没有的信息**。
7. **`build_title` 保持原格式**（`Unit N · base`，不分 rp/main），避免引入新形态造成格式漂移。
8. **小学册排除在 unit 写盘范围外** —— v6 判据对小学不可信，且小学现有前缀本身是对的。
9. **改了标题要同步中文译文**：`sync_title_translate()` 把中文译文里「第N单元」的编号跟着改
   （认阿拉伯数字和中文数字两种写法）。
10. **上游词库 `relWords` 整组错配**（见下面词库节）→ `word-test.ts` 的相似度出题被污染。
11. **朗读「一句一句」的验收方式**：浏览器实测抓 `https://dict.youdao.com/dictvoice?audio=…&type=2`
    的 **`audio` 参数**（URL 里参数名是 `audio` 不是 `le`），确认它就是被点的那一句，
    不是整段/整篇。尺子：`node _tools\_check_read_aloud.js`（7 项）。
12. **撇号有多种 Unicode 形态，别只防 U+2019**（2026-11-22 踩到）：
    - 课本 PDF 里同一个撇号会出现 `’`(U+2019) / `‘`(U+2018) / **`‛`(U+201B)** /
      `‚`(U+201A) / `′`(U+2032) / `ʼ`(U+02BC) / `‵`(U+275B) 等好几种。
    - **八下 Unit 5/6/7 用的是 U+201B**，`scripts/textbook_text_repair.py` 的 `QUOTE_MAP`
      原来只列了 5 种 → 漏了 U+201B → 提取出来的课文带 `I‛m`。
    - 跟打页是**逐字符比对**，用户键盘打的是 ASCII `'` → 非 ASCII 撇号**永远打不出来**。
    - 修法（已做）：`QUOTE_MAP` 补全 9 种 + `_tools/fix_article_apostrophes.py` 归一存量数据
      （**只动 `text`/`title`**，中文译文里的 `’‘` 是中文单引号，正确，不能动）。
    - **尺子的锅**：`check_textbook_articles.py` 原来只查 U+2019 → 5 处 U+201B 全被放行（漏报）。
      改成查全部形态时又踩了第二个坑：`CURLY_APOS in text` 是**子串匹配**，
      多字符串要求连续出现整个串 → 文本里只有一个撇号时永远匹配不上（假阴性）。
      → **必须写 `any(ch in text for ch in CURLY_APOS)`**。
      这条是被 `_tools\_tb_revert_check.py`（退回验证）当场抓住的。

## 词库数据清洗（2026-11-22 新增）

用户「再看看有什么问题」深挖到词库脏数据层，**全部在数据层修，没动前端**。

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
python _tools\dedupe_dict_trans.py --apply      # 去重释义 9664 条
py -3 scripts\fill_missing_dict_translations.py --all --apply   # 补释义 1188 → 5
python _tools\fix_dict_relwords.py --apply       # 清空错配 relWords 16838 条
python _tools\fix_dict_clean.py --apply          # 控制字符/null标记/重复条目/错位
python _tools\fix_dict_last.py --apply           # 最后 5 条（laurel×4 + problemn）
```

### 判据（写之前先想清楚，别乱改）

1. **词条主释义字段是 `trans[]`（带 pos）**，`synos[]` 只是同义词补充。
   只看 `synos` 会把 9905 条正常词误判成「无释义」。
2. **去重分两套判据**：
   - `trans`（无 ws 字段）→ `(pos, cn)` 相同才算重复；
   - `synos`（带 ws 近义词组）→ 必须 `(pos, cn, ws)` **全同**才算重复
     （同中文不同 ws 是不同近义词组，去掉会丢信息；实测 296 条属此类，**不动**）。
3. **`relWords` 整组错配是上游的锅，无法复原，只能清空**。三个排除性结论（都实测过）：
   - 不是固定下标偏移（K 扫描：K=0 命中 56%，其它 K 均 ≈0.1%）；
   - 不是成对置换（抽查 0 条）；
   - 跨册回填覆盖率 **0%**（错配词头在所有册里都坏，没有干净副本）。
   - 判据**只清「彻底无关」那一档**（族里没有任何词与词头有 ≥2 字符公共前缀）。
     放弃过「相似度 < 0.75」那档 —— 误杀 `explosive←explode` / `drunk←drink` /
     `audience←auditory`（英语派生不都是前缀关系，drink→drunk 是元音变化）。
     **宁可漏报不可误清正确数据 —— 精确率优先。**
   - 已知漏报（故意保留）：`regarding←registry` / `standpoint←startle` / `cassette←cave`
     这类共享 2~3 字符前缀的错配。
4. **释义空缺 1188 → 5**：优先从离线词典（65,655 词）+ 其它 207 册复用，
   复用不回来的 355 个唯一词才送 LLM（速率 4~5 词/s，失败 0）。
   脚本要支持 `--all`（原来只处理 tags 含「六」「九」的册）。
5. **`laurel` ×4**：trans 空但 synos 里有中文 → 搬进 trans（**`problemn` 分支必须排在
   「synos→trans」分支前面**，否则会把别人的释义搬过来）。
6. **`problemn`**（beijing_junior_high_school idx 1199）是**双重损坏**：词头多一个 n，
   内容整条是 `snowy` 的（同册已有完整 snowy）→ 词头改回 `problem`，释义取自离线词典，
   snowy 那套错内容一并清掉。
7. **控制字符**：释义末尾混进 `\x08`（如 `'圆圈\x08'`），87 处。
8. **`null` 标记**：上游 null 值被字符串化（`'null （Stray）（挪、美、英、俄）斯特雷（人名）'`、
   `'…；null'`），31 处。
9. **`bridging` 释义错位**：`'unit 衔接单元'`（把同册 `unit` 的英文拼上来了）→
   改成 `n. 架桥；搭桥` + `v. 架桥；搭桥；连接`。

### 尺子假阳性（这轮踩得最狠，记一下）

- **`check_dict_data.py` 的 D3**：「所有中文都一样」会误杀 381 条 `n. 预测` / `v. 预测`
  （不同词性同中文，正常）。真缺陷是「同中文 + 其中一条 pos 为空」。
- **`check_dict_family.py` 的 v2 判据**（相似度 < 0.75）误杀一堆英语派生词，见上面第 3 条。
- **`check_dict_glue.py`** 原来只查 `synos` 为空 → `greece` 能拆成 `gree+ce`、
  `france` 拆成 `fr+ance`、`bathtub` 拆成 `bath+tub`，**全是假阳性**
  （离线词典里收录了 ce/ai/fr/er/un 这些两三字母缩写）。
  现在要求：① 词条**完全没有释义**（trans 和 synos 都空）② 拆出的两段长度 ≥4 ③ 不是缩写。
  → 全库 207 册 **0 真粘连词**。
- **`check_dict_head_mismatch.py` / `check_dict_typo.py` 已删除**（误报 10 万 / 175 条，别再跑）。

### 词库 json 的格式规矩（**写回必须照原样**）

207 册有两种形态：**197 册 compact 单行**（无 BOM / 无末尾换行）＋ **10 册 indent=2 + CRLF + 末尾换行**。
用 `json.dumps(indent=2)` 重写会把 compact 文件撑成 4 倍。

```python
import sys; sys.path.insert(0, r"...\scripts")
from json_io import dump_like, load_preserve
arr, raw = load_preserve(path)
open(path, "wb").write(dump_like(raw, arr))
```

**⚠️ 词库 json 改动不进 git**：`.gitignore` 第 46 行 `public/dicts/**` 把它们排除了
（只有 `public/dicts/en/word/CET4_T.json` 是早期 force-add 的例外）。
→ 日后从镜像版重灌词库，**本轮所有清洗结果都会丢**。
重灌后跑 `python _tools\check_dict_data.py` + `check_dict_family.py` 会立刻报红。

## 课本释义写回：复习页的中文要和课本一致（2026-11-22 新增）

用户原话：「复习一本书的时候，英语后面紧跟着的中文和课本上的不一样」。

**根因在数据层，不在前端**：复习页显示的中文 = 词条 `trans[0].cn`，
那是**通用词典**的首释义；而课本（莱芜 13 册 PDF）有自己的一套中文。
前端 `shortTrans()`（`app/pages/(words)/book-review.vue:130`）只做「取第一段 + 超 14 字截断」，
它不查课本 → 显示的自然是词典口径。

**修法（只动数据层，不改前端）**：

1. `scripts/extract-textbook-wordlists.py` 从 13 册课本 PDF 抽 word→课本中文，
   产物 `data/textbook-wordlists.json`（外层 key = 册 id，内层 key = **词库原样词头，区分大小写**）。
2. `_tools/check_textbook_trans.py --apply` 把课本释义写进该册词条的 `trans[0].cn`
   （保留原 `pos`；原通用释义追加到 `trans` 末尾，信息不丢）。
3. 写回后**必须重建查词索引**：
   `node scripts\build-word-index.mjs` → `node scripts\augment-word-index.mjs`。

结果：13 册「释义不一致」全部归零（词库 4533 词 / 命中 4377 / 不一致 0），
浏览器实测 41 对样本全一致。

**各册课本释义互相独立**（`centre` 六上「中心；中央」≠ 七上），复习哪本就显示哪本口径
—— **不要跨册合并**，也不要把某一册的口径推广到别的册。

### 抽课本 PDF 的坑

1. **两种版式**：小学（`LWXX_*`）逐行；初中（`LWCZ_*`）以 `p.N` 行分块、条目可跨行。
2. **PDF 两栏会丢英文**（`cloudy` 只剩 `l`、`d`）→ 单词必须有结构信号
   （`p.N` 收尾 / 词性标记 / 在该册词库白名单里）。
3. **四层噪声控制**：结构层（`p.N` 分块、词性标记当粘连信号切断）、
   内容层（纯 ASCII 字母 / 词性标记 / `单元词语表` / `注：` / `。` / `例如` / `意为` → 丢弃）、
   章节层（正文撞词优先级最低）、白名单层（只留该册词库词头）。
4. **多来源候选取最优**：同词多个候选 → 先按权威层级
   （总词表 tier0 > A—Z tier1 > 每单元词表 tier2 > 兜底 tier9），同级取最长。
5. **章节标题行必须独占一行且不含数字**（否则把目录行当章节）。
6. **大小写敏感**：`WHO`/`who`、`US`/`us`、`Brown`/`brown` 是不同词条；
   大小写不一致 → **歧义跳过，宁可不写**（撇号形态差异不算歧义）。
7. **音标夹在词中间**要还原词头：`Angel /ˈeɪndʒl/ Falls 安赫尔瀑布` → `Angel Falls`。
8. **残缺候选丢弃**（`cn_is_bad`）：括号不闭合 → 丢；
   末尾括号是「纯中文 1~2 字且不含『的』」而它前面（括号外深度 0）无中文 → 丢
   （如 `（shoot的过去式）（篮）` 丢了『投』字）。
9. **语法讲解框的整句**（含 `。`/`例如`/`意为`）→ 丢。
10. **PDF 会混进定位控制字符**：`LWCZ_6_1` 有 33 条释义被 `\x08`（退格符）粘在末尾
    （`泰山\x08`）→ 写回后被 `check_dict_data.py` 的 CTRL 项判脏。
    清洗函数 `sanitize_cn()` 在**提取脚本**和**对账脚本**里各一份，必须口径一致，
    否则对账会把这 33 条报成永久不一致。

### 写回与对账的规矩

- **写回前必须备份词库**（词库被 gitignore，改错无法回滚）→ 备份到 repo 外目录。
- **对账口径必须复刻前端的 `shortTrans`**（取第一段 + 14 字截断），否则「不一致」全是假阳性。
- 写回后跑 `_tools/_check_dict_format.py` 确认 BOM / CRLF / compact / 末尾换行 /
  条数 / **词头顺序**都没被破坏（写回必须用 `scripts/json_io.py` 的 `dump_like`）。
- 词库改动**不进 git**（`.gitignore` 排除 `public/dicts/**`）→ 重灌词库会丢全部写回结果。

### 浏览器实测尺子的坑

`node _tools\_check_book_review_trans.js`（改复习页 / 词库释义必跑）：

- **BaseButton 渲染的是 `div.base-button`，不是 `<button>`** → 定位用 `.base-button:has-text(...)`。
- **复习页默认全选 13 册** → 直接点 chip 是「取消」，而且干扰项会来自别的册
  （课本口径不一致，断言必然红）。必须先点「取消全选」，再只勾目标册。
- **等词库清单加载完再点 chip**（等 `已选 13 册 · 约 N 个词` 且 N > 0），
  否则点击落在还没初始化的列表上，「开始复习」按钮还是灰的，点了没反应。
- **一行「英文 + 中文」在 `.detail-row`**（`.detail-en` / `.detail-cn`），提交答案后才渲染；
  生词表里 `.option` 的 span 顺序完全不同（英文/中文/册名），别混。
- 退回验证：`_tools/_revert_check_book_review.py break|restore`
  （故意改坏一个词的释义 → 尺子必须红在「页面中文全部等于课本口径」那一条）。

## 莱芜 13 册词表对账 + 补词（2026-11-22 新增）

用户原话：「导入的英文单词准确吗？怎么感觉好像跟书籍有点差距呢就是五四教育莱芜区的那个英文单词」。

**结论**：词库原本只覆盖课本词表的 **~92%**，差的就是真漏词 + 词形变体，不是「不准」。
本轮补齐后 13 册 **MISSING 0 / 释义不一致 0 / 垃圾词头 0**。

### 唯一口径模块：`_tools/_textbook_wordsheet.py`

改词表相关逻辑**只能改这一个模块**，它对外提供：

- `heads_of(bid)` → `(order, heads)`：从课本 PDF 抽该册词头（带出现顺序）
- `gaps_of(bid, ...)`：课本有、词库没有的缺口
- `head_ok(h, dict_keys, universe_keys)`：词头是否合格（能进词库）
- `entry_alts(piece)`：**词头抽取的公共实现**（模块和诊断尺子必须共用这一份）
- `dict_path(bid)` / `load_dict(bid)`

> ⚠️ 词头抽取逻辑一旦在诊断脚本里自己抄一份，**对拍结论全是假的**。本轮 v9 就是在修这个。

### 抽取器三条铁律（每条都是被数据否掉过的）

1. **不能用「有没有音标」判断英文侧**——初中词表大量专名英文侧根本没有音标
   （`Zhangjiajie National Forest Park`、`Amazon`）。
2. **不能用「短中文行 = 分类小标题」**——实测 13 册词表里纯中文行去重 454 个，
   **绝大多数是真词义**（`进入` x4 / `不寻常的` x4 / `累人的` x4 …），只有极少数是小标题。
   靠这招过滤会误杀大量真词。
3. **正确方向 = 噪声前置过滤 + 上下文归属**：
   - 先滤掉页眉（`Reference Word List` / `Vocabulary in Each Unit` / `Vocabulary A—Z` …）、
     分类小标题（`数词`/`月份`/`星期`）、表格续表头（`续表`）、版权页与后记长段落；
   - 再用「这一行有没有英文侧」判断它是**新词条开始**还是**上一个词条的续行**；
   - **定稿 = 括号平衡 + 有英文侧 + 有中文释义**。

### 改抽取逻辑必须做新旧口径对拍

`_tools/_check_wordsheet_diff.py` 打印 old / new 两个口径的词头差集（LOST / GAIN）。

v9 的对拍结论：

- 小学 6 册：**lost=0 gained=0**，全净。
- 初中 LOST 全部是**该丢的垃圾**：页眉 `Vocabulary in Each Unit`、
  附录裸词 `wrote`/`known`/`sent`、PDF 残片 `math )n` / `v. (stole , stolen )`。
- 初中 GAIN 全部是**真词回捞**：`Zhangjiajie National Forest Park`、`Amazon`、`Helsinki`、
  `Nobel Prize`、`Hans Christian Andersen`、`Alexander Graham Bell`、`grandmother`、`maths`、
  `information technology`、`per cent` ……

### 补词规则

- 只补「**课本词表里有、词库完全没有**」的**单词型**条目。
- 跳过：教辅省略短语、书名号作品名、截断短语（含 `one's`，如 `bottom of one's`）、
  纯注释型词条、PDF 残缺词。
- **复用优先于新建**：词库已有该词就只改 `trans[0].cn`，不要新建重复条目。
- **只增不删**。
- 覆盖型写回前**先剔除与新值重复的旧行**再把新值放首位（否则撞出「同值重复」脏数据）。
- 覆盖前必须有 **repo 外备份**（词库被 gitignore，git 回滚不了）。

本轮共补 **51 词**：六上 3 / 六下 1 / 七上 5 / 八上 3 / 八下 30 / 九上 9。

### 尺子

| 尺子 | 查什么 |
| --- | --- |
| `_tools/check_book_wordsheet.py` | `MISSING`（课本有词库没有）/ `TRANS`（释义口径不一致）/ `DIRTY`（词头含中文或标点） |
| `_tools/check_book_wordsheet.py --selftest` | 尺子自身退回验证（内存里造坏样本，不碰磁盘） |
| `_tools/fix_book_wordsheet_gaps.py` | 生成补词计划；`--apply` 才写回 |

- `check_book(bid, book, order, heads, universe_keys)` 是**纯函数** → 才能在内存里造坏样本做退回验证。
- `--selftest` 4 项：干净样本 0 问题；删 `centre` → 精确报 `MISSING centre`；
  改坏 `banana` 释义 → 精确报 `TRANS banana`；混入垃圾词头 `续表` → 精确报 `DIRTY 续表`。
- **文件级退回验证**（真删 `LWCZ-8-2` 的 `humorous` → 尺子红在 `MISSING humorous`、退出码 1
  → 从 `破甲\_dict_backup_20261122e` 恢复 → 全绿）。

### 本轮踩的坑

1. **课本值是页面值的前缀 = 课本释义被 PDF 截断** → **保留页面完整值，不覆盖**
   （如 `inspiration` 课本 `鼓舞人心或` vs 页面 `鼓舞人心或振奋人心`）。11 条。
2. **括号注释在词头侧、不在释义侧**：`Miss /mɪs/ （对未婚女子的礼貌称呼）` + 下一行 `小姐；女士`
   → 覆盖课本释义时括号那句自然丢掉，别把它当释义。
3. **「释义括号不闭合」不能当全库通用尺子**——上游词典数据里 5704 条普遍半/全角混排，
   只对莱芜 13 册查。
4. `LWCZ-7-2` 的 `mm` 原条目是拼凑的（首释义 `/`、`millimeter) 毫米` 碎片、
   `etymology` 混了别的词源串）→ 已重写为 毫米（millimeter）/ 唔，嗯 / 缅甸的域名，
   `etymology` 置 null。
5. PDF 私用区字符：八下音标是 `` = `Amazon`
   → heads 侧要剥 `-`。

## 六~九年级课本词表可见性（2026-11-21 新增）

用户反馈「六年级到九年级的单词好像还没弄上」。**查完发现：词库数据一册不缺**
（207 册全在盘且非空，六~九年级 PEP/外研/冀教/上海/牛津全都有）。真正的毛病是**可见性**：

- `app/components/list/DictGroup.vue:15-19` —— `currentTag = tagList[0]`，
  每个分类**默认只露第一个 tag 页签**。
- `app/pages/(words)/dict-list.vue:33-58` `groupByDictTags()` —— 页签 key 顺序 =
  「按数组顺序遍历，每册把自己 push 进它**所有** tag 的桶」。
- 于是「青少年英语」分类第一个页签是「通用」（高考 3500 / 中考核心词…只有 4 册），
  PEP/外研/冀教的六~九年级课本册**全藏在后面页签里**，用户以为没弄上。

修法走**数据层，不动前端**：

- `scripts/tag-junior-textbooks.js` 给 30 册六~九年级课本册打上 tag **「六~九年级」**
  并放在 `tags[0]`，同时把「青少年英语」分类里这 30 册挪到数组最前面，
  组内按 **(年级, 册序, 教材)** 排：六上 → 六下 → 七上 → 七下 → 八上 → 八下 →
  九全 → 九上 → 九下。
  → 该分类的第一个页签变成「六~九年级」，打开就看得见，且顺序按年级。
- 30 册 = 人教 PEP 7 + 人教新起点 2 + 外研 8 + 新外研 2 + 外研新起点 2 +
  冀教 7 + 上海版 1 + 上海初中牛津 1。
- 「通用/新概念英语/其他」和高中册**不进**这个 tag。

**坑**：

1. 人教 PEP 的册子名只有「六年级上」这种光秃秃的名字，**认不出「人教版」三个字**，
   只能靠 `enName`（`liu1/qi1/ba1/jiu/…`）认；漏了它会少 7 册。
2. 「上海初中牛津词汇」名字里没有年级，要按 `enName === 'SHjuniormiddleOxford'` 特判成初中通用。
3. 数组重排**安全**：所有页面都是按 id 查（`find` / `Map`），没有按下标取的地方。
4. `public/list/word.json` 是**本地补全的索引**，日后从镜像版重灌词库会被覆盖 →
   覆盖后跑 `python _tools\check_dict_list.py` 会立刻报红，重跑上面的脚本即可恢复。

## 体检器（改测试链路必跑）

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
python _tools\check_test_flow.py --http     # 17 项，全绿 exit 0
python _tools\check_placement.py --http    # 72 项，全绿 exit 0
python _tools\check_book_review.py --http  # 38 项，全绿 exit 0
python _tools\check_article_import.py --http # 81 项，全绿 exit 0
python _tools\check_word_lookup.py --http     # 89 项（查词），全绿 exit 0
python _tools\check_textbook_articles.py --http # 280 项（莱芜课本课文），全绿 exit 0
python _tools\check_dict_list.py --http         # 65 项（词典列表/六~九年级可见性），全绿 exit 0
python _tools\_tb_revert_check.py             # 课文体检器退回验证（坏样本精确命中），全绿 exit 0

# —— 2026-11-22 新增 ——
python _tools\check_article_quality.py        # 课文质量：行内多句 / 句首小写 / 疑似乱序，失败项 0
python _tools\check_title_unit.py            # 英文 Unit 号 vs 中文「第N单元」一致，失败项 0
python _tools\check_dict_data.py             # 词库 5 类脏数据（D1~D5），全 0
python _tools\check_dict_family.py           # relWords 归属错误 0 条
python _tools\check_dict_glue.py             # 粘连词，全库 207 册 0 真粘连
python _tools\check_textbook_trans.py       # 课本释义对账（13 册「释义不一致」= 0）
python _tools\_check_dict_format.py         # 词库格式（对照备份：BOM/CRLF/compact/条数/词头顺序）
node   _tools\_check_read_aloud.js           # 朗读「一句一句」浏览器实测 7 项
node   _tools\_check_book_review_trans.js   # 复习页课本释义浏览器实测（41 对样本全一致）
```

`node _tools\_check_lookup_ui.js` 走 Playwright 实测点词（查词链路每次改动必跑），
`node _tools\_check_cross_browser.js` 跑跨浏览器闭环。
`node _tools\_check_placement_ui.js` 跑摸底答题实测（摸底页每次改动必跑），
`node _tools\_check_placement_ladders.js` 跑 8 套阶梯加载实测（改了阶梯/词库就必跑），
`node _tools\_check_placement_advice.js` 跑报告页文案实测，
`node _tools\_shot_placement.js` 出「答错后 / 报告页」两张截图给视觉模型验收，
`node _tools\_shot_setup.js` 出 setup 页桌面 + 窄屏截图给视觉模型验收。
`node _tools\_check_dict_visibility.js` 逐个分类、逐个标签页点开，扒出**每个页签下真正可见的册子**
（查「某类词到底露不露得出来」用它，别只读 JSON），
`node _tools\_shot_dict_list.js` 给词典列表页出截图给视觉模型验收。

词典扩充（改了词库/查词就重跑）：

```powershell
node scripts\build-word-index.mjs     # 重建教辅词库索引
node scripts\augment-word-index.mjs   # 再灌 CC-CEDICT + 词形映射（缺词典会自动下载）
node _tools\_diag_coverage2.mjs       # 看文章词覆盖率
```

**全量回归一条命令**（2026-11-22 新增，dev server 要开着）：

```powershell
& _tools\_run_all_checks.ps1     # 末尾打印「失败项合计: N」，必须是 0
```

它把上面 17 个 py 尺子 + 4 个 node 浏览器实测串着跑一遍。
**尺子文件不在就 SKIP，别当失败** —— 2026-11-22 核对时发现
`_tools\check_skip_bridge.py` 和 `_tools\_check_skip_bridge_ui.js`（上一轮「跳读桥」）
**在这个工作树里根本不存在**，`app/components/article/TypingArticle.vue` 里也没有跳读桥代码
（`_shots\skip_bridge_page_1.png` 是旧截图残留）。跳读桥那摊活目前**不在本树**，
要么重做要么从回归清单里删掉，别让回归脚本长期报红。

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
13. **跟打页的「重要提示」弹窗会禁用键盘监听**：`ConflictNotice` 开着时 `useDisableEventListener`
    把 `window.disableEventListener` 置 true → 键盘事件被吞 → **打不了字**。Playwright 实测必须先点
    `#dialog-ok` 关掉它（该按钮还会被 `.panel-wrap` 挡住，用 `evaluate(el => el.click())`）。
14. **read / grep 工具显示会丢字符**：`emitter.off(EventKey.onTyping, onTyping)` 会被显示成少了
    `, onTyping` —— 拿它当 edit 的 old_string 必然匹配失败。改 `TypingArticle.vue` 这类 **CRLF** 文件时，
    用 bash 的 `[System.IO.File]::ReadAllText` 取真实字节再替换（顺手把行尾统一回 CRLF）。
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

29. **词典列表「默认只露第一个 tag 页签」（2026-11-21）**：
    - `DictGroup.vue` 的 `currentTag = tagList[0]`，页签 key 顺序由 `word.json` 的**数组顺序**
      + 每册 `tags` 的顺序决定 → 想让某组默认可见，就让它在数组里靠前、且 tag 排 `tags[0]`。
    - `groupByDictTags()` 把每册 push 进它**所有** tag 的桶 → 打一个 tag 不会从别的 tag 里消失。
    - **数组重排安全**：全项目都是按 id 查（`find`/`Map`），没有按下标取词库的地方。
    - `public/list/word.json` 是**本地补全的索引**，日后从镜像版重灌会被覆盖 →
      覆盖后 `python _tools\check_dict_list.py` 立刻报红，重跑 `node scripts\tag-junior-textbooks.js` 恢复。
    - **行尾**：仓库 `core.autocrlf=true`，Windows 上 `git checkout` 会把工作区变成 CRLF →
      已加 `.gitattributes` 把 `public/list/*.json`、`scripts/*.js`、`_tools/*.py` 钉成 LF；
      体检器对行尾按「统一即可」判，不硬钉 LF（那不是缺陷，是环境差异）。
30. **人教 PEP 的册子名认不出教材名**：`六年级上` / `七年级上` 这种名字里没有「人教版」，
    靠 `enName`（`liu1/qi1/ba1/jiu/san1…wu2`）才认得出；
    「上海初中牛津词汇」名字里没年级，要按 `enName === 'SHjuniormiddleOxford'` 特判。
    → 写按教材分类的脚本时漏掉这条会少 7 册。


## 已知缺口（master 分支本来就没有，别以为是改坏的）

- `/import`、`/nce`、`/fsrs`、`/practice-sentences`、`/login` 等页面不存在 → 404。
  `app/pages/(words)/dict.vue` 里的 `goImportPage()` 会跳 `/import`，那是**云端功能**，本地纯离线模式用不到。
- 自定义词典/个人词库依赖 Supabase（`runtimeConfig.public.apiBase`），本地没填就不可用。
- 线上站比 master 新，`dev` 分支页面多但资源走 CDN，不能直接混用。

## 上游既有行为（看着像缺陷，其实不是，别去「修」）

- **跟打页的空格读不出来**：`TypingArticle.vue` 把句子按词切成 `.word`（inline-block），
  空格由 `Space.vue` 的**空 span**（`width: 0.6rem`）渲染。
  → `innerText` 读出来是 `HelloElevationI'mLiMing.` 这种**连成一坨**的样子，
  **视觉上是有空格的**。别据此判定产物有 bug，要看截图。
- **≤1439px 视口下课文目录面板变全屏 modal**：`PracticeLayout.vue` 的
  `@media (max-width: 1439px)` 把 `.panel-wrap` 改成全屏 + `rgba(0,0,0,0.5)` 遮罩（z-index 1000），
  会盖住课文。**所有书都这样**（NCE 也一样），与课本数据无关；≥1440px 才是右侧停靠。
  要给截图验收用 **1600 宽**视口。
- **跟打页首次进入弹「重要提示」引导弹窗**（讲键盘冲突插件），点「关闭」即可。
- **跟打页两条 console error**（`Cannot set properties of undefined (setting 'volume')` /
  `play() failed because the user didn't interact`）是上游既有，不算缺陷。
- 课文目录面板在跟打页是**右侧固定面板**，正文在中间；`article-content` 的矩形是
  `x=432, width=960`（1600 视口）。


## 本地词表导入（2026-11-22 新增）

上游 master 的词表链路是**断的**：词典详情页有「导入」按钮 → `nav('/import')`，但 `app/pages`
下根本没有 `import.vue` → 404 死链；而且上游只有「手动一个个加词」，没有批量导入。
本轮把整条链补齐，**纯本地、零云端、不新增 IndexedDB schema**。

### 落地形态

- `app/core/utils/custom-word-import.ts` —— **纯解析层**（零依赖、无 DOM、不碰 store）：
  表头归一化与别名、分隔符探测、引号转义、列识别、单词合法性、UTF-8/GBK 解码。
  独立成模块是为了能单独测边界用例（`_tools/check_import_parser.mjs` 直接 import 这份 TS 跑断言）。
- `app/components/word/ImportWordList.vue` —— Dialog 形态的导入组件（Header/Body/Footer 三段式）。
- `app/pages/import.vue` —— 接住上游死链的薄壳页，把 query（`type` / `targetId`）交给同一个组件。
- `app/pages/(words)/dict-list.vue` —— 词典列表页加「导入词表」按钮（主入口）。
- `app/components/BaseTable.vue` —— **补上上游缺失的导入按钮**：
  上游声明了 `import` 事件、`dict.vue` 也传了 `onImport`，但工具栏里**从没 emit('import')** → 那个入口是死的。
  新增按钮复用已有的 `$t('import')` key（14 个语言包都有，**不新增语言包条目**）。

### 关键设计决定

- **复用上游已预留的 `custom` 词书机制**（`Dict.custom` / `Word.custom` / `createCustomDict()`），
  持久化走既有 `dataSync.saveDictState()` → **不新增 IndexedDB schema，零迁移风险**。
- 词书 id 用 `custom-dict-<timestamp>` 前缀，不与内置词库 id（1..265）撞号。
- **合并只对 custom / system 词典生效**：内置词典（CET-4 那些）的词条是按需下载的，
  `shakeCommonDict()` 存盘时会把非 custom、非 system 词典的 `words` 整份清空 → 往里塞词等于白干。
  所以目标若是内置词典，**降级成新建 + 如实文字提示**，不能让用户以为合并成功了。
- 合并模式**只新增不覆盖**：同名单词跳过并计数（不删用户已有的编辑）。
- 入口形态：**一个入口 + 一个出口** —— 词典列表页一个按钮 → Dialog → 选文件 → 预览 → 导入 → 落 `/dict`；
  `/import` 页面只作死链补丁的薄壳，不进主导航。

### 踩过的坑（真踩，别再踩）

1. **TS/JS 注释里出现 `*/` 会提前闭合块注释** → 整页 Vite Error（写 `**/import` 这类就中招）。
   静态尺子里有专门的「块注释成对闭合」判据（剥字符串+行注释后数 `/*` `*/`）。
2. **`①` 不能作标识符**（那是正则里的字符范围写法，不是变量名）。
3. **computed 在 `<script setup>` 的 script 里必须写 `.value`**：
   裸写 `isMergeMode` 拿到的是 ref 对象，**恒为 truthy** → `if (!isMergeMode && ...)` 永远不成立
   → 词书名永远空着 → 提交被「给这本词书起个名字」拦下。**本轮真踩了。**
   （这个文件里 `ref()` 没被 reactivity transform 改写，编译产物里就是 `let bookName = ref("")`；
   要确认 transform 开没开，直接看 Vite 编译产物 `/_nuxt/components/...`。）
4. **上游 `Dialog.vue` 靠 `watch(modelValue)` 的「变化」来打开**：`visible` 初始 false，
   `onMounted` 只在 `modelValue === undefined` 时才打开 →
   **挂载时直接传 `true`，弹窗永远不出现**。`/import` 薄壳页必须 `ref(false)` + `onMounted` 里置 true。
5. **取 pinia 别用 `Symbol.for('pinia')`**：pinia 用的是**本地** `Symbol('pinia')`，
   按 `provides[Symbol.for('pinia')]` 永远拿不到 → 走 `app.config.globalProperties.$pinia`
   （或用 `Reflect.ownKeys` 扫 provides）。
6. **IndexedDB 里存的是 `{val, version, updated_at}` 包装**（`persistLocalState` 里 `JSON.stringify`），
   词书在 `data.val.word.bookList`，**不是** `data.word.bookList`。
7. **`shakeCommonDict` 会清空内置词典的 words** —— 见上面「关键设计决定」。

### 尺子

| 尺子 | 覆盖面 |
| --- | --- |
| `_tools/check_custom_import.py` | 静态：文件存在、入口挂载、不新增 IndexedDB schema、id 前缀、别名表覆盖、块注释配对 |
| `_tools/check_import_parser.mjs` | 解析层单测 58 项：Node 24 直接 `import` 那份 TS 跑断言（引号转义、字段内换行、CRLF、BOM、GBK 回退、坏行、重复词…） |
| `_tools/_check_custom_import_ui.js` | 浏览器端到端 40+ 项：入口 → 预览 → 导入 → Toast → store → IndexedDB → 刷新后仍在 → 合并模式 → 无云端请求 → 无页面报错 |

浏览器尺子要点：干净 profile（`newContext` 不带 storageState）→ IndexedDB 是空的；
`localStorage['tour-guide']='1'` 打掉上游 Shepherd 新手引导遮罩；
`input[type=file]` 是 hidden 的，用 `setInputFiles`；
BaseButton 渲染成 `div.base-button` 不是 `<button>`。

**尺子自己也踩过的坑（比业务 bug 更误导人）**：
pinia 取法写错过（`Symbol.for` → 恒 null）、IndexedDB 读路径写错过（少了 `.val`）、
合并用例的期望值写错过（喂了整份重复的 CSV，按语义应该是「1 重复 + 1 新增」）。
**判据写歪比数据缺陷更误导人 —— 改完尺子必须连跑 ≥3 次 + 退回验证（故意塞坏样本看它红在正确的那条）。**

## 线上词库补充（2026-11-22）

旧账②：把线上词库补到本地，**只拉有用的 10 册**。已完成。

### 线上资源到底在哪（踩过坑）

- **词库文件不在 typewords.cc 同域**：https://typewords.cc/dicts/en/word/x.json 返回的是 SPA fallback 的 text/html。
- 真相在 dev 分支的 pp/core/config/env.ts：RESOURCE_URL = 'https://files.typewords.cc/'
  - 清单（**只是默认展示列表，不全**）：https://files.typewords.cc/list/word.json → 194 条
  - 完整清单（**schema 不同**：id 是英文短名如 ieltsWang3）：https://typewords.cc/list/word.json → 241 条
  - 词库文件真实路径：https://files.typewords.cc/dicts/en/word/<url>（files 清单没列的文件也能下）
- 两份清单对完的结论：**files 域那 194 册本地全有**（本地 207 = files 194 + 莱芜 13 册）。
  241 份里本地独有 47 个 url，其中 37 册是「雅思听力 dayN」噪音（每册 22~78 词），判为不拉。

### 拉进来的 10 册（public/dicts/en/word/，清单 id 266..275）

| id | enName | 显示名 | 词数 |
|----|--------|--------|------|
| 266 | ieltsWang3 | 雅思wang C3 | 1134 |
| 267 | ieltsWang4 | 雅思wang C4 | 346 |
| 268 | ieltsWang5 | 雅思wang C5 | 1566 |
| 269 | ieltsWang11 | 雅思wang C11 | 1611 |
| 270 | ielts-real-1 | 雅思 real 词汇 1 | 736 |
| 271 | ielts-real-2 | 雅思 real 词汇 2 | 402 |
| 272 | ielts-real-3 | 雅思 real 词汇 3 | 256 |
| 273 | ielts-real-4 | 雅思 real 词汇 4 | 201 |
| 274 | ielts-real-5 | 雅思 real 词汇 5 | 183 |
| 275 | frequently_used_words03_level3 | 超高频单词level 3 | 1435 |

注意 enName 冲突：本地已有 requently_used_words03 = 超高频单词level 2（url requently_used_word02.json），
线上 level 3 用 requently_used_words03_level3 避开。

### 铁律

1. **清单只能按条目合并，绝不整份覆盖。** 本地有莱芜 13 册线上没有；两边 id 空间不同（本地 1..275，线上主站是英文短名）。
2. **清单格式 = 2 空格缩进 + 末尾换行**（check_dict_list.py 逐字节校验，写歪就红）。
3. **本地词库比线上原始数据新**（本地清过 relWords 重复、trans 重复）→ **拉新册可以，覆盖旧册就是倒退**。
4. **线上原始数据的 relWords 会整组挂错词头**（实证：IELTS_WANG_3 第 0 条 bility 挂着 ackground 的词族，
   第 2 条 ccountant 挂着 charge；重新下载线上原件一模一样 → 上游自己的锅，不是我们拉的锅）。
   判据沿用 ix_dict_relwords.py（词族与词头公共前缀 < 2 字符 → 判错配），清空成 {root:'', rels:[]}。
   import_online_dicts.py 已内置这一步（统计项 D6）。
5. **补不上的中文释义直接删词条，不编造释义**（本地 207 册 D1=0 是标准）。
   data/cedict.txt.gz **不是**中英词典（是「中文词条→英文释义」的混合词典），**补不了中文释义**，别拿它补。
6. **加完词必须重建查词索引**：
ode scripts/build-word-index.mjs → 
ode scripts/augment-word-index.mjs
   （本次 33376 → 67132 词）。
7. **词库数据被 gitignore**，commit 只含 public/list/word.json + _tools/import_online_dicts.py；
   写盘前后都要有 repo 外备份（%TEMP%）。

### 工具

_tools/import_online_dicts.py：下载 → 清洗 → 落地 → 按条目合并清单；--dry-run 只报告。
清洗口径与 check_dict_data.py 一致：D2 同 (词性,中文) 去重 / D3 同中文缺词性删 / D4 控制字符 / D6 错位 relWords 清空 / 无释义用 data/word-index.json 补，补不上的删。
