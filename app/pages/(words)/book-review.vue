<script setup lang="ts">
/**
 * 整本复习（Book Review）—— 查缺补漏
 * =====================================
 * 把九年义务教育（或自选多册）的单词去重过一遍：
 *  - 认识的词快速跳过
 *  - 不会或不太清楚（包括蒙对）的词精准筛出并导出
 *  - 不修改全站「已掌握」词库
 */
import { onMounted, onUnmounted, toRaw } from 'vue'
import { BaseButton, BaseInput, BasePage, Checkbox, Toast, VolumeIcon } from '@/base'
import { useBaseStore } from '@/core/stores/base.ts'
import { _getDictDataByUrl, cloneDeep, resourceWrap, shuffle, useNav } from '@/core/utils'
import { DICT_LIST } from '@/core/config/env.ts'
import { buildQuestion } from '@/core/utils/word-test'
import { PLACEMENT_LADDERS } from '@/core/data/placement'
import { getDefaultDict } from '@/core/types/func'
import { DictType, ShortcutKey } from '@/core/types/enum'
import {
  clearBookProgress,
  loadBookProgress,
  loadLastSession,
  saveBookProgress,
  saveLastSession,
  type BookReviewProgress,
  type BookReviewSession,
  type ReviewResultCode,
} from '@/core/utils/placement-progress'
import type { Question, Word } from '@/core/types/types.ts'
import { cancelWordPracticeAudio, usePlayBeep, usePlayCorrect, usePlayWordAudio } from '@/core/hooks/sound.ts'
import { useEvents } from '@/core/utils/eventBus'
import { useStartKeyboardEventListener } from '@/core/hooks/event.ts'
import { useSettingStore } from '@/core/stores/setting.ts'

interface BookInfo {
  index: number
  label: string
  words: Word[]
}

interface PoolItem {
  word: Word
  bookIndex: number
  bookLabel: string
}

interface UnclearRow {
  key: string
  word: Word
  bookLabel: string
  status: 'unknown' | 'fuzzy'
  chosenWrong?: string
}

const base = useBaseStore()
const settingStore = useSettingStore()
const playBeep = usePlayBeep()
const playCorrect = usePlayCorrect()
const playWordAudio = usePlayWordAudio()
const { nav } = useNav()

let phase = $ref<'setup' | 'loading' | 'quiz' | 'report'>('setup')
let ladderKey = $ref('lw')
let selectedBooks = $ref<number[]>([])
let books = $ref<BookInfo[]>([])
let pool = $ref<PoolItem[]>([])
/** 小写单词 → 0 不会 / 1 清楚 / 2 不太清楚 */
let results = $ref<Record<string, ReviewResultCode>>({})
let wrongChosen = $ref<Record<string, string>>({})
let cursor = $ref(0)
let question = $ref<Question | null>(null)
let submitted = $ref(false)
let selectedIndex = $ref(-1)
let savedHint = $ref('')
let savedCount = $ref(0)
let lastSession = $ref<BookReviewSession | null>(null)
let loadingText = $ref('正在准备词表…')
let shuffleOrder = $ref(false)

let wrongPage = $ref(0)
let showAllWrong = $ref(false)
let reportFilter = $ref<'all' | 'unknown' | 'fuzzy'>('all')
let reportSearch = $ref('')
let showDetail = $ref(false)
let mode = $ref<'full' | 'wrong'>('full')
let retryResults = $ref<Record<string, ReviewResultCode>>({})

const WRONG_PAGE_SIZE = 50
const optionLabels = ['A', 'B', 'C', 'D']

const ladder = () => PLACEMENT_LADDERS.find(v => v.key === ladderKey) ?? PLACEMENT_LADDERS[0]
const steps = () => ladder().steps
const keyOf = (w: Word) => (w?.word || '').trim().toLowerCase()
const curResults = () => (mode === 'wrong' ? retryResults : results)
const hasResult = (w: Word) => Object.prototype.hasOwnProperty.call(curResults(), keyOf(w))

function currentItemCode(): ReviewResultCode | undefined {
  const item = pool[cursor]
  if (!item) return undefined
  const k = keyOf(item.word)
  const src = curResults()
  return Object.prototype.hasOwnProperty.call(src, k) ? src[k] : undefined
}

function optionDetail(): { label: string, cn: string, en: string, isCorrect: boolean, isChosen: boolean }[] {
  if (!question) return []
  return question.candidates.map((c, i) => ({
    label: optionLabels[i] || String(i),
    cn: shortTrans(c.word),
    en: c.word.word || '',
    isCorrect: i === question!.correctIndex,
    isChosen: i === selectedIndex,
  }))
}

/** 选项与对照表用的简洁首义 */
function shortTrans(word: Word): string {
  const cn = word?.trans?.[0]?.cn || ''
  const first = cn.split(/[；;]/)[0].trim()
  const cut = first.length > 14 ? first.slice(0, 14) + '…' : first
  return cut || word?.word || ''
}

/** 导出文件用的中文释义：只取第一个意思（不截断） */
function firstTrans(word: Word): string {
  const cn = word?.trans?.[0]?.cn || ''
  return cn.trim() || word?.word || ''
}

function sanitizeWord(w: Word): Word {
  if (!w) return w
  if (!Array.isArray(w.trans)) w.trans = []
  if (!w.relWords || typeof w.relWords !== 'object') w.relWords = { root: '', rels: [] }
  if (!Array.isArray(w.relWords.rels)) w.relWords.rels = []
  if (!Array.isArray(w.synos)) w.synos = []
  if (!Array.isArray(w.phrases)) w.phrases = []
  if (!Array.isArray(w.sentences)) w.sentences = []
  return w
}

// ---------------------------------------------------------------- 册子选择
function toggleBook(index: number) {
  const i = selectedBooks.indexOf(index)
  if (i === -1) selectedBooks = [...selectedBooks, index]
  else selectedBooks = selectedBooks.filter(v => v !== index)
  selectedBooks.sort((a, b) => a - b)
  void refreshCurrentSaved()
}

function toggleAllBooks() {
  selectedBooks = selectedBooks.length === steps().length ? [] : steps().map((_, i) => i)
  void refreshCurrentSaved()
}

function selectStage(stage: 'all' | 'primary' | 'junior') {
  const list = steps()
  if (stage === 'all') {
    selectedBooks = list.map((_, i) => i)
  } else if (stage === 'primary') {
    selectedBooks = list
      .map((s, i) => ({ s, i }))
      .filter(({ s, i }) => (ladderKey === 'lw' ? i < 6 : !s.label.includes('初中') && !/七年级|八年级|九年级/.test(s.label)))
      .map(v => v.i)
  } else {
    selectedBooks = list
      .map((s, i) => ({ s, i }))
      .filter(({ s, i }) => (ladderKey === 'lw' ? i >= 6 : s.label.includes('初中') || /七年级|八年级|九年级/.test(s.label)))
      .map(v => v.i)
  }
  void refreshCurrentSaved()
}

function hasJuniorSteps(): boolean {
  return steps().some((s, i) => (ladderKey === 'lw' ? i >= 6 : s.label.includes('初中') || /七年级|八年级|九年级/.test(s.label)))
}

function hasPrimarySteps(): boolean {
  return steps().some((s, i) => (ladderKey === 'lw' ? i < 6 : !s.label.includes('初中') && !/七年级|八年级|九年级/.test(s.label)))
}

function selectedWordCount(): number {
  const list = dictListCache
  if (!list) return 0
  let sum = 0
  steps().forEach((step, index) => {
    if (!selectedBooks.includes(index)) return
    for (const id of step.ids) {
      const item = list.get(id)
      if (item) sum += Number(item.length) || 0
    }
  })
  return sum
}

function bookSize(index: number): number {
  const list = dictListCache
  const step = steps()[index]
  if (!list || !step) return 0
  let sum = 0
  for (const id of step.ids) {
    const item = list.get(id)
    if (item) sum += Number(item.length) || 0
  }
  return sum
}

async function changeLadder(key: string) {
  ladderKey = key
  const l = PLACEMENT_LADDERS.find(v => v.key === key) ?? PLACEMENT_LADDERS[0]
  selectedBooks = l.steps.map((_, i) => i)
  await refreshSavedState()
}

let dictListCache = $ref<Map<number, { name: string, url: string, length: number }> | null>(null)

// ---------------------------------------------------------------- 载入
async function loadBooks() {
  phase = 'loading'
  loadingText = '正在下载词表…'
  const list = await fetch(resourceWrap(DICT_LIST.WORD.ALL)).then(r => r.json())
  const map = new Map<number, { name: string, url: string, length: number }>()
  for (const item of list) map.set(Number(item.id), item)
  dictListCache = map

  const out: BookInfo[] = []
  const chosen = selectedBooks.length ? selectedBooks : steps().map((_, i) => i)
  for (const index of chosen) {
    const step = steps()[index]
    if (!step) continue
    const words: Word[] = []
    for (const id of step.ids) {
      const resource = map.get(id)
      if (!resource) continue
      loadingText = `正在加载：${resource.name}`
      try {
        const dict = await _getDictDataByUrl(resource)
        for (const w of dict.words || []) {
          words.push(sanitizeWord(w))
        }
      } catch {
        // 这一本拉不到就跳过
      }
    }
    out.push({ index, label: step.label, words })
  }
  books = out
  buildPool()
}

function buildPool() {
  const seen = new Set<string>()
  const items: PoolItem[] = []
  for (const b of books) {
    for (const w of b.words) {
      const k = keyOf(w)
      if (!k || seen.has(k)) continue
      seen.add(k)
      items.push({ word: w, bookIndex: b.index, bookLabel: b.label })
    }
  }
  pool = shuffleOrder ? shuffle(items) : items
}

async function start(fresh = false) {
  mode = 'full'
  await loadBooks()
  phase = 'loading'
  loadingText = '正在准备词表…'
  const chosen = selectedBooks.length ? selectedBooks : steps().map((_, i) => i)
  const saved = fresh ? null : await loadBookProgress(ladderKey, chosen)
  if (fresh) await clearBookProgress(ladderKey, chosen)
  results = saved?.results ? { ...saved.results } : {}
  wrongChosen = saved?.wrongChosen ? { ...saved.wrongChosen } : {}
  cursor = 0
  while (cursor < pool.length && hasResult(pool[cursor].word)) cursor++
  phase = 'quiz'
  nextQuestion()
}

// ---------------------------------------------------------------- 出题 / 答题
function nextQuestion() {
  if (cursor >= pool.length) return finish()
  const item = pool[cursor]
  const target = shortTrans(item.word)
  const sameBook = books.find(b => b.index === item.bookIndex)?.words ?? []
  const poolForDistractors = sameBook.length >= 6 ? sameBook : pool.map(p => p.word)
  const clean = poolForDistractors.filter(w => {
    if (keyOf(w) === keyOf(item.word)) return false
    return shortTrans(w) !== target
  })
  question = buildQuestion(item.word, clean.length >= 3 ? clean : pool.map(p => p.word))
  submitted = false
  selectedIndex = -1
  if (settingStore.wordSound) {
    playWordAudio((item.word.word || '').replace(/\s*['’]\s*/g, "'").trim(), false)
  }
}

function applyWordOutcome(code: ReviewResultCode, wrongOptWord?: string) {
  const item = pool[cursor]
  if (!item) return
  const k = keyOf(item.word)
  if (mode === 'wrong') {
    retryResults = { ...retryResults, [k]: code }
  } else {
    results = { ...results, [k]: code }
    if (code === 1) {
      if (wrongChosen[k]) {
        const nextWrong = { ...wrongChosen }
        delete nextWrong[k]
        wrongChosen = nextWrong
      }
    } else if (wrongOptWord) {
      wrongChosen = { ...wrongChosen, [k]: wrongOptWord }
    }
  }
  persist()
}

function select(i: number) {
  if (submitted || !question) return
  selectedIndex = i
  submitted = true
  const correct = i === question.correctIndex
  const chosenWord = question.candidates[i]?.word?.word || ''
  applyWordOutcome(correct ? 1 : 0, correct ? undefined : chosenWord)
  if (correct) playCorrect()
  else playBeep()
}

/** 认识：直接标为清楚并跳下一题 */
function markClearAndNext() {
  if (phase !== 'quiz' || !question || submitted) return
  applyWordOutcome(1)
  playCorrect()
  cursor++
  if (cursor >= pool.length) return finish()
  nextQuestion()
}

/** 不太清楚：标记为模糊待导出，并展开对照 */
function markFuzzy() {
  if (submitted || !question) return
  selectedIndex = -1
  submitted = true
  applyWordOutcome(2)
  playBeep()
}

/** 不认识：直接记生词并展开对照 */
function skipUnknown() {
  if (submitted || !question) return
  selectedIndex = -1
  submitted = true
  applyWordOutcome(0)
  playBeep()
}

/** 提交后纠偏（防蒙对、防手滑） */
function togglePostSubmitOutcome(nextCode: ReviewResultCode) {
  if (!submitted || !pool[cursor]) return
  applyWordOutcome(nextCode)
  if (nextCode === 1) Toast.success('已改标为「清楚」')
  else Toast.info('已标为「不太清楚」，将收入导出清单')
}

function prevQuestion() {
  if (cursor <= 0 || phase !== 'quiz') return
  cursor--
  nextQuestion()
}

function advance() {
  if (!submitted || phase !== 'quiz') return
  cursor++
  if (cursor >= pool.length) return finish()
  nextQuestion()
}

function persist() {
  const chosen = selectedBooks.length ? selectedBooks : steps().map((_, i) => i)
  if (mode === 'wrong') return
  const payload: BookReviewProgress = {
    ladderKey,
    books: chosen,
    results: { ...results },
    wrongChosen: { ...wrongChosen },
    updatedAt: Date.now(),
  }
  void saveBookProgress(payload)
  lastSession = { ladderKey, books: chosen, done: Object.keys(results).length, updatedAt: Date.now() }
  void saveLastSession(lastSession)
}

async function resumeLast() {
  const s = lastSession
  if (!s) return
  ladderKey = s.ladderKey
  const l = PLACEMENT_LADDERS.find(v => v.key === s.ladderKey) ?? PLACEMENT_LADDERS[0]
  selectedBooks = s.books.filter(i => i >= 0 && i < l.steps.length)
  await start(false)
}

async function refreshSavedState() {
  savedHint = ''
  savedCount = 0
  lastSession = null
  try {
    const session = await loadLastSession()
    if (session && session.done > 0) {
      lastSession = session
      const l = PLACEMENT_LADDERS.find(v => v.key === session.ladderKey)
      const names = session.books
        .map(i => l?.steps[i]?.label)
        .filter(Boolean)
        .join('、')
      savedHint = `上次复习的是《${l?.name ?? session.ladderKey}》${names}（${session.books.length} 册），已过 ${session.done} 个词`
    }
  } catch {
    // 忽略
  }
  await refreshCurrentSaved()
}

async function refreshCurrentSaved() {
  savedCount = 0
  const chosen = selectedBooks.length ? selectedBooks : steps().map((_, i) => i)
  try {
    const saved = await loadBookProgress(ladderKey, chosen)
    if (saved) savedCount = Object.keys(saved.results || {}).length
  } catch {
    // 忽略
  }
}

// ---------------------------------------------------------------- 报告
interface BookStat {
  label: string
  total: number
  tested: number
  right: number
  rate: number
}

function quizStatsSummary() {
  const src = curResults()
  let tested = 0
  let unclear = 0
  for (const p of pool) {
    const k = keyOf(p.word)
    if (!Object.prototype.hasOwnProperty.call(src, k)) continue
    tested++
    if (src[k] !== 1) unclear++
  }
  return { tested, unclear }
}

function bookStats(): BookStat[] {
  const src = curResults()
  return books.map(b => {
    const items = pool.filter(p => p.bookIndex === b.index)
    const testedItems = items.filter(p => hasResult(p.word))
    const right = testedItems.filter(p => src[keyOf(p.word)] === 1).length
    return {
      label: b.label,
      total: items.length,
      tested: testedItems.length,
      right,
      rate: testedItems.length ? Math.round((right / testedItems.length) * 100) : 0,
    }
  })
}

function report() {
  const src = curResults()
  const tested = pool.filter(p => hasResult(p.word))
  const right = tested.filter(p => src[keyOf(p.word)] === 1).length
  const fuzzy = tested.filter(p => src[keyOf(p.word)] === 2).length
  const unknown = tested.filter(p => src[keyOf(p.word)] === 0).length
  const rate = tested.length ? Math.round((right / tested.length) * 100) : 0
  const stats = bookStats()
  const weak = stats.find(s => s.tested > 0 && s.rate < 60)
  const allDone = tested.length === pool.length && pool.length > 0
  const knownCount = right
  const untested = pool.length - tested.length
  const estimate = knownCount + Math.round(untested * (rate / 100))

  if (mode === 'wrong') {
    const fixed = right
    const still = tested.length - right
    const top = tested.length === 0
      ? '生词还没重刷'
      : still === 0
        ? `生词全记住了！${fixed} 个都答对了`
        : `${fixed} 个记住了，还有 ${still} 个没过`
    const advice = still === 0
      ? '这批不太清楚的词已经拿下，可以接着往下刷下一册了。'
      : `还有 ${still} 个词没过，继续重刷或导出这批词集中记一下。`
    return { tested, right, fuzzy, unknown, rate, stats, weak, allDone, knownCount, untested, estimate, top, advice }
  }

  const unclearTotal = fuzzy + unknown
  const top = allDone
    ? weak
      ? `《${weak.label}》还没吃透，其余都过了`
      : unclearTotal === 0
        ? '这一套全掌握了'
        : `过完一轮：筛出 ${unclearTotal} 个待补漏单词`
    : weak
      ? `水平到《${weak.label}》为止`
      : `已过 ${tested.length} / ${pool.length} 个词`
  const advice = allDone
    ? weak
      ? `《${weak.label}》掌握率 ${weak.rate}%，建议把筛出的 ${unclearTotal} 个词导出来重点背。`
      : unclearTotal === 0
        ? '全部词都过了一遍，这一套可以直接过了。'
        : `可以直接把下面 ${unclearTotal} 个不太清楚的词导出或生成专属词典攻克。`
    : weak
      ? `《${weak.label}》掌握率 ${weak.rate}%，这里是断层，还有 ${untested} 个词未过。`
      : `继续把剩下的 ${untested} 个词过完，结论会更完整。`
  return { tested, right, fuzzy, unknown, rate, stats, weak, allDone, knownCount, untested, estimate, top, advice }
}

function wrongList(): PoolItem[] {
  const src = curResults()
  return pool.filter(p => {
    const code = src[keyOf(p.word)]
    return code === 0 || code === 2
  })
}

function unclearRows(): UnclearRow[] {
  const src = curResults()
  const rows: UnclearRow[] = []
  for (const p of pool) {
    const k = keyOf(p.word)
    const code = src[k]
    if (code !== 0 && code !== 2) continue
    rows.push({
      key: k,
      word: p.word,
      bookLabel: p.bookLabel,
      status: code === 2 ? 'fuzzy' : 'unknown',
      chosenWrong: wrongChosen[k],
    })
  }
  return rows
}

function filteredUnclearRows(): UnclearRow[] {
  const all = unclearRows()
  const q = reportSearch.trim().toLowerCase()
  return all.filter(r => {
    if (reportFilter !== 'all' && r.status !== reportFilter) return false
    if (!q) return true
    const cn = firstTrans(r.word).toLowerCase()
    return r.word.word.toLowerCase().includes(q) || cn.includes(q) || r.bookLabel.toLowerCase().includes(q)
  })
}

function wrongPageRows(): UnclearRow[] {
  const all = filteredUnclearRows()
  if (showAllWrong) return all
  return all.slice(wrongPage * WRONG_PAGE_SIZE, (wrongPage + 1) * WRONG_PAGE_SIZE)
}

function wrongPageCount(): number {
  return Math.ceil(filteredUnclearRows().length / WRONG_PAGE_SIZE) || 1
}

// ---------------------------------------------------------------- 继续
function nextBookIndex(): number {
  const done = new Set(selectedBooks)
  const total = steps().length
  for (let i = 0; i < total; i++) {
    if (!done.has(i)) return i
  }
  return -1
}

function nextBookLabel(): string {
  const i = nextBookIndex()
  return i >= 0 ? steps()[i].label : ''
}

async function continueNextBook() {
  const i = nextBookIndex()
  if (i < 0) return
  const carried = { ...results }
  const carriedWrong = { ...wrongChosen }
  if (!selectedBooks.includes(i)) selectedBooks = [...selectedBooks, i].sort((a, b) => a - b)
  mode = 'full'
  await loadBooks()
  phase = 'loading'
  loadingText = '正在准备词表…'
  results = carried
  wrongChosen = carriedWrong
  cursor = 0
  while (cursor < pool.length && hasResult(pool[cursor].word)) cursor++
  phase = 'quiz'
  nextQuestion()
  persist()
}

async function retryWrong() {
  const wrong = wrongList()
  if (!wrong.length) {
    Toast.info('没有不太清楚的词，不需要重刷')
    return
  }
  mode = 'wrong'
  if (!books.length) await loadBooks()
  phase = 'loading'
  loadingText = '正在准备生词…'
  pool = wrong.slice()
  retryResults = {}
  cursor = 0
  phase = 'quiz'
  nextQuestion()
}

// ---------------------------------------------------------------- 导出 / 词典 / 错词本
function downloadTextFile(filename: string, content: string, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function exportUnclearCsv() {
  const rowsData = unclearRows()
  if (!rowsData.length) {
    Toast.info('目前没有不太清楚的单词需要导出')
    return
  }
  const rows: string[][] = [['单词', '音标', '释义', '所属册子', '状态', '误选词']]
  for (const r of rowsData) {
    rows.push([
      r.word.word,
      r.word.phonetic1 || r.word.phonetic0 || '',
      firstTrans(r.word),
      r.bookLabel,
      r.status === 'fuzzy' ? '不太清楚' : '不会',
      r.chosenWrong || '',
    ])
  }
  const csv =
    '\uFEFF' +
    rows.map(row => row.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  downloadTextFile(
    `不太清楚的单词_${new Date().toISOString().slice(0, 10)}.csv`,
    csv,
    'text/csv;charset=utf-8'
  )
  Toast.success(`已导出 ${rowsData.length} 个不太清楚的单词`)
}

function exportUnclearTxt() {
  const rowsData = unclearRows()
  if (!rowsData.length) {
    Toast.info('没有不太清楚的单词可导出')
    return
  }
  const lines = rowsData.map(r => `${r.word.word}\t${firstTrans(r.word)}`)
  downloadTextFile(`待补漏词表_${new Date().toISOString().slice(0, 10)}.txt`, lines.join('\r\n'))
  Toast.success(`已导出 ${rowsData.length} 个词（TXT）`)
}

async function copyUnclearWords() {
  const rowsData = unclearRows()
  if (!rowsData.length) {
    Toast.info('没有不太清楚的单词可复制')
    return
  }
  const text = rowsData.map(r => `${r.word.word}  ${firstTrans(r.word)}`).join('\n')
  try {
    await navigator.clipboard.writeText(text)
    Toast.success(`已复制 ${rowsData.length} 个词到剪贴板`)
  } catch {
    Toast.warning('浏览器限制自动复制，请使用导出 CSV / TXT')
  }
}

function createGapDict() {
  const rowsData = unclearRows()
  if (!rowsData.length) {
    Toast.info('没有不太清楚的单词，无需生成词典')
    return
  }
  const name = `查缺补漏_${ladder().name.slice(0, 6)}_${new Date().toISOString().slice(5, 10)}(${rowsData.length}词)`
  const newDict = getDefaultDict({
    id: `custom-gap-${Date.now()}`,
    name,
    description: `整本复习筛出的不太清楚单词（共 ${rowsData.length} 词）`,
    type: DictType.word,
    custom: true,
    words: rowsData.map(r => cloneDeep(toRaw(r.word))),
    length: rowsData.length,
  })
  base.word.bookList.push(newDict)
  Toast.success(`已生成专属词典《${name}》，在「我的词典」可专项练习`)
}

function exportCsv() {
  const src = curResults()
  const rows: string[][] = [['单词', '音标', '释义', '所属册子', '结果', '误选词']]
  for (const p of pool) {
    if (!hasResult(p.word)) continue
    const code = src[keyOf(p.word)]
    const label = code === 1 ? '答对' : code === 2 ? '不太清楚' : '答错'
    rows.push([
      p.word.word,
      p.word.phonetic1 || p.word.phonetic0 || '',
      firstTrans(p.word),
      p.bookLabel,
      label,
      wrongChosen[keyOf(p.word)] || '',
    ])
  }
  const csv =
    '\uFEFF' +
    rows.map(row => row.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  downloadTextFile(`整本复习_${new Date().toISOString().slice(0, 10)}.csv`, csv, 'text/csv;charset=utf-8')
  Toast.success(`全量明细 CSV 已导出，${rows.length - 1} 个词`)
}

function addWrongToBook() {
  const rowsData = unclearRows()
  let n = 0
  for (const r of rowsData) {
    const k = r.key
    if (base.wrong.words.find(v => (v.word || '').trim().toLowerCase() === k)) continue
    base.wrong.words.push(cloneDeep(toRaw(r.word)))
    n++
  }
  base.wrong.length = base.wrong.words.length
  const total = rowsData.length
  if (!total) {
    Toast.info('没有不太清楚的词，不需要加入错词本')
    return
  }
  if (n > 0) Toast.success(`已把 ${n} 个词加进错词本，现有 ${base.wrong.words.length} 个`)
  else Toast.info(`这 ${total} 个词错词本里已经有了`)
}

function finish() {
  cancelWordPracticeAudio()
  phase = 'report'
  wrongPage = 0
  showAllWrong = false
  reportFilter = 'all'
  reportSearch = ''
}

function restart() {
  cancelWordPracticeAudio()
  phase = 'setup'
  pool = []
  results = {}
  retryResults = {}
  wrongChosen = {}
  mode = 'full'
  cursor = 0
  books = []
  void refreshSavedState()
}

onUnmounted(() => {
  cancelWordPracticeAudio()
})

// ---------------------------------------------------------------- 键盘
useStartKeyboardEventListener()
useEvents([
  [ShortcutKey.ChooseA, () => select(0)],
  [ShortcutKey.ChooseB, () => select(1)],
  [ShortcutKey.ChooseC, () => select(2)],
  [ShortcutKey.ChooseD, () => select(3)],
  [ShortcutKey.ToggleSimple, () => {
    if (phase === 'quiz' && !submitted) markClearAndNext()
  }],
  [ShortcutKey.WordTestingNext, () => {
    if (submitted) advance()
  }],
])

onMounted(async () => {
  ladderKey = PLACEMENT_LADDERS[0].key
  selectedBooks = PLACEMENT_LADDERS[0].steps.map((_, i) => i)
  try {
    const list = await fetch(resourceWrap(DICT_LIST.WORD.ALL)).then(r => r.json())
    const map = new Map<number, { name: string, url: string, length: number }>()
    for (const item of list) map.set(Number(item.id), item)
    dictListCache = map
  } catch {
    // 忽略
  }
  await refreshSavedState()
})
</script>

<template>
  <BasePage>
    <!-- ============================ 1. 设置 ============================ -->
    <div v-if="phase === 'setup'" class="card flex flex-col gap-5">
      <div>
        <div class="page-title">整本复习</div>
        <div class="text-base color-reverse-black mt-1">
          选中教材与册子，把单词过一遍，结束后精准导出不会或不太清楚的词。
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="title">选教材</div>
        <div class="flex gap-2 flex-wrap">
          <BaseButton
            v-for="l in PLACEMENT_LADDERS"
            :key="l.key"
            :type="ladderKey === l.key ? 'primary' : 'info'"
            @click="changeLadder(l.key)"
          >
            {{ l.name }}
          </BaseButton>
        </div>
        <div class="text-sm color-reverse-black">{{ ladder().desc }}</div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div class="title">选册子（可多选）</div>
          <div class="flex items-center gap-3 text-sm">
            <span class="cursor-pointer color-link" @click="selectStage('all')">九年全套</span>
            <span v-if="hasPrimarySteps()" class="cursor-pointer color-link" @click="selectStage('primary')">仅小学</span>
            <span v-if="hasJuniorSteps()" class="cursor-pointer color-link" @click="selectStage('junior')">仅初中</span>
            <BaseButton type="text" @click="toggleAllBooks">
              {{ selectedBooks.length === steps().length ? '取消全选' : '全选' }}
            </BaseButton>
          </div>
        </div>
        <div class="flex gap-2 flex-wrap">
          <div
            v-for="(s, i) in steps()"
            :key="i"
            class="book-chip"
            :class="selectedBooks.includes(i) ? 'on' : ''"
            @click="toggleBook(i)"
          >
            <span>{{ s.label }}</span>
            <span class="book-chip-num">{{ bookSize(i) }}</span>
          </div>
        </div>
        <div class="text-sm color-reverse-black">
          已选 {{ selectedBooks.length }} 册 · 约 {{ selectedWordCount() }} 个词（重复词只过一遍）。
        </div>
        <div v-if="savedHint" class="text-sm color-link">{{ savedHint }}</div>
      </div>

      <div class="flex items-center">
        <Checkbox v-model="shuffleOrder">随机乱序出题</Checkbox>
      </div>

      <div class="flex gap-3 flex-wrap items-center">
        <BaseButton
          type="primary"
          :disabled="selectedBooks.length === 0"
          disabled-reason="至少选一册书"
          @click="start(false)"
        >
          {{ savedCount > 0 ? `继续（已过 ${savedCount} 词）` : '开始复习' }}
        </BaseButton>
        <BaseButton v-if="lastSession && lastSession.done > 0" type="info" @click="resumeLast">
          接着上次（已过 {{ lastSession.done }} 词）
        </BaseButton>
        <BaseButton v-if="savedCount > 0" type="info" @click="start(true)">
          重新开始
        </BaseButton>
        <BaseButton type="text" @click="nav('/placement-test')">去摸底测试</BaseButton>
        <BaseButton type="text" @click="nav('/words')">返回</BaseButton>
      </div>
    </div>

    <!-- ============================ 2. 载入 ============================ -->
    <div v-else-if="phase === 'loading'" class="card flex flex-col gap-3">
      <div class="page-title">正在准备词表…</div>
      <div class="text-base">{{ loadingText }}</div>
    </div>

    <!-- ============================ 3. 答题 ============================ -->
    <div v-else-if="phase === 'quiz'" class="card flex flex-col gap-4">
      <div class="flex items-center justify-between flex-wrap gap-2">
        <div class="flex items-center gap-3">
          <div class="page-title">{{ mode === 'wrong' ? '重刷生词' : '整本复习' }}</div>
          <span class="text-sm color-reverse-black">
            当前册子：{{ pool[cursor]?.bookLabel }} · 已过 {{ quizStatsSummary().tested }} · 生词 {{ quizStatsSummary().unclear }}
          </span>
        </div>
        <div class="text-base">第 {{ cursor + 1 }} / {{ pool.length }} 个词</div>
      </div>

      <div class="bar-track">
        <div class="bar-fill bg-green-500" :style="{ width: Math.round((cursor / Math.max(pool.length, 1)) * 100) + '%' }" />
      </div>

      <div v-if="question" class="flex flex-col gap-4">
        <div class="text-4xl en-article-family flex flex-wrap items-center gap-3">
          <span>{{ question.candidates[question.correctIndex].word.word }}</span>
          <span class="text-xl">{{ question.candidates[question.correctIndex].word.phonetic1 || question.candidates[question.correctIndex].word.phonetic0 }}</span>
          <VolumeIcon title="发音" :cb="() => playWordAudio(question!.candidates[question!.correctIndex].word.word, true)" />
        </div>

        <div class="grid gap-3">
          <div
            v-for="(opt, i) in question.candidates"
            :key="i"
            class="option border rounded cursor-pointer text-lg"
            :class="{
              'text-green-600': submitted && i === question.correctIndex,
              'text-red-600': submitted && i === selectedIndex && i !== question.correctIndex,
            }"
            @click="submitted ? playWordAudio(opt.word.word) : select(i)"
          >
            <span class="italic">{{ optionLabels[i] }}</span>
            <span class="mx-2">[{{ [settingStore.shortcutKeyMap[ShortcutKey.ChooseA], settingStore.shortcutKeyMap[ShortcutKey.ChooseB], settingStore.shortcutKeyMap[ShortcutKey.ChooseC], settingStore.shortcutKeyMap[ShortcutKey.ChooseD]][i] }}]</span>
            <span>{{ shortTrans(opt.word) }}</span>
          </div>
        </div>

        <div v-if="submitted" class="flex items-center justify-between flex-wrap gap-2 text-base">
          <div>
            <span v-if="currentItemCode() === 1" class="text-green-600">答对了！</span>
            <span v-else-if="currentItemCode() === 2" class="text-amber-600">
              已标为不太清楚：{{ question.candidates[question.correctIndex].word.word }}（{{ firstTrans(question.candidates[question.correctIndex].word) }}）
            </span>
            <span v-else class="text-red-600">
              正确答案：{{ question.candidates[question.correctIndex].word.word }}（{{ firstTrans(question.candidates[question.correctIndex].word) }}）
            </span>
          </div>
          <BaseButton
            v-if="currentItemCode() === 1"
            type="text"
            @click="togglePostSubmitOutcome(2)"
          >
            其实是蒙的？标为不太清楚
          </BaseButton>
          <BaseButton
            v-else
            type="text"
            @click="togglePostSubmitOutcome(1)"
          >
            其实认识（改标清楚）
          </BaseButton>
        </div>

        <div v-if="submitted" class="detail-box">
          <div class="flex items-center justify-between flex-wrap gap-2">
            <div class="title text-sm">这一题的四个单词（点击英文可发音）</div>
            <BaseButton type="text" @click="showDetail = !showDetail">
              {{ showDetail ? '收起' : '展开对照' }}
            </BaseButton>
          </div>
          <div v-if="showDetail" class="grid md:grid-cols-2 gap-2 mt-2">
            <div
              v-for="d in optionDetail()"
              :key="d.label"
              class="detail-row"
              :class="{ 'is-correct': d.isCorrect, 'is-chosen': d.isChosen && !d.isCorrect }"
            >
              <span class="detail-label">{{ d.label }}</span>
              <span class="detail-cn">{{ d.cn }}</span>
              <span class="detail-arrow">→</span>
              <span class="detail-en" @click="playWordAudio(d.en, true)">{{ d.en }}</span>
              <span v-if="d.isCorrect" class="detail-tag correct">正确</span>
              <span v-else-if="d.isChosen" class="detail-tag wrong">你选的</span>
            </div>
          </div>
        </div>

        <div class="mt-2 flex gap-3 flex-wrap items-center justify-between">
          <div class="flex gap-3 flex-wrap items-center">
            <template v-if="!submitted">
              <BaseButton type="primary" @click="markClearAndNext">
                清楚 · 秒过 [{{ settingStore.shortcutKeyMap[ShortcutKey.ToggleSimple] }}]
              </BaseButton>
              <BaseButton type="info" @click="markFuzzy">不太清楚</BaseButton>
              <BaseButton type="info" @click="skipUnknown">不认识</BaseButton>
            </template>
            <BaseButton v-else type="primary" @click="advance">
              下一个[{{ settingStore.shortcutKeyMap[ShortcutKey.WordTestingNext] }}]
            </BaseButton>
          </div>
          <div class="flex gap-3 items-center">
            <BaseButton v-if="cursor > 0" type="text" @click="prevQuestion">上一题</BaseButton>
            <BaseButton type="info" @click="finish">结束，看结果</BaseButton>
          </div>
        </div>
      </div>
    </div>

    <!-- ============================ 4. 报告 ============================ -->
    <div v-else class="card flex flex-col gap-5">
      <div>
        <div class="page-title">{{ mode === 'wrong' ? '生词重刷结果' : '复习结果' }}</div>
        <div class="text-3xl font-bold mt-2">{{ report().top }}</div>
        <div class="text-base mt-1">
          已过 {{ report().tested.length }} / {{ pool.length }} 个词
          （清楚 {{ report().right }} · 不太清楚 {{ report().fuzzy }} · 不会 {{ report().unknown }} · 掌握率 {{ report().rate }}%）
        </div>
      </div>

      <div class="grid md:grid-cols-3 gap-4">
        <div class="stat2">
          <div class="num">{{ report().knownCount }}</div>
          <div class="txt">已确认掌握（个）</div>
        </div>
        <div class="stat2">
          <div class="num">{{ report().fuzzy + report().unknown }}</div>
          <div class="txt">不太清楚 / 不会（个）</div>
        </div>
        <div class="stat2">
          <div class="num">{{ report().weak?.label || '无断层' }}</div>
          <div class="txt">推算词汇量约 {{ report().estimate }}</div>
        </div>
      </div>

      <div v-if="mode === 'full'" class="flex flex-col gap-2">
        <div class="title">每册掌握情况</div>
        <div v-for="s in report().stats" :key="s.label" class="sweep-row flex items-center gap-3">
          <div class="w-28 text-base">{{ s.label }}</div>
          <div class="bar-track flex-1">
            <div
              class="bar-fill"
              :class="s.rate >= 80 ? 'bg-green-500' : s.rate >= 60 ? 'bg-yellow-500' : 'bg-red-500'"
              :style="{ width: s.rate + '%' }"
            />
          </div>
          <div class="w-40 text-sm">答对 {{ s.right }} / 测 {{ s.tested }} · {{ s.rate }}%</div>
        </div>
      </div>

      <!-- 简洁导出区：一行直达，重点突出「导出不太清楚的单词」 -->
      <div class="flex gap-3 flex-wrap items-center">
        <BaseButton type="primary" @click="exportUnclearCsv">
          导出不太清楚的单词（CSV · {{ unclearRows().length }} 词）
        </BaseButton>
        <BaseButton type="info" @click="createGapDict">生成专属补漏词典</BaseButton>
        <BaseButton type="info" @click="addWrongToBook">加入错词本</BaseButton>
        <span class="text-sm cursor-pointer color-link ml-1" @click="copyUnclearWords">复制词表</span>
        <span class="text-sm cursor-pointer color-link" @click="exportUnclearTxt">导出 TXT</span>
        <span class="text-sm cursor-pointer color-link" @click="exportCsv">导出全量明细</span>
      </div>

      <!-- 生词表 -->
      <div class="flex flex-col gap-3">
        <div class="flex items-center justify-between flex-wrap gap-2">
          <div class="title">生词表（{{ filteredUnclearRows().length }} 个）</div>
          <div class="flex items-center gap-2 flex-wrap">
            <BaseButton size="small" :type="reportFilter === 'all' ? 'primary' : 'info'" @click="reportFilter = 'all'; wrongPage = 0">
              全部 ({{ unclearRows().length }})
            </BaseButton>
            <BaseButton size="small" :type="reportFilter === 'unknown' ? 'primary' : 'info'" @click="reportFilter = 'unknown'; wrongPage = 0">
              不会 ({{ unclearRows().filter(r => r.status === 'unknown').length }})
            </BaseButton>
            <BaseButton size="small" :type="reportFilter === 'fuzzy' ? 'primary' : 'info'" @click="reportFilter = 'fuzzy'; wrongPage = 0">
              不太清楚 ({{ unclearRows().filter(r => r.status === 'fuzzy').length }})
            </BaseButton>
            <BaseButton v-if="filteredUnclearRows().length > WRONG_PAGE_SIZE" type="text" @click="showAllWrong = !showAllWrong">
              {{ showAllWrong ? '分页显示' : '全部展开' }}
            </BaseButton>
          </div>
        </div>

        <BaseInput
          v-if="unclearRows().length > 10"
          v-model="reportSearch"
          placeholder="搜索单词或释义…"
          clearable
        />

        <div class="grid md:grid-cols-2 gap-2">
          <div
            v-for="r in wrongPageRows()"
            :key="r.key"
            class="unclear-card border rounded text-base flex flex-col gap-1"
          >
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold cursor-pointer detail-en" @click="playWordAudio(r.word.word, true)">
                {{ r.word.word }}
              </span>
              <span v-if="r.word.phonetic1 || r.word.phonetic0" class="text-sm opacity-75">
                {{ r.word.phonetic1 || r.word.phonetic0 }}
              </span>
              <span class="status-pill" :class="r.status">
                {{ r.status === 'fuzzy' ? '不太清楚' : '不会' }}
              </span>
              <span class="text-xs opacity-70">· {{ r.bookLabel }}</span>
            </div>
            <div class="text-sm color-reverse-black">
              {{ firstTrans(r.word) }}
              <span v-if="r.chosenWrong" class="text-red-500 ml-2">（误选：{{ r.chosenWrong }}）</span>
            </div>
          </div>
        </div>

        <div v-if="!showAllWrong && wrongPageCount() > 1" class="flex gap-3 items-center">
          <BaseButton type="info" size="small" @click="wrongPage = Math.max(0, wrongPage - 1)">上一页</BaseButton>
          <span class="text-sm">第 {{ wrongPage + 1 }} / {{ wrongPageCount() }} 页</span>
          <BaseButton type="info" size="small" @click="wrongPage = Math.min(wrongPageCount() - 1, wrongPage + 1)">下一页</BaseButton>
        </div>
      </div>

      <!-- 接着来 -->
      <div class="continue-box flex flex-col gap-2">
        <div class="flex gap-3 flex-wrap items-center">
          <BaseButton
            v-if="mode !== 'wrong' && nextBookIndex() >= 0"
            type="primary"
            @click="continueNextBook"
          >
            接着刷下一册：{{ nextBookLabel() }}
          </BaseButton>
          <BaseButton
            v-if="mode !== 'wrong' && wrongList().length > 0"
            type="primary"
            @click="retryWrong"
          >
            只重刷生词（{{ wrongList().length }} 个）
          </BaseButton>
          <BaseButton v-if="mode === 'wrong'" type="primary" @click="restart">
            回到整本复习
          </BaseButton>
          <BaseButton type="info" @click="restart">再选册子</BaseButton>
          <BaseButton type="text" @click="nav('/words')">返回词表</BaseButton>
        </div>
      </div>
    </div>
  </BasePage>
</template>

<style scoped>
.book-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.8rem;
  border: 1px solid var(--color-main-text);
  border-radius: 0.3rem;
  cursor: pointer;
  user-select: none;
  font-size: 0.95rem;

  &.on {
    background: var(--btn-primary, rgb(75, 85, 99));
    color: white;
  }

  .book-chip-num {
    font-size: 0.75rem;
    opacity: 0.7;
  }
}

.bar-track {
  height: 0.5rem;
  border-radius: 0.25rem;
  background: var(--color-second, #eee);
  overflow: hidden;
  width: 100%;
}

.bar-fill {
  height: 100%;
  transition: width 0.2s;
}

.detail-box {
  border: 1px solid var(--color-item-border, #eee);
  border-radius: 0.4rem;
  padding: 0.75rem 1rem;
  background: var(--bg-card-secend, rgb(0 0 0 / 2%));
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.6rem;
  border-radius: 0.3rem;
  border: 1px solid transparent;
  font-size: 0.95rem;

  &.is-correct {
    border-color: rgb(34 197 94 / 60%);
    background: rgb(34 197 94 / 8%);
  }

  &.is-chosen {
    border-color: rgb(239 68 68 / 60%);
    background: rgb(239 68 68 / 8%);
  }
}

.detail-label {
  font-weight: 700;
  min-width: 1.2rem;
}

.detail-cn {
  color: var(--color-main-text);
}

.detail-arrow {
  opacity: 0.5;
}

.detail-en {
  font-weight: 700;
  cursor: pointer;
  text-decoration: underline dotted;
  text-underline-offset: 3px;
}

.detail-tag {
  font-size: 0.75rem;
  padding: 0.05rem 0.4rem;
  border-radius: 0.25rem;

  &.correct {
    background: rgb(34 197 94 / 18%);
    color: rgb(22 163 74);
  }

  &.wrong {
    background: rgb(239 68 68 / 18%);
    color: rgb(220 38 38);
  }
}

.unclear-card {
  padding: 0.55rem 0.75rem;
  border-color: var(--color-item-border, #e5e7eb);
}

.status-pill {
  font-size: 0.75rem;
  padding: 0.05rem 0.45rem;
  border-radius: 0.25rem;

  &.unknown {
    background: rgb(239 68 68 / 15%);
    color: rgb(220 38 38);
  }

  &.fuzzy {
    background: rgb(245 158 11 / 16%);
    color: rgb(217 119 6);
  }
}

.continue-box {
  border-top: 1px solid var(--color-item-border, #e5e7eb);
  padding-top: 0.85rem;
}
</style>
