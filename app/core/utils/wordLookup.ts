import { queryWord } from '../apis/words.ts'
import { CLOUD_WORD_QUERY_ENABLED } from '../config/env.ts'
import type { Word } from '../types/types.ts'

const lookupCache = new Map<string, Word | null>()

export interface WordLookupResolution {
  query: string
  candidates: string[]
  data: Word | null
}

export function stripWordPunctuation(word: string): string {
  return word.replace(/^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$/g, '')
}

export function normalizeWordForLookup(raw: string): string[] {
  const query = raw.trim()
  return query ? [query] : []
}

/**
 * 查本地词库（服务端离线索引，零网络、毫秒级）。
 *
 * 返回三态，不能简单当 null 处理：
 *   - `hit`        → 命中，data 有值
 *   - `miss`       → **词典服务正常，但这个词没收录** → 别再打云端（本地云端必然失败，
 *                    打过去要等 4 秒连接被拒，用户看到的���「查询中...」卡几秒）
 *   - `unavailable` → 服务端索引没构建 / 网络错误 → 这种才值得走云端兜底
 */
type LocalLookup =
  | { status: 'hit'; data: Word }
  | { status: 'miss'; data: null }
  | { status: 'unavailable'; data: null }

async function queryLocalWord(word: string): Promise<LocalLookup> {
  try {
    const res = await $fetch<{ success: boolean; data: Word }>('/api/word-query', {
      query: { word },
    })
    if (res?.data) return { status: 'hit', data: res.data }
    return { status: 'miss', data: null }
  } catch (e: any) {
    // 404 = 词典在、词没有 → 确定性 miss
    const status = e?.statusCode ?? e?.response?.status ?? e?.status
    if (status === 404) return { status: 'miss', data: null }
    // 503 / 网络错误 / 其他 → 服务不可用，才考虑云端
    return { status: 'unavailable', data: null }
  }
}

/**
 * 平台无关的查词入口：严格按用户点击的原词查询一次，不做大小写或词形转换。
 *
 * 顺序：**先本地离线词库**（本地 dev server 索引 207 份词库，0 延迟），
 *       本地明确没收录 → 直接返回（不外网）；
 *       本地服务不可用 → 才走云端 Supabase。
 * 之前是直接打云端 → 本地没配 apiBase 必然失败 → 弹有道整页 iframe，慢得要死。
 */
export async function resolveWordLookup(rawWord: string): Promise<WordLookupResolution> {
  const query = rawWord.trim()
  const candidates = normalizeWordForLookup(rawWord)
  if (!query) return { query: '', candidates, data: null }

  if (lookupCache.has(query)) {
    return { query, candidates, data: lookupCache.get(query) ?? null }
  }

  const local = await queryLocalWord(query)
  let data: Word | null = null

  if (local.status === 'hit') {
    data = local.data
  } else if (local.status === 'unavailable' && CLOUD_WORD_QUERY_ENABLED) {
    const res = await queryWord({ word: query })
    data = res.success && res.data ? res.data : null
  }

  lookupCache.set(query, data)
  return { query, candidates, data }
}

export function splitEnglishText(text: string): { text: string; isWord: boolean }[] {
  if (!text) return []
  const tokens: { text: string; isWord: boolean }[] = []
  const regex = /[a-zA-Z]+(?:'[a-zA-Z]+)?|[^a-zA-Z]+/g
  let match: RegExpExecArray | null
  while ((match = regex.exec(text)) !== null) {
    const token = match[0]
    tokens.push({ text: token, isWord: /[a-zA-Z]/.test(token) })
  }
  return tokens
}

function escapeRegExp(string: string): string {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

export function getWordRegexes(word: string): RegExp[] {
  const normalized = word.trim().toLowerCase()
  if (!normalized) return []
  const escaped = escapeRegExp(normalized)
  const patterns = [
    `\\b${escaped}\\b`,
    `\\b${escaped}s\\b`,
    `\\b${escaped}es\\b`,
    `\\b${escaped}ed\\b`,
    `\\b${escaped}ing\\b`,
  ]
  return Array.from(new Set(patterns)).map(pattern => new RegExp(pattern, 'gi'))
}

/** 判断单个 token 是否为目标单词（含常见变形），逻辑与 SentenceHightLightWord 一致 */
export function isHighlightToken(token: string, highlightWord: string): boolean {
  if (!highlightWord.trim()) return false
  const regexes = getWordRegexes(highlightWord)
  return regexes.some(regex => {
    regex.lastIndex = 0
    return regex.test(token)
  })
}

/** 生成与 SentenceHightLightWord 相同的高亮 HTML */
export function buildHighlightedHtml(
  text: string,
  highlightWord: string,
  options: { highLight?: boolean; dictation?: boolean } = {}
): string {
  if (!text || !highlightWord) return text

  const classNames = [
    options.highLight !== false ? 'highlight-word' : '',
    options.dictation ? 'word-shadow' : '',
  ]
    .filter(Boolean)
    .join(' ')
  const wrap = (match: string) => `<span class="${classNames}">${match}</span>`

  return getWordRegexes(highlightWord).reduce((result, regex) => result.replace(regex, wrap), text)
}
