/**
 * 整本复习进度存储
 * ====================
 * 「整本复习」要把选中几本书的**全部**单词过一遍，九年义务教育全套有 3,000+ 词，
 * 不可能一口气做完 —— 所以每答一题就落一次盘，中途关掉浏览器下次接着做。
 *
 * 三态结果定义：
 *   1 = 清楚（认识，不需要导出）
 *   0 = 不会（答错 / 不认识，进入待查缺补漏导出清单）
 *   2 = 不太清楚（模糊 / 蒙对，同样进入待查缺补漏导出清单）
 *
 * 为什么用 localStorage 而不是 IndexedDB：
 *   实测这台机器上 idb-keyval 的 keyval-store 库会被反复删除重建
 *   （db 名退化成 keyval-store@1@1，object store 直接不存在），
 *   写进去的进度读不出来。localStorage 同步、稳当，几十 KB 数据完全放得下。
 *
 * 分桶规则：key = 教材 + 册子组合
 *   tw-book-review:<ladderKey>:<books 逗号分隔>
 * 换一套书就是另一个桶，进度不会串味。
 */

/** 复习单题判定结果：0=不会，1=清楚，2=不太清楚（模糊/蒙对） */
export type ReviewResultCode = 0 | 1 | 2

/** 顺手在对照表里标出的干扰项生词 */
export interface ExtraUnclearItem {
  word: string
  phonetic: string
  cn: string
  bookLabel: string
}

export interface BookReviewProgress {
  /** 教材 key */
  ladderKey: string
  /** 选中的册子 index（对应 placement.ts 里的 steps 下标） */
  books: number[]
  /** 小写单词 → 0 不会 / 1 清楚 / 2 不太清楚 */
  results: Record<string, ReviewResultCode>
  /** 可选：答错时误选的英文词，方便导出复盘易混词 */
  wrongChosen?: Record<string, string>
  /** 可选：做题时从干扰项对照表顺手标出的不太清楚单词 */
  extraUnclear?: ExtraUnclearItem[]
  /** 最后一次更新 */
  updatedAt: number
}

/** 「最近一次复习」指针：刷新页面后默认册子组合会变，靠它找回上次那套 */
export interface BookReviewSession {
  ladderKey: string
  books: number[]
  /** 上次做到第几个词 */
  done: number
  updatedAt: number
}

const PREFIX = 'tw-book-review'
const LAST_KEY = 'tw-book-review:last'

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    if (!raw) return null
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // 存不进去也不能把测试卡死，忽略
  }
}

/** 进度桶的 key：教材 + 册子组合 */
export function progressKey(ladderKey: string, books: number[]): string {
  return `${PREFIX}:${ladderKey}:${books.slice().sort((a, b) => a - b).join(',')}`
}

/** 读回某个组合的进度（没有就返回 null） */
export function loadBookProgress(
  ladderKey: string,
  books: number[]
): BookReviewProgress | null {
  const raw = readJson<BookReviewProgress>(progressKey(ladderKey, books))
  if (!raw || !raw.results) return null
  return raw
}

/** 写进度 */
export function saveBookProgress(p: BookReviewProgress): void {
  writeJson(progressKey(p.ladderKey, p.books), p)
}

/** 清掉某个组合的进度（重新开始） */
export function clearBookProgress(ladderKey: string, books: number[]): void {
  try {
    localStorage.removeItem(progressKey(ladderKey, books))
  } catch {
    // 同上
  }
}

/** 记下「最近一次复习的是哪套书、做到哪」 */
export function saveLastSession(s: BookReviewSession): void {
  writeJson(LAST_KEY, s)
}

/** 读回最近一次复习记录 */
export function loadLastSession(): BookReviewSession | null {
  const raw = readJson<BookReviewSession>(LAST_KEY)
  if (!raw || !Array.isArray(raw.books)) return null
  return raw
}
