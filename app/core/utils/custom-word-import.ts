/**
 * 本地词表导入：解析层（纯函数，不碰 DOM / 不碰 store）
 * ==================================================
 * 为什么要单独拆一层：
 *   1. 解析逻辑是最容易出错的地方（引号、换行、BOM、GBK、表头识别），
 *      混在 Vue 组件里就没法单独测；
 *   2. 浏览器实测尺子（Playwright）只测「端到端能不能用」，
 *      边界用例（坏行、重复词、缺表头）靠肉眼看不见。
 *
 * 支持的输入：
 *   - .xlsx / .xls：走上游自己的 xlsx 库（LIB_JS_URL.XLSX），
 *     跟「导出 xlsx」用的是同一个库 → 导出→改→导入 闭环。
 *   - .csv / .txt：逗号 / 制表符 / 分号分隔，带引号的字段里可以有逗号和换行。
 *
 * 表头别名（大小写不敏感、空格忽略）：
 *   单词 / word / 英文 / 词汇 / term          → word
 *   音标 / 音标① / phonetic / phonetics      → phonetic0
 *   音标② / phonetic2                        → phonetic1
 *   翻译 / 中文 / 释义 / 意思 / translation / meaning → trans
 *   笔记 / note / remark                     → note
 */

/** 词表里的列 → 词条字段 */
export type WordField = 'word' | 'phonetic0' | 'phonetic1' | 'trans' | 'note'

/** 每列在第几列（-1 = 没有这一列） */
export type ColumnMap = Record<WordField, number>

export const EMPTY_COLUMN_MAP: ColumnMap = {
  word: -1,
  phonetic0: -1,
  phonetic1: -1,
  trans: -1,
  note: -1,
}

/**
 * 表头别名表。
 * 键是小写化的表头文本，值是字段名。
 *
 * 两个坑：
 *   1. 含 ①/② 的中文 key 必须加引号 —— ① 属 So 类，不是合法 JS 标识符字符，
 *      写成 `音标①: '...'` 直接是 SyntaxError（tsc: TS1127 Invalid character）。
 *   2. 匹配是**精确查表**（normalizeHeader 后全等），不是前缀匹配，
 *      所以「音标」不会抢走「音标①」。
 */
export const HEADER_ALIASES: Record<string, WordField> = {
  // 单词
  单词: 'word',
  英文: 'word',
  词汇: 'word',
  词: 'word',
  word: 'word',
  english: 'word',
  term: 'word',
  vocabulary: 'word',
  // 音标①
  '音标①': 'phonetic0',
  '音标1': 'phonetic0',
  音标: 'phonetic0',
  phonetic: 'phonetic0',
  phonetics: 'phonetic0',
  pronunciation: 'phonetic0',
  // 音标②
  '音标②': 'phonetic1',
  '音标2': 'phonetic1',
  phonetic2: 'phonetic1',
  // 翻译
  翻译: 'trans',
  中文: 'trans',
  释义: 'trans',
  意思: 'trans',
  译文: 'trans',
  '翻译①': 'trans',
  translation: 'trans',
  meaning: 'trans',
  chinese: 'trans',
  definition: 'trans',
  // 笔记
  笔记: 'note',
  note: 'note',
  notes: 'note',
  remark: 'note',
  remarks: 'note',
}

/** 表头文本归一化：去 BOM、去首尾空白、去掉所有空格、小写 */
export function normalizeHeader(text: string): string {
  return String(text ?? '')
    .replace(/^\uFEFF/, '')
    .replace(/[\s\u3000]+/g, '')
    .toLowerCase()
}

/** 表头单元格 → 字段名；认不出来返回 null */
export function matchField(header: string): WordField | null {
  const key = normalizeHeader(header)
  if (!key) return null
  return HEADER_ALIASES[key] ?? null
}

/**
 * 探测分隔符：在候选里挑「引号外出现次数最多」的。
 * 优先逗号，其次制表符，再次分号。
 *
 * 注意：不能只看第一行。
 * 第一行可能是带引号的多行字段（`"line1\nline2",z`），它内部没有分隔符 →
 * 只看第一行会误判成「单列」，整篇解析塌成一行。
 * 所以这里扫全文，但跳过引号内的字符（引号里的逗号不是分隔符）。
 */
export function guessDelimiter(text: string): string {
  const src = String(text ?? '')
  const candidates = [',', '\t', ';']
  const counts: Record<string, number> = { ',': 0, '\t': 0, ';': 0 }
  let inQuote = false
  for (let i = 0; i < src.length; i++) {
    const ch = src[i]
    if (ch === '"') {
      if (inQuote && src[i + 1] === '"') {
        i++ // "" 转义，跳过
        continue
      }
      inQuote = !inQuote
      continue
    }
    if (inQuote) continue
    if (ch in counts) counts[ch]++
  }
  let best = ','
  let bestCount = counts[',']
  for (const d of ['\t', ';']) {
    if (counts[d] > bestCount) {
      bestCount = counts[d]
      best = d
    }
  }
  // 全文里一个分隔符都没有 → 整份文件当单列
  return bestCount > 0 ? best : ''
}

/**
 * 解析分隔符文本 → 二维数组。
 * 支持：带引号字段（"" 转义）、字段内换行、CRLF/LF、BOM。
 * 空行直接丢掉（不产生空数组元素）。
 */
export function parseDelimited(text: string, delimiter?: string): string[][] {
  let src = String(text ?? '')
  if (src.charCodeAt(0) === 0xfeff) src = src.slice(1)

  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuote = false
  let i = 0

  // 没给分隔符就自动探测；探测结果是空串 → 整份当单列
  const d = delimiter === undefined ? guessDelimiter(src) : delimiter

  const pushField = () => {
    row.push(field)
    field = ''
  }
  const pushRow = () => {
    pushField()
    // 整行都是空 → 当空行丢掉
    if (row.length > 1 || row[0].trim() !== '') rows.push(row)
    row = []
  }

  while (i < src.length) {
    const ch = src[i]
    if (inQuote) {
      if (ch === '"') {
        if (src[i + 1] === '"') {
          field += '"'
          i += 2
          continue
        }
        inQuote = false
        i++
        continue
      }
      field += ch
      i++
      continue
    }
    if (ch === '"' && field.trim() === '') {
      // 字段开头的引号 → 进引用模式
      field = ''
      inQuote = true
      i++
      continue
    }
    if (d && ch === d) {
      pushField()
      i++
      continue
    }
    if (ch === '\r') {
      // \r\n 或单独的 \r 都算换行
      if (src[i + 1] === '\n') i++
      pushRow()
      i++
      continue
    }
    if (ch === '\n') {
      pushRow()
      i++
      continue
    }
    field += ch
    i++
  }
  // 文件末尾没有换行 → 收尾
  if (field !== '' || row.length) pushRow()

  return rows
}

/**
 * 判断有没有表头，并给出列映射。
 * 有表头：第一行至少有一个单元格能认出来。
 * 没表头：默认第 0 列是单词、第 1 列是翻译（列数够才认）。
 */
export function detectColumns(rows: string[][]): { map: ColumnMap; hasHeader: boolean } {
  const map: ColumnMap = { ...EMPTY_COLUMN_MAP }
  if (!rows.length) return { map, hasHeader: false }

  const header = rows[0]
  const hits = header.map(h => matchField(h))
  const hitCount = hits.filter(Boolean).length

  if (hitCount > 0) {
    hits.forEach((f, idx) => {
      if (!f) return
      // 同一个字段被多列命中 → 取第一列
      if (map[f] === -1) map[f] = idx
    })
    // 表头里出现「单词」列但被映射到了别的字段（不太可能），兜底：保证 word 列存在
    if (map.word === -1) {
      const idx = header.findIndex(h => normalizeHeader(h).includes('单词') || normalizeHeader(h) === 'word')
      if (idx > -1) map.word = idx
    }
    return { map, hasHeader: true }
  }

  // 无表头
  map.word = 0
  if (header.length > 1) map.trans = 1
  return { map, hasHeader: false }
}

export interface ImportRowError {
  /** 数据行号（从 1 开始，不含表头行） */
  row: number
  reason: string
  raw: string
}

export interface BuildWordsResult {
  words: Array<{
    word: string
    phonetic0: string
    phonetic1: string
    trans: string
    note: string
  }>
  errors: ImportRowError[]
  /** 重复单词（同一份文件里出现多次） */
  duplicates: number
}

/** 单词合法性：至少含一个英文字母，且长度 <= 64 */
export function isValidWord(word: string): boolean {
  const w = String(word ?? '').trim()
  if (!w || w.length > 64) return false
  return /[A-Za-z]/.test(w)
}

/**
 * 数据行 → 词条列表。
 * - 空单词行直接跳过（不报错）
 * - 不含字母的 → 记为坏行
 * - 同一文件内重复单词 → 记为重复并跳过（后面的不覆盖前面的）
 */
export function buildWords(rows: string[][], map: ColumnMap, hasHeader: boolean): BuildWordsResult {
  const dataRows = hasHeader ? rows.slice(1) : rows
  const words: BuildWordsResult['words'] = []
  const errors: ImportRowError[] = []
  const seen = new Set<string>()
  let duplicates = 0

  dataRows.forEach((row, idx) => {
    const rowNo = idx + 1
    const pick = (f: WordField): string => {
      const col = map[f]
      if (col === -1) return ''
      return String(row[col] ?? '').trim()
    }
    const rawWord = pick('word')
    if (!rawWord) return // 空行，静默跳过

    if (!isValidWord(rawWord)) {
      errors.push({ row: rowNo, reason: '不是有效单词（不含字母或过长）', raw: rawWord })
      return
    }
    const key = rawWord.toLowerCase()
    if (seen.has(key)) {
      duplicates++
      errors.push({ row: rowNo, reason: '重复单词，已跳过', raw: rawWord })
      return
    }
    seen.add(key)
    words.push({
      word: rawWord,
      phonetic0: pick('phonetic0'),
      phonetic1: pick('phonetic1'),
      trans: pick('trans'),
      note: pick('note'),
    })
  })

  return { words, errors, duplicates }
}

/**
 * 尝试用多种编码解码一个 ArrayBuffer（UTF-8 优先，失败再 GBK）。
 * 返回解码文本 + 实际用的编码名。
 */
export function decodeBuffer(buffer: ArrayBuffer): { text: string; encoding: string } {
  const bytes = new Uint8Array(buffer)
  const utf8 = new TextDecoder('utf-8', { fatal: false }).decode(bytes)
  // 有替换字符 → 很可能不是 UTF-8，再用 GBK 试一次
  if (utf8.includes('\uFFFD')) {
    try {
      const gbk = new TextDecoder('gbk', { fatal: false }).decode(bytes)
      if (!gbk.includes('\uFFFD')) return { text: gbk, encoding: 'GBK' }
    } catch {
      /* 浏览器不支持 gbk 解码器 → 忽略 */
    }
  }
  return { text: utf8, encoding: 'UTF-8' }
}
