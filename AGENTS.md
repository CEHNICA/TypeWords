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
| `app/pages/(words)/book-review.vue` | 新增：`/book-review` 整本复习页（**册子多选 + 全词逐个过 + 中断续做 + 每册掌握率报告 + 生词进错词本**） |
| `app/core/utils/placement-progress.ts` | 新增：整本复习进度持久化（**localStorage**，按「教材+册子组合」分桶 + `tw-book-review:last` 指针） |
| `_tools/check_book_review.py` | 新增：整本复习链路体检器 25 项 |

## 体检器（改测试链路必跑）

```powershell
cd C:\Users\17321\Documents\破甲\typewords-src
python _tools\check_test_flow.py --http     # 17 项，全绿 exit 0
python _tools\check_placement.py --http    # 32 项，全绿 exit 0
python _tools\check_book_review.py --http  # 25 项，全绿 exit 0
```

## 硬规矩（补）

7. **灰按钮必须说清为什么灰**：任何 `:disabled` 的 BaseButton 都要同时给 `:disabled-reason`，
   否则用户只看到「点了没反应」。
8. **改 `nuxt.config.ts` 后必须重启 dev server**，热更新不生效。


## 已知缺口（master 分支本来就没有，别以为是改坏的）

- `/import`、`/nce`、`/fsrs`、`/practice-sentences`、`/login` 等页面不存在 → 404。
  `app/pages/(words)/dict.vue` 里的 `goImportPage()` 会跳 `/import`，那是**云端功能**，本地纯离线模式用不到。
- 自定义词典/个人词库依赖 Supabase（`runtimeConfig.public.apiBase`），本地没填就不可用。
- 线上站比 master 新，`dev` 分支页面多但资源走 CDN，不能直接混用。
