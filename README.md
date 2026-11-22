<h1 align=center>
  <img src="https://github.com/user-attachments/assets/9d626e0f-0601-4640-8981-ad66d8ac4853" alt="TypeWords" style="width: 500px;"/>
</h1>

<p align="center">
  <a href="/README.md">English</a> |
  <a href="/docs/README.es.md">Español</a> |
  <a href="/docs/README.de.md">Deutsch</a> |
  <a href="/docs/README.fr.md">Français</a> |
  <a href="/docs/README.pt.md">Português</a> |
  <a href="/docs/README.ru.md">Русский</a> |
  <a href="/docs/README.uk.md">Українська</a> |
  <a href="/docs/README.ja.md">日本語</a> |
  <a href="/docs/README.ko.md">한국인</a> |
  <a href="/docs/README.th.md">ไทย</a> |
  <a href="/docs/README.vi.md">Tiếng Việt</a> |
  <a href="/docs/README.id.md">Bahasa Indonesia</a> |
  <a href="/docs/README.zh-TW.md">繁體中文</a> |
  <a href="/docs/README.zh-CN.md">简体中文</a> 
</p>

<p align="center">
  <b>Learn English, one keystroke at a time; smarter memorization, more efficient learning - an open-source word and article practice tool</b>
</p>

> **This repository is a fork of [zyronon/TypeWords](https://github.com/zyronon/TypeWords)**
> (GPL-3.0) with local enhancements: an offline word-lookup dictionary, a 13-book
> Laiwu textbook article set, a level-placement test, a phonetics page, and a
> local CSV/Excel word-list importer. Upstream credit goes to zyronon.

## Project Introduction

<https://www.bilibili.com/video/BV1QwYv6eEAS>

## Online Access

<https://typewords.cc>

<img width="1920" height="1440" alt="practice words" src="/public/imgs/words.png" />
<img width="1920" height="1440" alt="practice articles" src="/public/imgs/articles.png" />

## Features

### Word Practice

- Practice modes: Follow-along / Dictation / Self-test / Spelling from memory
- Smart mode: Automatically calculates learning words based on memory curves, deepening memory through dictation
- Free mode: No restrictions, plan your own learning
- Provides phonetics, pronunciation (American/British), example sentences, phrases, synonyms, root words, etymology, error statistics, and more

### Article Memorization

- Built-in classic textbooks; you can also add or import articles with one-click translation and bilingual comparison
- Follow-along + dictation dual modes, sentence-by-sentence input with automatic pronunciation for more efficient memorization
- Supports listening while writing from memory to reinforce learning

### Favorites, Wrong Words, Mastered

- Words typed incorrectly while learning are automatically added to your wrong word book for later review
- Actively add words to mastered to automatically skip them in future sessions
- Add words to favorites for consolidation and review

### Highly Customizable

- Rich keyboard sound effects
- Customizable shortcuts
- Highly configurable settings

### Clean and Efficient

- Clean design, modern UI, ad-free
- Refreshing interface, simple operation
- No forced subscription to any platform

### Vocabulary Library

Built-in commonly used vocabulary including CET-4, CET-6, GMAT, GRE, IELTS, SAT, TOEFL, Graduate English, TEM-4, TEM-8, and more (official website only).
Designed to meet most users' vocabulary learning needs. Community contributions of additional vocabulary are welcome.

## Vocabulary Data (Important)

**The vocabulary libraries are not stored in Git** — `public/dicts/**` is git-ignored
on purpose (hundreds of megabytes of licensed teaching material; see `.gitignore`).
A fresh clone therefore ships the app **without** word books.

What *is* tracked, and what you get out of the box:

| Path | Tracked? | What it is |
|------|----------|------------|
| `public/dicts/en/article/NCE_1.json` | yes | New Concept English article text (extracted from the textbook PDFs) |
| `public/dicts/en/article/LWXX_*.json`, `LWCZ_*.json` | yes | Laiwu (Shandong) 5-4 textbook articles, 13 books |
| `public/dicts/en/word/CET4_T.json` | yes | CET-4 word list (the only bundled word book) |
| `public/dicts/en/word/*.json` (everything else) | **no** | ~210 other word books — fetch them separately |
| `public/list/word.json` | yes | The catalogue that maps each book id to its file and metadata |
| `data/word-index.json` | **no** | Offline lookup index — rebuild with `node scripts/build-word-index.mjs` |

To get the full word set, download the books from the upstream CDN
(`https://files.typewords.cc/dicts/en/word/<url>`, where `<url>` is the `url` field
of each entry in `public/list/word.json`) and drop them into
`public/dicts/en/word/`. `_tools/import_online_dicts.py` does exactly this for the
books listed in its `SPEC` table (download → clean → merge the catalogue by entry).

Also note: the upstream `dev` branch ships its media assets from a CDN, while this
branch keeps them local under `public/sound/`, `public/video/` and `public/imgs/`
so the app runs fully offline.

## Running the Project

#### Note: This project can run standalone with data saved locally. Manual backup is required when switching devices; this does not affect normal usage.

This project is built with `Nuxt` and requires a Node.js environment.

1. Install NodeJS, refer to the [official documentation](https://nodejs.org/en/download)
2. The project is large. It's recommended to use `git clone --depth 1 https://github.com/CEHNICA/TypeWords.git` to clone only the latest commit. GitHub's Download ZIP feature will not work properly.
3. In the project root directory, open a terminal and run `pnpm install` to download dependencies.
4. Run `pnpm run dev` to start the project. The default address is [`http://localhost:5567`](http://localhost:5567)
5. Open [`http://localhost:5567`](http://localhost:5567) in your browser to access the project.
6. Run `pnpm run generate` to build the project files.

### Local-only paths (textbook PDFs, backups)

Some tools under `_tools/` and `scripts/` need resources that are **not** in this
repository: the Laiwu textbook PDFs and the dictionary backup folders. They are
resolved in three steps (`scripts/local_paths.py`):

1. Environment variable — `TW_TEXTBOOK_PDF_DIR`, `TW_DICT_BACKUP`
2. `data/local_paths.json` (git-ignored, machine-local), e.g.

   ```json
   {
     "textbookPdfDir": "D:\\教材\\莱芜英语课本\\压缩版",
     "dictBackup": "D:\\备份\\_dict_backup_20261122"
   }
   ```
3. Repository-relative fallback — `<repo>/课本PDF`

The checks that need the PDFs (`check_book_wordsheet.py`, `check_textbook_trans.py`)
report a clear error instead of crashing when the PDFs are missing.

### Health checks

`_tools/_run_all_checks.ps1` runs the whole suite (data checks + browser checks).
It prints `失败项合计: N` at the end — that number must be `0`.

## Features and Suggestions

The project is currently in early development, with new features being added continuously. If you have any suggestions or feature requests, feel free to open an `Issue`.
If you like the design philosophy of this software, please submit a `PR`. Thank you for your support!

## Contributing Guide

[Contributing Guidelines](/docs/CONTRIBUTING.md)

If you're interested in this project, we welcome your contributions and will provide as much help as possible.

Before contributing, please communicate with the developers to avoid code conflicts.

Thank you again for your contributions!


## ❤️ Support TypeWords
If TypeWords has been helpful to you, feel free to sponsor the project to support server operation and future development.  
Of course, sponsorship is not required for use—sharing the project, submitting feedback, or contributing code are also highly valuable forms of support.

<img width="300" height="390" alt="practice words" src="/public/imgs/zhifubao.png" />
<img width="300" height="390" alt="practice words" src="/public/imgs/weixin.png" />

