<script setup lang="ts">
/**
 * 水平摸底测试（Placement Test）
 * =============================
 * 给孩子测「现在什么水平」：自适应出题 → 定位到具体年级 → 给词汇量估计和错词表。
 *
 * 两种测法：
 *  - adaptive 自适应定位：从最简单一级起步，答对升一级、答错退一级，撞墙即停。
 *    → 回答「我现在大概几年级水平」
 *  - sweep 逐级诊断：每个年级都单独抽题测一遍，一级一级往上。
 *    → 回答「哪个年级是断层」，出一张年表
 *
 * 核心逻辑：
 *  - 难度阶梯来自本地词库里的各年级教材词表（app/core/data/placement.ts）
 *  - 题型复用 buildQuestion：给英文词，选中文释义（干扰项同量级）
 */
import { onMounted } from 'vue'
import { BaseButton, BasePage, VolumeIcon } from '@/base'
import { useBaseStore } from '@/core/stores/base.ts'
import { _getDictDataByUrl, resourceWrap } from '@/core/utils'
import { DICT_LIST } from '@/core/config/env.ts'
import { buildQuestion } from '@/core/utils/word-test'
import {
  PLACEMENT_LADDERS,
  PLACEMENT_STEP_JUMP,
  type PlacementLadder,
} from '@/core/data/placement'
import type { Question, Word } from '@/core/types/types.ts'
import { usePlayBeep, usePlayCorrect, usePlayWordAudio } from '@/core/hooks/sound.ts'
import { useEvents } from '@/core/utils/eventBus'
import { useStartKeyboardEventListener } from '@/core/hooks/event.ts'
import { ShortcutKey } from '@/core/types/enum'
import { useSettingStore } from '@/core/stores/setting.ts'
import { useNav } from '@/core/utils'

interface LevelInfo {
  label: string
  words: Word[]
  /** 到本级为止累计的去重词数 */
  cumulative: number
}

interface PlacedRecord {
  word: Word
  chosen: Word
  level: number
  levelLabel: string
  correct: boolean
}

const base = useBaseStore()
const settingStore = useSettingStore()
const playBeep = usePlayBeep()
const playCorrect = usePlayCorrect()
const playWordAudio = usePlayWordAudio()
const { nav } = useNav()

let phase = $ref<'setup' | 'loading' | 'quiz' | 'report'>('setup')
let ladderKey = $ref('pep')
/** adaptive = 自适应定位（答对升一级）；sweep = 逐级诊断（每个年级都测） */
let mode = $ref<'adaptive' | 'sweep'>('adaptive')
let totalCount = $ref(20)
let perLevel = $ref(5)
let levels = $ref<LevelInfo[]>([])
let level = $ref(0)
let qIndex = $ref(0)
let question = $ref<Question | null>(null)
let submitted = $ref(false)
let selectedIndex = $ref(-1)
let records = $ref<PlacedRecord[]>([])
let usedWords = $ref<Set<string>>(new Set())
let loadingText = $ref('正在准备题目…')
let levelChanged = $ref('')
/** sweep 模式：当前这一级已经答了几题 */
let answeredInLevel = $ref(0)

const ladder = () => PLACEMENT_LADDERS.find(v => v.key === ladderKey) ?? PLACEMENT_LADDERS[0]
const optionLabels = ['A', 'B', 'C', 'D']
const isSweep = () => mode === 'sweep'

/** 小学词库的释义又长又全（ruler = 统治者，管理者；尺子，直尺；…），低年级读不完 */
function shortTrans(word: Word): string {
  const cn = word?.trans?.[0]?.cn || ''
  const first = cn.split(/[；;]/)[0].trim()
  const cut = first.length > 14 ? first.slice(0, 14) + '…' : first
  return cut || word?.word || ''
}

/**
 * 词条清洗：小学习题册的词条结构不完整（有的是短语、有的没有 relWords.rels），
 * 上游 buildQuestion / 词条详情页直接访问这些字段会崩，这里统一补齐。
 */
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

/** 载入整条阶梯的词（每级合并多本词表并去重） */
async function loadLadder() {
  phase = 'loading'
  loadingText = '正在下载词表…'
  const list = await fetch(resourceWrap(DICT_LIST.WORD.ALL)).then(r => r.json())
  const map = new Map<number, any>()
  for (const item of list) map.set(Number(item.id), item)

  const out: LevelInfo[] = []
  let cumulative = 0
  const steps = ladder().steps
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i]
    const words: Word[] = []
    const seen = new Set<string>()
    for (const id of step.ids) {
      const resource = map.get(id)
      if (!resource) continue
      loadingText = `正在加载：${resource.name}（${i + 1}/${steps.length}）`
      try {
        const dict = await _getDictDataByUrl(resource)
        for (const w of dict.words || []) {
          const key = (w.word || '').trim().toLowerCase()
          if (!key || seen.has(key)) continue
          seen.add(key)
          words.push(sanitizeWord(w))
        }
      } catch (e) {
        // 这一本拉不到就跳过，不影响整条阶梯
      }
    }
    cumulative += words.length
    out.push({ label: step.label, words, cumulative })
  }
  levels = out
  level = 0
  qIndex = 0
  records = []
  answeredInLevel = 0
  usedWords = new Set()
  phase = 'quiz'
  nextQuestion()
}

/** 出题：题干取当前级的词，干扰项取本级 + 邻级（保证同量级） */
function nextQuestion() {
  const cur = levels[level]
  if (!cur || !cur.words.length) {
    // 本级没词（词库缺失）→ 往后找有词的级别
    if (isSweep()) {
      let i = level + 1
      while (i < levels.length && !levels[i].words.length) i++
      if (i < levels.length) {
        level = i
        answeredInLevel = 0
        nextQuestion()
        return
      }
    }
    finish()
    return
  }
  let candidates = cur.words.filter(w => !usedWords.has(w.word.trim().toLowerCase()))
  if (!candidates.length) candidates = cur.words
  const word = candidates[Math.floor(Math.random() * candidates.length)]
  usedWords.add(word.word.trim().toLowerCase())

  const target = shortTrans(word)
  const neighbours = [cur.words, levels[level + 1]?.words || [], levels[level - 1]?.words || []].flat()
  const pool = neighbours.filter(w => {
    if (w.word.trim().toLowerCase() === word.word.trim().toLowerCase()) return false
    // 释义一样的当干扰项就是坑孩子，直接排掉
    return shortTrans(w) !== target
  })
  question = buildQuestion(word, pool.length >= 6 ? pool : cur.words)
  submitted = false
  selectedIndex = -1
  levelChanged = ''
  if (settingStore.wordSound) playWordAudio(word.word, false)
}

function select(i: number) {
  const q = question
  if (!q || submitted) return
  selectedIndex = i
  submitted = true
  const correctWord = q.candidates[q.correctIndex].word
  const correct = i === q.correctIndex
  records.push({
    word: correctWord,
    chosen: q.candidates[i].word,
    level,
    levelLabel: levels[level]?.label ?? '',
    correct,
  })
  if (correct) {
    playCorrect()
  } else {
    playBeep()
  }
}

/** 答完一题：调整难度，再出下一题 */
function advance() {
  const last = records[records.length - 1]
  if (!last) return
  qIndex++

  if (isSweep()) {
    // 逐级诊断：本级答满就升到下一级，不回头
    answeredInLevel++
    if (answeredInLevel >= perLevel) {
      answeredInLevel = 0
      let next = level + 1
      while (next < levels.length && !levels[next].words.length) next++
      if (next >= levels.length) return finish()
      level = next
      levelChanged = `进入 ${levels[level].label}`
    }
    nextQuestion()
    return
  }

  const prev = level
  if (last.correct) {
    level = Math.min(level + PLACEMENT_STEP_JUMP, levels.length - 1)
  } else {
    level = Math.max(level - PLACEMENT_STEP_JUMP, 0)
  }
  if (level > prev) levelChanged = `难度提升 → ${levels[level].label}`
  else if (level < prev) levelChanged = `这道有点难，退回 ${levels[level].label}`
  else if (level === levels.length - 1) levelChanged = '已经是最高难度了'

  const wrongStreak = trailingStreak(false)
  const rightStreak = trailingStreak(true)
  if (qIndex >= totalCount) return finish()
  // 连续 2 题答错且已经答了不少 → 撞墙了，收工
  if (wrongStreak >= 2 && qIndex >= 5) return finish()
  // 已经在最高难度还连对 → 封顶，收工
  if (level === levels.length - 1 && rightStreak >= 3) return finish()
  nextQuestion()
}

/** 末尾连续对/错的题数 */
function trailingStreak(wantCorrect: boolean): number {
  let n = 0
  for (let i = records.length - 1; i >= 0; i--) {
    if (records[i].correct === wantCorrect) n++
    else break
  }
  return n
}

function finish() {
  phase = 'report'
}

// ------------------------------------------------------------------ 报告计算
function report() {
  const list = records
  const total = list.length
  const right = list.filter(r => r.correct).length
  // 定位到「最高答对过」的级别
  let maxLevel = 0
  for (const r of list) {
    if (r.correct) maxLevel = Math.max(maxLevel, r.level)
  }
  const atLevel = list.filter(r => r.level === maxLevel)
  const atLevelRight = atLevel.filter(r => r.correct).length
  const ratio = atLevel.length ? atLevelRight / atLevel.length : (total ? right / total : 0)
  const before = maxLevel > 0 ? levels[maxLevel - 1]?.cumulative ?? 0 : 0
  const levelWords = levels[maxLevel]?.words.length ?? 0
  const estimate = Math.round(before + levelWords * ratio)
  const single = levels.length <= 1
  if (!total) {
    return {
      total: 0,
      right: 0,
      rate: 0,
      maxLevel: 0,
      levelLabel: '',
      estimate: 0,
      single,
      top: '没有作答记录',
      advice: '一题都没做，重新测一次吧。',
    }
  }
  return {
    total,
    right,
    rate: total ? Math.round((right / total) * 100) : 0,
    maxLevel,
    levelLabel: levels[maxLevel]?.label ?? '',
    estimate,
    single,
    top: single ? '综合词表水平' : `约 ${levels[maxLevel]?.label ?? ''} 水平`,
    advice: single
      ? '这套词表不分年级，按掌握比例估的词汇量。可以直接进 CET-4 或高考 3500 词库练。'
      : maxLevel >= levels.length - 1
        ? `可以开始学初中词汇了（下一站：${ladder().name} 初中词表）。`
        : `建议从《${ladder().name} ${levels[maxLevel]?.label}》接着学。`,
  }
}

/** 逐级诊断的年表：每个年级一行，掌握率 + 断层判断 */
function sweepReport() {
  const rows = levels.map((lv, i) => {
    const rs = records.filter(r => r.level === i)
    const right = rs.filter(r => r.correct).length
    const rate = rs.length ? Math.round((right / rs.length) * 100) : 0
    return { index: i, label: lv.label, total: rs.length, right, rate, words: lv.words.length }
  })
  const tested = rows.filter(r => r.total > 0)
  const total = records.length
  const right = records.filter(r => r.correct).length
  // 第一个掌握率 < 60% 的年级 = 能力断层（水平上限）
  const weak = tested.find(r => r.rate < 60)
  // 估算词汇量：按「水平上限年级」折算，口径跟自适应模式一致
  // （不能把各级词表词数直接求和——小学各册之间大量重复词会被重复计入，虚高）
  let estimate = 0
  if (weak) {
    const before = weak.index > 0 ? levels[weak.index - 1]?.cumulative ?? 0 : 0
    const own = levels[weak.index]?.words.length ?? 0
    estimate = before + Math.round(own * (weak.rate / 100))
  } else if (total) {
    // 全年级都过了 → 整条阶梯的累计词量
    estimate = levels[levels.length - 1]?.cumulative ?? 0
  }
  const top = weak
    ? `水平到《${ladder().name} ${weak.label}》为止`
    : total
      ? '各年级都过了，很扎实'
      : '没有作答记录'
  const advice = weak
    ? `${weak.label} 开始吃力（掌握率 ${weak.rate}%）。先把这一册啃下来，再往上走。`
    : total
      ? `这一套《${ladder().name}》全年级都掌握得不错，可以直接进初中词表。`
      : '一题都没做，重新测一次吧。'
  return { rows, tested, weak, estimate, total, right, top, advice }
}

/** 把本轮答错的词加进错词本 */
function addWrongToBook() {
  let n = 0
  for (const r of records) {
    if (r.correct) continue
    const key = r.word.word.trim().toLowerCase()
    if (base.wrong.words.find(v => v.word.trim().toLowerCase() === key)) continue
    base.wrong.words.push(r.word)
    n++
  }
  base.wrong.length = base.wrong.words.length
  return n
}

/** 导出 CSV 给老师 */
function exportCsv() {
  const rows: string[][] = [['单词', '音标', '释义', '级别', '结果']]
  for (const r of records) {
    rows.push([
      r.word.word,
      r.word.phonetic1 || r.word.phonetic0 || '',
      shortTrans(r.word),
      r.levelLabel,
      r.correct ? '答对' : '答错',
    ])
  }
  const csv =
    '\uFEFF' +
    rows
      .map(row => row.map(c => `"${String(c).replace(/"/g, '""')}"`).join(','))
      .join('\r\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `摸底测试_${new Date().toISOString().slice(0, 10)}.csv`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

function restart() {
  phase = 'setup'
  records = []
  levels = []
}

useStartKeyboardEventListener()
useEvents([
  [ShortcutKey.ChooseA, () => select(0)],
  [ShortcutKey.ChooseB, () => select(1)],
  [ShortcutKey.ChooseC, () => select(2)],
  [ShortcutKey.ChooseD, () => select(3)],
  [ShortcutKey.WordTestingNext, () => {
    // 没作答不许跳过：这题必须记一笔，否则摸底结果会缺一题
    if (submitted) advance()
  }],
])

onMounted(() => {
  ladderKey = PLACEMENT_LADDERS[0].key
})
</script>

<template>
  <BasePage>
    <!-- ============================ 1. 设置 ============================ -->
    <div v-if="phase === 'setup'" class="card flex flex-col gap-5">
      <div>
        <div class="page-title">水平摸底测试</div>
        <div class="text-base color-reverse-black mt-2">
          测一下现在的水平：自适应出题定位到具体年级；也可以每个年级都测一遍，看哪一册是断层。
          结束给「年级定位 + 词汇量估计 + 错词表」。
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="title">测法</div>
        <div class="flex gap-3 flex-wrap">
          <BaseButton
            :type="mode === 'adaptive' ? 'primary' : 'info'"
            @click="mode = 'adaptive'"
          >
            自适应定位
          </BaseButton>
          <BaseButton
            :type="mode === 'sweep' ? 'primary' : 'info'"
            @click="mode = 'sweep'"
          >
            逐级诊断（每个年级都测）
          </BaseButton>
        </div>
        <div class="text-sm color-reverse-black">
          {{
            mode === 'adaptive'
              ? '从最简单的一级开始，答对升一级、答错退一级，撞上不会的那一级就停。回答「我大概几年级水平」。'
              : '从最低年级开始一级一级往上，每一级都抽固定题量测一遍，最后出一张年表。回答「哪一册开始吃力」。'
          }}
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="title">选教材</div>
        <div class="flex gap-3 flex-wrap">
          <BaseButton
            v-for="l in PLACEMENT_LADDERS"
            :key="l.key"
            :type="ladderKey === l.key ? 'primary' : 'info'"
            @click="ladderKey = l.key"
          >
            {{ l.name }}
          </BaseButton>
        </div>
        <div class="text-sm color-reverse-black">{{ ladder().desc }}</div>
      </div>

      <div v-if="mode === 'adaptive'" class="flex flex-col gap-2">
        <div class="title">题量</div>
        <div class="flex gap-3 flex-wrap">
          <BaseButton
            v-for="n in [10, 20, 30]"
            :key="n"
            :type="totalCount === n ? 'primary' : 'info'"
            @click="totalCount = n"
          >
            {{ n }} 题
          </BaseButton>
        </div>
        <div class="text-sm color-reverse-black">题量越多定位越准，10 题只够看个大概。</div>
      </div>

      <div v-else class="flex flex-col gap-2">
        <div class="title">每个年级出几题</div>
        <div class="flex gap-3 flex-wrap">
          <BaseButton
            v-for="n in [3, 5, 8, 10]"
            :key="n"
            :type="perLevel === n ? 'primary' : 'info'"
            @click="perLevel = n"
          >
            {{ n }} 题/级
          </BaseButton>
        </div>
        <div class="text-sm color-reverse-black">
          共 {{ levels.length || PLACEMENT_LADDERS.find(v => v.key === ladderKey)?.steps.length }} 个年级，
          最多 {{ (PLACEMENT_LADDERS.find(v => v.key === ladderKey)?.steps.length || 0) * perLevel }} 题。
          每级 5 题左右比较准，3 题只能看个大概。
        </div>
      </div>

      <div class="flex gap-4">
        <BaseButton type="primary" @click="loadLadder">开始摸底</BaseButton>
        <BaseButton type="info" @click="nav('/book-review')">整本复习（全书逐词）</BaseButton>
        <BaseButton type="info" @click="nav('/words')">返回</BaseButton>
      </div>
    </div>

    <!-- ============================ 2. 载入 ============================ -->
    <div v-else-if="phase === 'loading'" class="card flex flex-col gap-3">
      <div class="page-title">正在准备题目…</div>
      <div class="text-base color-reverse-black">{{ loadingText }}</div>
    </div>

    <!-- ============================ 3. 答题 ============================ -->
    <div v-else-if="phase === 'quiz'" class="card flex flex-col gap-4">
      <div class="flex items-center justify-between">
        <div class="page-title">{{ isSweep() ? '逐级诊断' : '水平摸底' }}</div>
        <div v-if="isSweep()" class="text-base">
          第 {{ level + 1 }} / {{ levels.length }} 个年级
        </div>
        <div v-else class="text-base">第 {{ qIndex + 1 }} / {{ totalCount }} 题</div>
      </div>

      <div class="flex items-center gap-3 flex-wrap">
        <span class="text-sm px-2 py-1 rounded bg-color-second">当前难度：{{ levels[level]?.label }}</span>
        <span v-if="isSweep()" class="text-sm px-2 py-1 rounded bg-color-second">
          本级第 {{ answeredInLevel + 1 }} / {{ perLevel }} 题
        </span>
        <span v-else class="text-sm px-2 py-1 rounded bg-color-second">
          已答对 {{ records.filter(r => r.correct).length }} 题
        </span>
        <span v-if="levelChanged" class="text-sm color-link">{{ levelChanged }}</span>
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

        <div class="mt-2 flex gap-4">
          <BaseButton v-if="submitted" type="primary" @click="advance">
            下一题[{{ settingStore.shortcutKeyMap[ShortcutKey.WordTestingNext] }}]
          </BaseButton>
          <BaseButton type="info" @click="finish">结束，看结果</BaseButton>
        </div>
      </div>
    </div>

    <!-- ============================ 4. 报告 ============================ -->
    <div v-else class="card flex flex-col gap-5">
      <div>
        <div class="page-title">{{ isSweep() ? '逐级诊断结果' : '摸底结果' }}</div>
        <div class="text-3xl font-bold mt-2">{{ isSweep() ? sweepReport().top : report().top }}</div>
        <div class="text-base mt-1">
          答对 {{ isSweep() ? sweepReport().right : report().right }} /
          {{ isSweep() ? sweepReport().total : report().total }} 题
          （正确率 {{ isSweep() ? sweepReport().total ? Math.round((sweepReport().right / sweepReport().total) * 100) : 0 : report().rate }}%）
        </div>
      </div>

      <div class="grid md:grid-cols-3 gap-4">
        <div class="stat2">
          <div class="num">{{ isSweep() ? sweepReport().estimate : report().estimate }}</div>
          <div class="txt">估算词汇量（个）</div>
        </div>
        <div class="stat2">
          <div class="num">{{ isSweep() ? (sweepReport().weak?.label || '无断层') : report().levelLabel }}</div>
          <div class="txt">{{ isSweep() ? '断层在这一级' : '定位到这一级' }}</div>
        </div>
        <div class="stat2">
          <div class="num">{{ records.filter(r => !r.correct).length }}</div>
          <div class="txt">没答对的词</div>
        </div>
      </div>

      <div class="text-base">{{ isSweep() ? sweepReport().advice : report().advice }}</div>

      <!-- 逐级诊断的年表 -->
      <div v-if="isSweep()" class="flex flex-col gap-2">
        <div class="title">各年级掌握情况</div>
        <div class="flex flex-col gap-2">
          <div
            v-for="r in sweepReport().rows"
            :key="r.index"
            class="sweep-row flex items-center gap-3"
          >
            <div class="w-28 text-base">{{ r.label }}</div>
            <div class="bar-track flex-1">
              <div
                class="bar-fill"
                :class="r.rate >= 80 ? 'bg-green-500' : r.rate >= 60 ? 'bg-yellow-500' : 'bg-red-500'"
                :style="{ width: r.rate + '%' }"
              />
            </div>
            <div class="w-24 text-sm text-right">
              {{ r.right }}/{{ r.total }} · {{ r.rate }}%
            </div>
          </div>
        </div>
        <div class="text-sm color-reverse-black">
          绿 = 掌握度 80% 以上，黄 = 60~80%，红 = 60% 以下（红色那级就是断层）。
        </div>
      </div>

      <div class="flex flex-col gap-2">
        <div class="title">答题明细</div>
        <div class="flex flex-col gap-1 max-h-80 overflow-auto">
          <div
            v-for="(r, i) in records"
            :key="i"
            class="text-base flex items-center gap-3"
            :class="r.correct ? 'text-green-600' : 'text-red-600'"
          >
            <span class="w-6">{{ i + 1 }}</span>
            <span class="w-40 truncate">{{ r.word.word }}</span>
            <span class="truncate">{{ shortTrans(r.word) }}</span>
            <span class="text-sm color-reverse-black">{{ r.levelLabel }}</span>
          </div>
        </div>
      </div>

      <div class="flex gap-4 flex-wrap">
        <BaseButton type="primary" @click="exportCsv">导出 CSV（给老师）</BaseButton>
        <BaseButton type="info" @click="addWrongToBook">错词加入错词本</BaseButton>
        <BaseButton type="info" @click="restart">再测一次</BaseButton>
        <BaseButton type="info" @click="nav('/words')">返回词表</BaseButton>
      </div>
    </div>
  </BasePage>
</template>

<style scoped>
.option {
  min-height: 56px;
}
.option:hover {
  background: var(--color-second);
}
.bar-track {
  height: 14px;
  border-radius: 7px;
  background: var(--color-second);
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 7px;
  transition: width 0.2s ease;
}
</style>
