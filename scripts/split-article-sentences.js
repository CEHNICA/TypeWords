/**
 * 把莱芜课本课文的「句」切成真正的英文句子粒度
 * ==================================================
 *
 * 干什么用的：
 *   跟打页里「一行 = 一句 = 一次朗读单元」
 *   （`genArticleSectionData` 按 `\n` 切句；`playSentenceAudio` 拿整行文本去发音）。
 *   原来的课文是「一个自然段 = 一行」灌进去的，初中课文一行能塞 15 个英文句子 →
 *   点一次播放就"从头到尾发完了"，跟打也一屏一坨。
 *
 *   这个脚本按「句末标点 + 空白 + 下一句开头(大写/引号)」把每一行再切细，
 *   段落结构（`\n\n`）保持不变。
 *
 * 怎么跑：
 *   node scripts/split-article-sentences.js           # 改
 *   node scripts/split-article-sentences.js --dry-run # 只统计
 *   node scripts/split-article-sentences.js --only LWXX_3_1
 *
 * 切完必须跑： python _tools/check_article_sentences.py
 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const ARTICLE_DIR = path.join(ROOT, 'public', 'dicts', 'en', 'article')

const BOOKS = [
  'LWXX_3_1', 'LWXX_3_2', 'LWXX_4_1', 'LWXX_4_2', 'LWXX_5_1', 'LWXX_5_2',
  'LWCZ_6_1', 'LWCZ_6_2', 'LWCZ_7_1', 'LWCZ_7_2', 'LWCZ_8_1', 'LWCZ_8_2', 'LWCZ_9_1',
]

// 这些缩写后面的点不能当句末标点
//
// 分两类，因为大小写是语义的一部分：
//   ABBR_ANY —— 不管大小写都算缩写（e.g. / i.e. / etc. / vs.）
//   ABBR_CAP —— **必须原文首字母大写**才算缩写。
//   为什么：'no' 两种用法都有 ——
//     'No. 5 is here.'        → 'No.' 是编号缩写，不能切
//     'They said no. Then…'   → 'no.' 是句末，必须切
//   以前不分大小写，导致 'said no.' 整句不切，朗读就是一口气读完。
const ABBR_ANY = new Set([
  'e.g', 'i.e', 'u.s', 'u.k', 'u.s.a', 'etc', 'vs',
])
const ABBR_CAP = new Set([
  'mr', 'mrs', 'ms', 'dr', 'prof', 'st', 'jr', 'sr', 'no', 'fig',
  'inc', 'ltd', 'co', 'dept', 'est',
])

// 句末标点 + 可能的收尾引号/括号
const RE_END = /[.!?]+["'’”)\]]*(?=\s)/g

/** 判断 line 在 index 处的点是不是缩写 */
function isAbbrev(line, dotIndex) {
  // 取点前最近的词（含点）
  let i = dotIndex
  while (i >= 0 && /[A-Za-z.]/.test(line[i])) i--
  const raw = line.slice(i + 1, dotIndex + 1)
  const word = raw.replace(/\.$/, '')
  if (!word) return false
  const low = word.toLowerCase()
  if (ABBR_ANY.has(low)) return true
  if (ABBR_CAP.has(low)) return /^[A-Z]/.test(word)
  return false
}

/** 把一行切成若干句 */
function splitLine(line) {
  const trimmed = line.trim()
  if (!trimmed) return []
  const out = []
  let start = 0
  RE_END.lastIndex = 0
  let m
  while ((m = RE_END.exec(trimmed)) !== null) {
    const punctEnd = m.index + m[0].length - 1   // 句末标点（含引号）结束位置
    const dotIndex = m.index                    // 标点起点
    // 缩写保护
    if (trimmed[dotIndex] === '.' && isAbbrev(trimmed, dotIndex)) continue
    // 后面必须是空白 + 下一个实词以大写字母/引号开头
    const rest = trimmed.slice(punctEnd + 1)
    if (!rest.trim()) break                      // 句尾
    const nextWord = rest.trimStart()
    if (!/^[A-Z"'“‘(]/.test(nextWord)) continue
    const piece = trimmed.slice(start, punctEnd + 1).trim()
    if (piece) out.push(piece)
    start = punctEnd + 1
  }
  const tail = trimmed.slice(start).trim()
  if (tail) out.push(tail)
  return out.length ? out : [trimmed]
}

function splitText(text) {
  const paras = text.split('\n\n')
  const newParas = []
  for (const para of paras) {
    const lines = para.split('\n')
    const newLines = []
    for (const line of lines) {
      if (!line.trim()) { newLines.push(line); continue }
      newLines.push(...splitLine(line))
    }
    newParas.push(newLines.join('\n'))
  }
  return newParas.join('\n\n')
}

function countSentences(text) {
  let n = 0
  for (const para of text.split('\n\n')) {
    for (const s of para.split('\n')) if (s.trim()) n++
  }
  return n
}

function main() {
  const args = process.argv.slice(2)
  const dry = args.includes('--dry-run')
  const onlyIdx = args.indexOf('--only')
  const only = onlyIdx >= 0 ? args[onlyIdx + 1] : null
  const books = only ? [only] : BOOKS

  let before = 0
  let after = 0
  for (const book of books) {
    const file = path.join(ARTICLE_DIR, book + '.json')
    if (!fs.existsSync(file)) {
      console.error(`[SKIP] ${book}.json 不存在`)
      continue
    }
    const raw = fs.readFileSync(file, 'utf8')
    const data = JSON.parse(raw)
    const arts = Array.isArray(data) ? data : [data]
    let b = 0
    let a = 0
    let changed = 0
    for (const art of arts) {
      const oldText = art.text || ''
      const newText = splitText(oldText)
      const sb = countSentences(oldText)
      const sa = countSentences(newText)
      b += sb
      a += sa
      if (newText !== oldText) {
        changed++
        art.text = newText
        // 译文必须与句一一对应；旧译文是空的/对不上时清空，等翻译脚本回填
        art.textTranslate = ''
      }
    }
    before += b
    after += a
    console.log(`${book}: 句 ${b} -> ${a}（+${a - b}），改动 ${changed}/${arts.length} 篇`)
    if (!dry) {
      const text = JSON.stringify(arts, null, 2) + '\n'
      fs.writeFileSync(file, text, 'utf8')
    }
  }
  console.log(`\n合计句数 ${before} -> ${after}（+${after - before}）`)
  if (dry) console.log('(--dry-run 未写文件)')
}

main()
