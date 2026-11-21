# TypeWords 本地源码部署

## 这是什么

`typewords.cc` 的**官方开源源码**（上游 `zyronon/TypeWords`，GPL-3.0，12k+ star）。
你给的 `CEHNICA/TypeWords` 只是上游的一个 fork（0 star），README 里的 clone 命令还指向
`zyronon/TypeWords.git`。

- 上游：https://github.com/zyronon/TypeWords
- 本 fork：https://github.com/CEHNICA/TypeWords

## 和「逆向镜像」的区别

| | 逆向镜像 `typewords-mirror` | 本源码版 `typewords-src` |
|---|---|---|
| 内容 | 线上构建产物（_nuxt 静态包 + Python 代理） | 完整 Nuxt 4 源码（app/、composables、stores） |
| 能改吗 | 基本不能改，只能读 | 能改，改完热更新 |
| 词库 | 211 个文件 / 425 MB（从线上扒的） | 开源只带 2 个示例，**已从镜像灌入 211 份** |
| 后端接口 | 靠 server.py 代理线上 API | 本地跑，可换 Supabase 配置 |
| 启动 | `启动.cmd`（Python + 静态资源） | `启动.cmd`（pnpm run dev，端口 5567） |

源码版的独有价值：记忆曲线算法（ts-fsrs）、7 种练习模式、词库编辑/导入导出、
自定义词典、Web + 小程序 + VsCode 全套实现，都在代码里，可以随便改。

## 启动

双击 `启动.cmd`，或手动：

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
pnpm install
pnpm run dev
```

打开 **http://localhost:5567**

> 必须用 `localhost`，不能用 `127.0.0.1` —— 埋点按 hostname 判断。

## 环境

- Node v24.12.0
- pnpm 10.30.1
- 依赖已装（node_modules 就位）
- 词库已就位：`public/dicts/en/word` 207 份 + `article` 4 份 = 211 个文件 / 425 MB

## 已验证

- 首页 / `/words` `/dict-list` `/articles` `/setting` `/help` `/about` 全部 200
- 词典列表渲染正常，CET-4 显示 2607 词
- 词典详情加载完整（音标、释义、例句、短语、近义词）
- 加入书单 → 学习设置 → 练习页 `/practice-words/1` 正常出词、分组（20词/组）
- 控制台无 error（仅 Nuxt `<NuxtPage>` dev 警告 + Vite 动态 import 警告，均无害）

## 注意

- `pnpm run dev` 是开发服务器，首次冷启动约 5~15 秒。
- 想出静态站：`pnpm run generate`。
- 词库文件体积大（425 MB），`git status` 会看到 `public/dicts` 全是未跟踪文件，
  已加进 `.git/info/exclude`。

## 单词测试 / 复习 五个入口到底怎么用（2026-11-21 重做）

在 `/words` 页，主按钮（橙色）就是当前模式，旁边 **▼ 下拉**里可以切模式，右边是「自由练习」。
下面五个是**不同的事**，别混：

| 入口 | 干什么 | 需要什么条件 | 出多少题 |
|---|---|---|---|
| 开始学习（智能学习） | 按记忆曲线安排今天的新词 + 到期复习 | 选了词典即可 | 每日目标（默认 20） |
| 复习 | 只测**到期**的旧词 | 今天有到期词，否则灰（悬停会说明） | 到期词数 |
| 随机复习 | 从**学过的词**里随机抽来测 | 学过 ≥ 10 个词 | 对话框里选 |
| **单词测试** | 按**学习顺序**测已学的词 | 学过 ≥ 10 个词 | 一轮最多 20 个 |
| **随机单词测试** | 从整本词典**随机抽词**测（不管学没学过） | 只要选了词典 | 对话框里选（默认 50） |
| 自由练习 | 随便点词自己刷，不计成绩 | 无 | — |

**老师要拿词典测学生 → 用「随机单词测试」**（范围 + 数量自己定，0 进度也能用）。
**想检验自己学过的 → 用「单词测试」**（按学习顺序，一轮 20 个）。

改造前的老毛病（都已修）：

- 「单词测试」在 0 进度时是灰的，而且**灰得没有解释**，hover 也弹不出来 → 现在灰按钮一律
  悬停就说清为什么灰（`.disabled` 里去掉了 `pointer-events: none`，点击仍被拦住）。
- 「随机单词测试」也被「先学 10 个词」卡住 → 已解除。
- 随机测试的题量是**整本词典 2607 词**一次性倒出来 → 现在单轮 20 个（随机模式按你选的数量）。
- 测完没小结，答错不告诉你 → 现在结束出成绩卡：答对 X/Y、错词列表（自动进错词本）、
  「再测一轮 / 返回词表」。
- 没作答直接跳下一题，原来会出现「答对 0/2」却又写「全对，一个都没错」→ 现在未作答单独
  标出来并计入错词。

答题快捷键：选项后面的 `[1] [2] [3] [4]` 就是 A/B/C/D 的快捷键（可在设置里改），
`Space` = 下一题。

体检器（改这块后必跑）：

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
python _tools\check_test_flow.py --http
```

17 项，全绿才 exit 0。

## 水平摸底测试（本地新增，2026-11-21）

上游 master **没有**分级/摸底功能（`origin/dev` 的 `/test` 是作者的私有词库后台，跟水平测试无关）。
本地新增 `/placement-test`：给孩子做「我现在小学英语到几年级水平」的摸底。

**入口**：`/words` 页 → 「水平摸底测试」卡片 → 「开始摸底」。

**难度轴 = 教材年级**。数据来自本地已灌的教材词表（`public/list/word.json` 里 207 本）：

| 阶梯 | 级数 | 覆盖 |
|---|---|---|
| 莱芜小学五四（山东版） | 8 | 三上 → 六下（**默认**） |
| 人教版 PEP | 10 | 三上 → 初中七下 |
| 人教版新起点 | 12 | 一上 → 六下 |
| 外研版 | 12 | 一年级 → 六年级 |
| 冀教版 | 10 | 三上 → 六下 |
| 剑桥 JOIN IN / KET | 1 + 1 | 综合词表（不出年级结论，只估词汇量） |

> 「鲁教版」= 本地词库里的 **莱芜小学五四（山东版）**（山东莱芜五四制，常被叫鲁教版）。
> 小学段只到五下，**六年级起接初中五四**，所以阶梯做成 8 级到六下。
> 阶梯表第一位就是它（默认教材取 `PLACEMENT_LADDERS[0]`），打开即命中。

**两种测法**（setup 页二选一）：

| 测法 | 逻辑 | 回答什么问题 |
|---|---|---|
| 自适应定位 | 从最低级起步，答对升一级、答错退一级（`PLACEMENT_STEP_JUMP = 1`） | 「我大概几年级水平」 |
| 逐级诊断 | 每级固定抽题（3/5/8/10 题），**只升不降**，走完最高级 | 「哪一册开始吃力」 |

**逐级诊断出年表**：每个年级一行（答对/总题/掌握率/词数），进度条绿 ≥80% / 黄 60~80% / 红 <60%，
**第一个掌握率 <60% 的年级 = 断层**。词汇量按「水平上限年级」的**累计口径**折算
（`levels[weak-1].cumulative + 本级词数 × 掌握率`）—— 不能把各级词表词数直接求和，
小学各册之间大量重复词会被重复计入，虚高。全年级都过 → 取整条阶梯累计词量。

干扰项取同级 + 邻级的词，并排除释义与题干相同的词，防止蒙对和歧义。
释义必须精简（小学词库释义动辄几十字，截到 ≤14 字）。

**结束条件三选一**：题量用完（10/20/30）／已答 ≥5 且连错 2 题（撞墙）／已在最高级且连对 3 题（封顶）；
逐级诊断则是走完最高级为止。

**报告给老师三样东西**：年级定位（约 X 年级水平）+ 估算词汇量 + 错词表。
错词可**导 CSV**（`摸底测试_YYYY-MM-DD.csv`，带 BOM，Excel 直接开）或**一键进错词本**。

未作答不许跳题（`Space` 在没作答时无效），未作答计入成绩并进错词本 —— 否则摸底结果会缺题。

**残缺词条防御**（小学词库有一批词条缺 `relWords.rels` / `trans`，上游 `buildQuestion` 直接访问会崩，
整道题静默不渲染）：`app/core/utils/word-test.ts` 里加 `relsOf()` + `trans` 兜底，
摸底页再叠一层 `sanitizeWord()` 补齐结构（进错词本后词条详情页也不崩）。

体检器（改这块后必跑）：

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
python _tools\check_placement.py --http     # 32 项
```

## 整本复习（全量逐词，2026-11-21）

用户诉求：小学刚毕业的孩子，把**三上到五下这几本书的单词全部过一遍**，
一个一个点完（选择题），最后总结「这几本书他掌握到什么水平」。

上游 master 没有这个功能，本地新增 `/book-review`。

**入口**：`/words` 页 →「整本复习」卡片 →「去复习」；或摸底页 setup 页 →「整本复习（全书逐词）」。

**核心规则**

| 项 | 做法 |
|---|---|
| 册子多选 | 教材按钮（7 套阶梯）+ **册子 chip 网格多选**，每册显示词数；全选 / 取消全选 |
| 全量覆盖 | 选中的每册**每一个词都要过一遍**，不是抽样 |
| 去重 | 跨册重复词只过一遍（莱芜三上~五下 = 6 册 873 词 → 去重后 **803 词**） |
| 干扰项 | **优先取同一册**的词（不跨量级），并排除与题干同释义的词 |
| 「不认识」 | 一键标记生词 + 跳过（几百题全靠四选一根本做不完），跳过时显示正确答案 |
| 续做 | **每答一题就落一次盘**，中断/刷新后接着做；键盘 1-4 选选项、Space 下一题 |

**进度存储用 localStorage**（不是 IndexedDB）。
本机 idb-keyval 的 IndexedDB 出现库名退化（`keyval-store@1` / `keyval-store@1@1`）且
`transaction('keyval-store')` 报 object store 不存在 → 写进去读不出来。
`app/core/utils/placement-progress.ts` 用同步版 `readJson/writeJson` + try/catch。
桶按「教材 + 册子组合」分桶（`tw-book-review:<ladderKey>:<册子下标逗号分隔>`）防串味；
另存 `tw-book-review:last` 指针，解决「刷新后默认全选册子 → 查不到上次那个桶 → 找不到进度」的坑，
setup 页据此显示「接着上次那套（N 册，已过 N 词）」。

**报告给老师**：结论（这套全掌握了 / 水平到《X》为止）+ 综合掌握率 + 已确认掌握词数 +
推算词汇量 + **每册掌握情况表**（答对/测 · %）+ 生词表（分页 50/页，可全部展开）。
第一个掌握率 <60% 的册子判为**断层**。
生词可**导 CSV**（`整本复习_YYYY-MM-DD.csv`，带 BOM）或**一键进错词本**（有 Toast 反馈）。

**词汇量口径**：不把各册词数直接求和（重复词虚高），用
`已确认掌握词数 + round(未测数 × 当前掌握率)` 折算，与摸底的累计口径一致。

体检器（改这块后必跑）：

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
python _tools\check_book_review.py --http     # 25 项
```

## 英语音标页（本地新增，2026-11-20）

镜像版/线上站有的 `/phonetics` 音标教学页，master 分支上游没有，已移植成源码版原生页面：

| 文件 | 作用 |
|---|---|
| `app/core/data/phonetics.ts` | 48 个英式音标数据（20 元音 + 28 辅音）、6 大分类、筛选器 |
| `app/assets/css/phonetics.scss` | 页面样式（主题变量自适应浅色/深色） |
| `app/pages/phonetics.vue` | 页面本体：卡片网格、点击发音、详情弹窗、随机练习 |
| `app/layouts/default.vue` | 侧边栏 + 移动端顶栏加了「音标」入口 |

资源（48 个 mp3 + 48 个 mp4）已从镜像灌到 `public/sound/phonetics/`、`public/video/phonetics/`。

已实测：`/phonetics` SSR 出 48 张卡；点音标 → `GET /sound/phonetics/long-i.mp3` 206；
点详情 → 弹窗出视频 `GET /video/phonetics/long-i.mp4` 206；筛选全部/元音(20)/辅音(28)、
随机练习、紧凑/宽松、Escape 关弹窗均正常；本页无控制台 error。

## 踩过的坑

**`@vue-macros` 的 reactivity transform：`$ref` 变量在 script 里不能写 `.value`**

项目装了 `@vue-macros/nuxt`，reactivity transform 默认开启，`let x = $ref(0)` 之后
**script 代码里直接用 `x`，写 `x.value` 会拿到 undefined**（模板里仍自动解包）。
症状：页面渲染出骨架但列表全空、`filter()` 之类返回空数组，且不报任何错。
写新页面时，`$ref` / `$computed` 一律用裸变量名。

**`Cannot find module 'pathe'`**
上游 `nuxt.config.ts` 直接 `import { resolve } from 'pathe'`，但 `pathe` 没写进
`package.json` 的依赖（pnpm 严格依赖模型下不会自动 link）。已执行 `pnpm add -D pathe`
修好，package.json 里多这一行。**以后重装依赖如果又报这个错，先 `pnpm add -D pathe`。**

**dev server 挂在临时任务上会被掐断**
`pnpm run dev` 若由会话的后台任务拉起，任务到时限后进程被杀、端口 5567 立刻失效。
现在改用独立进程常驻：

```powershell
Start-Process -FilePath "$env:APPDATA\npm\pnpm.cmd" -ArgumentList 'run','dev' `
  -WorkingDirectory 'C:\Users\17321\Documents\破甲\typewords-src' `
  -WindowStyle Hidden -RedirectStandardOutput '_dev.log' -RedirectStandardError '_dev.err.log'
```

日志在 `_dev.log` / `_dev.err.log`。

## 学习进度存哪

源码版默认**纯本地**：进度和词库设置存在浏览器 IndexedDB（`keyval-store` / store `keyval`），
不联网上传。换浏览器或清缓存就没了。

想在「设置」页填 Supabase 的 url/key 可以开启云同步（对应 typewords.cc 官方那套后端），
填完进度就跟账号走、跨设备同步。

## 镜像版的老毛病（回退时会踩）

`typewords-mirror` 的 `_serve.ps1` 是**动态找端口**（8912~8942 轮询），端口一变，
浏览器的 origin 就变 → localStorage / IndexedDB 里的学习进度**换个端口就"消失"**。
本地模式建议把 `_serve.ps1` 改成固定端口 8912。

