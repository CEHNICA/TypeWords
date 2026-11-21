<script setup lang="ts">
/**
 * 整本复习（Book Review）
 * ==========================
 * 用户要的是：同时勾几本书 → 这几本书的单词**全部囊括进来** → 一个一个点完
 * → 总结「这几本书他掌握到什么水平」。
 *
 * 和「水平摸底」的区别：
 *  - 摸底是**抽样**：每册抽几题，快速定位年级
 *  - 整本复习是**全量**：选中的每一册的每一个词都要过一遍，一个不漏
 *
 * 莱芜三上~五下加起来 859 个词 → 必须能中断续做，所以每答一题就落一次盘。
 */
import { onMounted } from 'vue'
import { BaseButton, BasePage, Toast, VolumeIcon } from '@/base'
import { useBaseStore } from '@/core/stores/base.ts'
import { _getDictDataByUrl, resourceWrap } from '@/core/utils'
import { DICT_LIST } from '@/core/config/env.ts'
import { buildQuestion } from '@/core/utils/word-test'
import { PLACEMENT_LADDERS } from '@/core/data/placement'
import {
  clearBookProgress,
  loadBookProgress,
  loadLastSession,
  saveBookProgress,
  saveLastSession,
  type BookReviewProgress,
  type BookReviewSession,
} from '@/core/utils/placement-progress'
import type { Question, Word } from '@/core/types/types.ts'
import { usePlayBeep, usePlayCorrect, usePlayWordAudio } from '@/core/hooks/sound.ts'
import { useEvents } from '@/core/utils/eventBus'
import { useStartKeyboardEventListener } from '@/core/hooks/event.ts'
import { ShortcutKey } from '@/core/types/enum'
import { useSettingStore } from '@/core/stores/setting.ts'
import { useNav } from '@/core/utils'

interface BookInfo {
  /** 在 ladder.steps 里的下标 */
  index: number
  label: string
  words: Word[]
}

interface PoolItem {
  word: Word
  bookIndex: number
  bookLabel: string
}

const base = useBaseStore()
const settingStore = useSettingStore()
const playBeep = usePlayBeep()
const playCorrect = usePlayCorrect()
const playWordAudio = usePlayWordAudio()
const { nav } = useNav()

let phase = $ref<'setup' | 'loading' | 'quiz' | 'report'>('setup')
let ladderKey = $ref('lw')
/** 选中的册子下标（可多选） */
let selectedBooks = $ref<number[]>([])
let books = $ref<BookInfo[]>([])
/** 合并去重后的全部词（这就是要过的全量题库） */
let pool = $ref<PoolItem[]>([])
/** 小写单词 → 1 答对 / 0 答错 */
let results = $ref<Record<string, 0 | 1>>({})
/** 已经过到第几个词 */
let cursor = $ref(0)
let question = $ref<Question | null>(null)
let submitted = $ref(false)
let selectedIndex = $ref(-1)
/** setup 页提示「上次做到 x/y」 */
let savedHint = $ref('')
/** 上次已经过了多少个词（>0 说明有进度可续） */
let savedCount = $ref(0)
/** 最近一次复习的是哪套书（刷新后靠它找回上次的册子组合） */
let lastSession = $ref<BookReviewSession | null>(null)
let loadingText = $ref('正在准备词表…')
/** 生词表分页（几百行一起渲染会卡） */
let wrongPage = $ref(0)
let showAllWrong = $ref(false)

const WRONG_PAGE_SIZE = 50
const optionLabels = ['A', 'B', 'C', 'D']

const ladder = () => PLACEMENT_LADDERS.find(v => v.key === ladderKey) ?? PLACEMENT_LADDERS[0]
const steps = () => ladder().steps
const keyOf = (w: Word) => (w?.word || '').trim().toLowerCase()
const hasResult = (w: Word) => Object.prototype.hasOwnProperty.call(results, keyOf(w))

/** 小学词库释义又长又全，低年级读不完 */
function shortTrans(word: Word): string {
  const cn = word?.trans?.[0]?.cn || ''
  const first = cn.split(/[；;]/)[0].trim()
  const cut = first.length > 14 ? first.slice(0, 14) + '…' : first
  return cut || word?.word || ''
}

/** 词条清洗：小学词库有一批词条缺 relWords.rels / trans，直接访问会崩 */
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

// ---------------------------------------------------------------- 册子多选
function toggleBook(index: number) {
  const i = selectedBooks.indexOf(index)
  if (i === -1) selectedBooks = [...selectedBooks, index]
  else selectedBooks = selectedBooks.filter(v => v !== index)
  selectedBooks.sort((a, b) => a - b)
  void refreshCurrentSaved()
}

/** 全选 / 取消全选 */
function toggleAllBooks() {
  selectedBooks = selectedBooks.length === steps().length ? [] : steps().map((_, i) => i)
  void refreshCurrentSaved()
}

/** 估算选中的册子一共多少词（按词库清单里的 length，秒出，不用下载） */
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

/** 单册词数（词库清单里的 length 之和） */
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

/** 换教材：册子列表全变了，重选为该教材全部册子，并看看上次做到哪 */
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
        // 这一本拉不到就跳过，不影响别的册子
      }
    }
    out.push({ index, label: step.label, words })
  }
  books = out
  buildPool()
}

/** 合并选中册子的全部词，去重（同一个词在多本里出现只过一次） */
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
  pool = items
}

async function start(fresh = false) {
  // 先把词表拉下来、合并去重，再谈进度
  await loadBooks()
  phase = 'loading'
  loadingText = '正在准备词表…'
  const chosen = selectedBooks.length ? selectedBooks : steps().map((_, i) => i)
  const saved = fresh ? null : await loadBookProgress(ladderKey, chosen)
  if (fresh) await clearBookProgress(ladderKey, chosen)
  results = saved?.results ? { ...saved.results } : {}
  // 续做：找到第一个没测过的词
  cursor = 0
  while (cursor < pool.length && hasResult(pool[cursor].word)) cursor++
  phase = 'quiz'
  nextQuestion()
}

// ---------------------------------------------------------------- 出题 / 答题
/** 出题：题干是当前词，干扰项优先取同一册的词（不跨量级） */
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
}

/** 选了一个选项 */
function select(i: number) {
  if (submitted || !question) return
  selectedIndex = i
  submitted = true
  const correct = i === question.correctIndex
  results = { ...results, [keyOf(pool[cursor].word)]: correct ? 1 : 0 }
  if (correct) playCorrect()
  else playBeep()
  persist()
}

/** 「不认识」：直接记生词并跳过（几百题全靠四选一点不动） */
function skipUnknown() {
  if (submitted || !question) return
  selectedIndex = -1
  submitted = true
  results = { ...results, [keyOf(pool[cursor].word)]: 0 }
  playBeep()
  persist()
}

/** 记完一题 → 下一个词 */
function advance() {
  if (!submitted) return
  if (phase !== 'quiz') return
  cursor++
  if (cursor >= pool.length) return finish()
  nextQuestion()
}

/** 每答一题就落盘（几百题，中途关掉不能白干） */
function persist() {
  const chosen = selectedBooks.length ? selectedBooks : steps().map((_, i) => i)
  const payload: BookReviewProgress = {
    ladderKey,
    books: chosen,
    results: { ...results },
    updatedAt: Date.now(),
  }
  void saveBookProgress(payload)
  lastSession = { ladderKey, books: chosen, done: Object.keys(results).length, updatedAt: Date.now() }
  void saveLastSession(lastSession)
}

/** 继续最近一次：把那套书重新选上，然后接着做 */
async function resumeLast() {
  const s = lastSession
  if (!s) return
  ladderKey = s.ladderKey
  const l = PLACEMENT_LADDERS.find(v => v.key === s.ladderKey) ?? PLACEMENT_LADDERS[0]
  selectedBooks = s.books.filter(i => i >= 0 && i < l.steps.length)
  await start(false)
}

/** 读一下最近一次复习到哪了 */
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
    // 读不到就当没有
  }
  await refreshCurrentSaved()
}

/** 当前这套选择自己的进度（换个册子组合，进度也是分开的） */
async function refreshCurrentSaved() {
  savedCount = 0
  const chosen = selectedBooks.length ? selectedBooks : steps().map((_, i) => i)
  try {
    const saved = await loadBookProgress(ladderKey, chosen)
    if (saved) savedCount = Object.keys(saved.results || {}).length
  } catch {
    // 读不到就当没有
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

function bookStats(): BookStat[] {
  return books.map(b => {
    const items = pool.filter(p => p.bookIndex === b.index)
    const testedItems = items.filter(p => hasResult(p.word))
    const right = testedItems.filter(p => results[keyOf(p.word)] === 1).length
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
  const tested = pool.filter(p => hasResult(p.word))
  const right = tested.filter(p => results[keyOf(p.word)] === 1).length
  const rate = tested.length ? Math.round((right / tested.length) * 100) : 0
  const stats = bookStats()
  // 第一个掌握率 <60% 的册子 = 断层（水平上限）
  const weak = stats.find(s => s.tested > 0 && s.rate < 60)
  const allDone = tested.length === pool.length && pool.length > 0
  const knownCount = right
  const untested = pool.length - tested.length
  // 推算：按当前掌握率外推未测部分（不把各册词数直接求和，重复词会虚高）
  const estimate = knownCount + Math.round(untested * (rate / 100))
  const top = allDone
    ? weak
      ? `《${weak.label}》还没吃透，其余都过了`
      : '这一套全掌握了，可以进下一套书'
    : weak
      ? `水平到《${weak.label}》为止`
      : `已过 ${tested.length} / ${pool.length} 个词`
  const advice = allDone
    ? weak
      ? `《${weak.label}》掌握率只有 ${weak.rate}%，先把这一册的生词啃下来。`
      : '全部词都过了一遍，这一套可以直接过了。'
    : weak
      ? `《${weak.label}》掌握率 ${weak.rate}%，这里是断层。剩下的 ${untested} 个词还没过。`
      : `继续把剩下的 ${untested} 个词过完，结论会更准。`
  return { tested, right, rate, stats, weak, allDone, knownCount, untested, estimate, top, advice }
}

/** 生词表：全部答错的词 */
function wrongList() {
  return pool.filter(p => results[keyOf(p.word)] === 0)
}

/** 生词表分页数据 */
function wrongPageRows() {
  const all = wrongList()
  if (showAllWrong) return all
  return all.slice(wrongPage * WRONG_PAGE_SIZE, (wrongPage + 1) * WRONG_PAGE_SIZE)
}

function wrongPageCount() {
  return Math.ceil(wrongList().length / WRONG_PAGE_SIZE) || 1
}

// ---------------------------------------------------------------- 导出 / 错词本
function exportCsv() {
  const rows: string[][] = [['单词', '音标', '释义', '所属册子', '结果']]
  for (const p of pool) {
    if (!hasResult(p.word)) continue
    const ok = results[keyOf(p.word)] === 1
    rows.push([
      p.word.word,
      p.word.phonetic1 || p.word.phonetic0 || '',
      shortTrans(p.word),
      p.bookLabel,
      ok ? '答对' : '答错',
    ])
  }
  const csv =
    '\uFEFF' +
    rows.map(row => row.map(c => `"${String(c).replace(/"/g, '""')}"`).join(',')).join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `整本复习_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  Toast.success(`CSV 已导出，${rows.length - 1} 个词`)
}

/** 生词进错词本 */
function addWrongToBook() {
  let n = 0
  for (const p of wrongList()) {
    const k = keyOf(p.word)
    if (base.wrong.words.find(v => (v.word || '').trim().toLowerCase() === k)) continue
    base.wrong.words.push(p.word)
    n++
  }
  base.wrong.length = base.wrong.words.length
  const total = wrongList().length
  if (!total) {
    Toast.info('这一套没有生词，全答对了，没东西要加')
    return
  }
  if (n > 0) {
    Toast.success(`已把 ${n} 个生词加进错词本，错词本现有 ${base.wrong.words.length} 个词`)
  } else {
    Toast.info(`这 ${total} 个生词错词本里已经有了，没重复添加`)
  }
}

function finish() {
  phase = 'report'
  wrongPage = 0
  showAllWrong = false
}

function restart() {
  phase = 'setup'
  pool = []
  results = {}
  cursor = 0
  books = []
}

// ---------------------------------------------------------------- 键盘
useStartKeyboardEventListener()
useEvents([
  [ShortcutKey.ChooseA, () => select(0)],
  [ShortcutKey.ChooseB, () => select(1)],
  [ShortcutKey.ChooseC, () => select(2)],
  [ShortcutKey.ChooseD, () => select(3)],
  [ShortcutKey.WordTestingNext, () => {
    if (submitted) advance()
  }],
])

onMounted(async () => {
  ladderKey = PLACEMENT_LADDERS[0].key
  selectedBooks = PLACEMENT_LADDERS[0].steps.map((_, i) => i)
  // 词库清单：用来显示每册多少词（不用下载词库就能预览）
  try {
    const list = await fetch(resourceWrap(DICT_LIST.WORD.ALL)).then(r => r.json())
    const map = new Map<number, { name: string, url: string, length: number }>()
    for (const item of list) map.set(Number(item.id), item)
    dictListCache = map
  } catch {
    // 清单拉不到只是看不到词数，不影响复习
  }
  // 看看上次做到哪儿了
  await refreshSavedState()
})
</script>

<template>
  <BasePage>
    <!-- ============================ 1. 设置 ============================ -->
    <div v-if="phase === 'setup'" class="card flex flex-col gap-5">
      <div>
        <div class="page-title">整本复习</div>
        <div class="text-base color-reverse-black mt-2">
          同时勾几本书 → 这几本书的<b>全部单词</b>都囊括进来，一个一个点完，
          结束给你一份「这几本书他掌握到什么水平」的总结：综合掌握率 + 每册掌握率 + 生词表。
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="title">选教材</div>
        <div class="flex gap-3 flex-wrap">
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
        <div class="flex items-center justify-between">
          <div class="title">选册子（可多选）</div>
          <BaseButton type="text" @click="toggleAllBooks">
            {{ selectedBooks.length === steps().length ? '取消全选' : '全选' }}
          </BaseButton>
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
          已选 {{ selectedBooks.length }} 册 · 约 {{ selectedWordCount() }} 个词
          （去重后实际要过的词会少一些，重复词只过一遍）。
        </div>
        <div v-if="savedHint" class="text-sm color-link">{{ savedHint }}</div>
      </div>

      <div class="flex gap-4">
        <BaseButton
          type="primary"
          :disabled="selectedBooks.length === 0"
          disabled-reason="至少选一册书"
          @click="start(false)"
        >
          {{ savedCount > 0 ? `继续（已过 ${savedCount} 个词）` : '开始复习' }}
        </BaseButton>
        <BaseButton
          v-if="lastSession && lastSession.done > 0"
          type="info"
          @click="resumeLast"
        >
          接着上次那套（{{ lastSession.books.length }} 册，已过 {{ lastSession.done }} 词）
        </BaseButton>
        <BaseButton
          v-if="savedCount > 0"
          type="info"
          @click="start(true)"
        >
          重新开始（清掉这次选择的进度）
        </BaseButton>
        <BaseButton type="info" @click="nav('/placement-test')">去摸底测试</BaseButton>
        <BaseButton type="info" @click="nav('/words')">返回</BaseButton>
      </div>
    </div>

    <!-- ============================ 2. 载入 ============================ -->
    <div v-else-if="phase === 'loading'" class="card flex flex-col gap-3">
      <div class="page-title">正在准备词表…</div>
      <div class="text-base">{{ loadingText }}</div>
    </div>

    <!-- ============================ 3. 答题 ============================ -->
    <div v-else-if="phase === 'quiz'" class="card flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <div class="page-title">整本复习</div>
        <div class="text-base">
          第 {{ cursor + 1 }} / {{ pool.length }} 个词
        </div>
      </div>

      <div class="flex items-center gap-3 flex-wrap">
        <span class="text-sm px-2 py-1 rounded bg-color-second">
          当前册子：{{ pool[cursor]?.bookLabel }}
        </span>
        <span class="text-sm px-2 py-1 rounded bg-color-second">
          已过 {{ cursor }} · 答对 {{ Object.values(results).filter(v => v === 1).length }}
        </span>
      </div>

      <div class="bar-track">
        <div class="bar-fill bg-green-500" :style="{ width: Math.round((cursor / Math.max(pool.length, 1)) * 100) + '%' }" />
      </div>

      <div v-if="question" class="flex flex-col gap-4">
        <div class="text-4xl en-article-family flex flex-wrap items-center gap-3">
          <span>{{ question.candidates[question.correctIndex].word.word }}</span>
          <span class="text-xl">{{ question.candidates[question.correctIndex].word.phonetic1 }}</span>
          <VolumeIcon title="发音" :cb="() => playWordAudio(question.candidates[question.correctIndex].word.word, true)" />
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

        <div v-if="submitted" class="text-base">
          <span v-if="selectedIndex === question.correctIndex" class="text-green-600">答对了！</span>
          <span v-else class="text-red-600">
            正确答案：{{ question.candidates[question.correctIndex].word.word }}
            （{{ shortTrans(question.candidates[question.correctIndex].word) }}）
          </span>
        </div>

        <div class="mt-2 flex gap-4 flex-wrap">
          <BaseButton v-if="submitted" type="primary" @click="advance">
            下一个[{{ settingStore.shortcutKeyMap[ShortcutKey.WordTestingNext] }}]
          </BaseButton>
          <BaseButton v-if="!submitted" type="info" @click="skipUnknown">
            不认识（记生词，跳过）
          </BaseButton>
          <BaseButton type="info" @click="finish">结束，看结果</BaseButton>
        </div>
      </div>
    </div>

    <!-- ============================ 4. 报告 ============================ -->
    <div v-else class="card flex flex-col gap-5">
      <div>
        <div class="page-title">复习结果</div>
        <div class="text-3xl font-bold mt-2">{{ report().top }}</div>
        <div class="text-base mt-1">
          已过 {{ report().tested.length }} / {{ pool.length }} 个词
          （答对 {{ report().right }} 个，掌握率 {{ report().rate }}%）
        </div>
      </div>

      <div class="grid md:grid-cols-3 gap-4">
        <div class="stat2">
          <div class="num">{{ report().knownCount }}</div>
          <div class="txt">已确认掌握的词（个）</div>
        </div>
        <div class="stat2">
          <div class="num">{{ report().estimate }}</div>
          <div class="txt">推算词汇量（个）</div>
        </div>
        <div class="stat2">
          <div class="num">{{ report().weak?.label || '无断层' }}</div>
          <div class="txt">断层在这一册</div>
        </div>
      </div>

      <div class="text-base">{{ report().advice }}</div>

      <div class="flex flex-col gap-2">
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

      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <div class="title">生词表（{{ wrongList().length }} 个）</div>
          <BaseButton v-if="wrongList().length > WRONG_PAGE_SIZE" type="text" @click="showAllWrong = !showAllWrong">
            {{ showAllWrong ? '分页显示' : '全部展开' }}
          </BaseButton>
        </div>
        <div class="grid md:grid-cols-2 gap-2">
          <div
            v-for="p in wrongPageRows()"
            :key="keyOf(p.word)"
            class="option border rounded text-base flex items-center gap-2"
          >
            <span class="font-bold">{{ p.word.word }}</span>
            <span class="text-sm color-reverse-black">{{ shortTrans(p.word) }}</span>
            <span class="text-sm color-reverse-black">· {{ p.bookLabel }}</span>
          </div>
        </div>
        <div v-if="!showAllWrong && wrongPageCount() > 1" class="flex gap-3 items-center">
          <BaseButton type="info" size="small" @click="wrongPage = Math.max(0, wrongPage - 1)">上一页</BaseButton>
          <span class="text-sm">第 {{ wrongPage + 1 }} / {{ wrongPageCount() }} 页</span>
          <BaseButton type="info" size="small" @click="wrongPage = Math.min(wrongPageCount() - 1, wrongPage + 1)">下一页</BaseButton>
        </div>
      </div>

      <div class="flex gap-4 flex-wrap">
        <BaseButton type="primary" @click="exportCsv">导出 CSV（给老师）</BaseButton>
        <BaseButton type="info" @click="addWrongToBook">生词加入错词本</BaseButton>
        <BaseButton type="info" @click="restart">再选册子</BaseButton>
        <BaseButton type="info" @click="nav('/words')">返回词表</BaseButton>
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
</style>
