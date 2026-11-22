<script setup lang="ts">
import { onMounted, onUnmounted, toRaw } from 'vue'
import { BaseButton, BaseIcon, BasePage, Toast, VolumeIcon } from '@/base'
import { useRoute, useRouter } from 'vue-router'
import { useBaseStore } from '@/core/stores/base.ts'
import type { Dict, Question, TaskWords, Word } from '@/core/types/types.ts'
import { _getDictDataByUrl, getShufflePracticeWords, isIgnoreWord, shuffle, useNav } from '@/core/utils'
import type { ShufflePracticeSetting } from '@/core/utils'
import { useRuntimeStore } from '@/core/stores/runtime.ts'
import { usePlayBeep, usePlayCorrect, usePlayWordAudio } from '@/core/hooks/sound.ts'
import { useEvents } from '@/core/utils/eventBus'
import { useStartKeyboardEventListener } from '@/core/hooks/event.ts'
import { ShortcutKey, WordPracticeMode } from '@/core/types/enum'
import { useSettingStore } from '@/core/stores/setting.ts'
import { buildQuestion } from '@/core/utils/word-test'
import TranslationList from '@/components/word/TranslationList.vue'
import { useWordOptions } from '@/core/hooks/dict.ts'
import { closeWordCollectPicker, openWordCollectPicker } from '@/core/hooks/useWordCollectPicker.ts'

/** 一轮测试最多出多少道题（顺序测试 / 直接打开网址时兜底） */
const TEST_ROUND_SIZE = 20

const route = useRoute()
const router = useRouter()
const base = useBaseStore()
const runtimeStore = useRuntimeStore()
const settingStore = useSettingStore()
const playBeep = usePlayBeep()
const playCorrect = usePlayCorrect()
const playWordAudio = usePlayWordAudio()
const { isWordCollect, toggleWordCollect } = useWordOptions()

let loading = $ref(false)
let dict = $ref<Dict>()
let question = $ref<Question | null>(null)
let index = $ref(0)
let allWords: Word[] = []
let testWords: Word[] = []
/** 本轮是否已结束（结束后显示成绩小结） */
let finished = $ref(false)
/** 本轮答对的题数 */
let correctCount = $ref(0)
/** 本轮答错的词 */
let wrongWords = $ref<Word[]>([])
/** 本轮没作答直接跳过的题数（没答对，也进错词本） */
let skippedCount = $ref(0)
/** 本轮说明（顺序测试 / 随机测试） */
let roundTitle = $ref('')
/** 顺序测试的取词偏移，「再测一轮」时接着往后取 */
let roundOffset = $ref(0)
/** 随机测试时记住设置对话框给的「范围 + 数量」，「再测一轮」时重新抽 */
let shuffleSetting = $ref<ShufflePracticeSetting | null>(null)

const currentWord = $computed(() => question?.candidates[question.correctIndex]?.word)

function openCollectPicker(word: Word, event: MouseEvent) {
  openWordCollectPicker(word, event.currentTarget as HTMLElement, {
    excludeDictId: dict?.id,
  })
}

function buildCurrentQuestion() {
  const word = testWords[index]
  question = word ? buildQuestion(word, allWords) : null
}

/**
 * 按当前模式决定本轮考哪些词：
 * - 单词测试（顺序）：考「已经学过」的词，按学习顺序，一轮最多 TEST_ROUND_SIZE 道
 * - 随机单词测试：用设置对话框里选好的词；没有就直接从词典里随机抽
 */
function buildTestWords() {
  const mode = settingStore.wordPracticeMode
  const ignoreSet = base.getIgnoreWordsSet()
  const dictWords = toRaw(dict?.words ?? [])
  let picked: Word[] = []

  if (mode === WordPracticeMode.ReviewWordsTest) {
    const learned = Math.max(Math.min(Number(dict?.lastLearnIndex) || 0, dictWords.length), 0)
    if (learned <= 0) {
      // 一点进度都没有：退化成随机测试，别让用户点了没反应
      picked = shuffle(dictWords).slice(0, TEST_ROUND_SIZE)
      roundTitle = '随机测试（暂无学习进度）'
    } else {
      const start = Math.min(roundOffset, Math.max(learned - 1, 0))
      picked = dictWords
        .slice(start, start + TEST_ROUND_SIZE)
        .filter((w: Word) => !isIgnoreWord(ignoreSet, w.word))
      roundTitle = `按学习顺序测试 · 已学 ${learned} 个词`
    }
  } else {
    const fromDialog = runtimeStore.routeData.taskWords?.review
    const total = Number(runtimeStore.routeData.total) || 0
    const range = runtimeStore.routeData.shuffleRange
    if (total > 0 && range) {
      shuffleSetting = { total, range }
    }
    if (fromDialog && fromDialog.length) {
      picked = toRaw(fromDialog).slice()
    } else {
      picked = shuffle(dictWords.filter((w: Word) => !isIgnoreWord(ignoreSet, w.word))).slice(0, TEST_ROUND_SIZE)
    }
    roundTitle = '随机测试'
  }

  if (!picked.length) {
    picked = shuffle(dictWords).slice(0, TEST_ROUND_SIZE)
    roundTitle = '随机测试'
  }
  testWords = picked
}

async function init() {
  // route.params.id 是字符串，不转数字会找不到词典，被踢回 /words
  let dictId = Number(route.params.id)
  let d = base.word.bookList.find(v => v.id === dictId)
  if (!d) d = base.sdict
  if (!d?.id) return router.push('/words')
  if (!d.words.length && d.url) {
    loading = true
    try {
      d = await _getDictDataByUrl(d)
    } catch (e) {
      // 拉不到词典文件就按没有词处理
    }
    loading = false
  }
  dict = d
  if (!dict.words.length) {
    Toast.warning('没有单词可测试！')
    return router.push('/words')
  }
  allWords = toRaw(dict.words).slice()
  index = 0
  finished = false
  correctCount = 0
  wrongWords = []
  skippedCount = 0
  buildTestWords()
  if (!testWords.length) {
    Toast.warning('没有单词可测试！')
    return router.push('/words')
  }
  // 按需生成当前题，避免进入页面时连续遍历整本词典生成 100 道题。
  buildCurrentQuestion()

  if (settingStore.wordSound) playCurrentWord(false)

  Toast.info('按快捷键进行选择,例如按快捷键[' + aShortcutKey + ']选择A', { duration: 3000 })
}

let submitted = $ref(false)
let selectedIndex = $ref(-1)
/** 记一次错：进错词本 + 记进本轮错词表 */
function markWrong(word: Word) {
  if (!word) return
  const key = word.word.toLowerCase()
  if (!base.wrong.words.find((v: Word) => v.word.toLowerCase() === key)) {
    base.wrong.words.push(word)
    base.wrong.length = base.wrong.words.length
  }
  if (!wrongWords.find((v: Word) => v.word.toLowerCase() === key)) {
    wrongWords.push(word)
  }
}

function select(i: number) {
  const q = question
  if (!q || submitted) return
  selectedIndex = i
  submitted = true
  if (i === q.correctIndex) {
    correctCount++
    playCorrect()
  } else {
    playBeep()
    markWrong(q.candidates[q.correctIndex].word)
  }
}

const { nav } = useNav()

function playCurrentWord(handle = true) {
  if (!question) return
  const word = question.candidates[question.correctIndex]?.word.word
  if (word) playWordAudio(word, handle)
}

function next() {
  closeWordCollectPicker()
  // 没作答就跳下一题：算没答对，并进错词本，别让成绩小结自相矛盾
  if (!submitted && question) {
    skippedCount++
    markWrong(question.candidates[question.correctIndex].word)
  }
  submitted = false
  selectedIndex = -1
  if (index + 1 >= testWords.length) {
    finished = true
    return
  }
  index++
  buildCurrentQuestion()
  if (settingStore.wordSound) playCurrentWord(false)
}

/** 再测一轮：顺序测试接着往后取一批，随机测试重新抽一批 */
function restart() {
  closeWordCollectPicker()
  submitted = false
  selectedIndex = -1
  finished = false
  correctCount = 0
  wrongWords = []
  skippedCount = 0
  index = 0
  if (settingStore.wordPracticeMode === WordPracticeMode.ReviewWordsTest) {
    roundOffset = Math.min(roundOffset + TEST_ROUND_SIZE, Math.max(allWords.length - 1, 0))
  }
  buildTestWords()
  if (settingStore.wordPracticeMode !== WordPracticeMode.ReviewWordsTest && shuffleSetting) {
    // 随机测试：按原来的范围和数量重新抽一批，别老考同一批
    const res = getShufflePracticeWords(allWords, shuffleSetting, base.getIgnoreWordsSet())
    if (res.words.length) {
      testWords = res.words
    }
  }
  if (!testWords.length) {
    Toast.warning('没有更多单词可测了')
    return nav('/words')
  }
  buildCurrentQuestion()
  if (settingStore.wordSound) playCurrentWord(false)
}

function end() {
  closeWordCollectPicker()
  nav('/words')
}

useStartKeyboardEventListener()

useEvents([
  [ShortcutKey.ChooseA, () => select(0)],
  [ShortcutKey.ChooseB, () => select(1)],
  [ShortcutKey.ChooseC, () => select(2)],
  [ShortcutKey.ChooseD, () => select(3)],
  [ShortcutKey.WordTestingNext, () => next()],
  [ShortcutKey.PlayWordPronunciation, () => playCurrentWord()],
])

let aShortcutKey = settingStore.shortcutKeyMap[ShortcutKey.ChooseA]
let bShortcutKey = settingStore.shortcutKeyMap[ShortcutKey.ChooseB]
let cShortcutKey = settingStore.shortcutKeyMap[ShortcutKey.ChooseC]
let dShortcutKey = settingStore.shortcutKeyMap[ShortcutKey.ChooseD]

let nextShortcutKey = settingStore.shortcutKeyMap[ShortcutKey.WordTestingNext]

onMounted(init)
onUnmounted(closeWordCollectPicker)
</script>

<template>
  <BasePage>
    <div class="card flex flex-col text-xl">
      <div class="flex items-center justify-between">
        <div class="page-title">测试：{{ dict?.name }}</div>
        <div class="text-base">{{ finished ? '已结束' : `${index + 1} / ${testWords.length}` }}</div>
      </div>
      <div class="line my-2"></div>

      <!-- 成绩小结 -->
      <div v-if="finished" class="flex flex-col gap-4">
        <div class="text-3xl font-bold">本轮结束：答对 {{ correctCount }} / {{ testWords.length }}</div>
        <div class="text-base">{{ roundTitle }}</div>
        <div v-if="skippedCount" class="text-base">其中 {{ skippedCount }} 题没作答，直接跳过了。</div>
        <div v-if="wrongWords.length" class="flex flex-col gap-1">
          <div class="text-base">答错的词（已加入错词本）：</div>
          <div v-for="w in wrongWords" :key="w.word" class="text-base">{{ w.word }}</div>
        </div>
        <div v-else-if="correctCount === testWords.length" class="text-base">全对，一个都没错。</div>
        <div v-else class="text-base">没有错词记录。</div>
        <div class="mt-4 flex gap-4">
          <BaseButton type="primary" @click="restart">再测一轮</BaseButton>
          <BaseButton type="info" @click="end">返回词表</BaseButton>
        </div>
      </div>

      <div v-else-if="question" class="flex flex-col gap-4">
        <div class="text-base">{{ roundTitle }}</div>
        <div v-if="currentWord" class="text-4xl en-article-family flex flex-wrap items-center gap-2">
          <span>{{ currentWord.word }}</span>
          <VolumeIcon
            :title="`发音(${settingStore.shortcutKeyMap[ShortcutKey.PlayWordPronunciation]})`"
            :cb="playCurrentWord"
          />
          <BaseIcon
            :title="isWordCollect(currentWord) ? $t('uncollect') : $t('collect')"
            @click.stop="toggleWordCollect(currentWord)"
          >
            <IconFluentStar16Filled v-if="isWordCollect(currentWord)" />
            <IconFluentStar16Regular v-else />
          </BaseIcon>
          <BaseIcon :title="$t('collect_to_dict')" @click.stop="openCollectPicker(currentWord, $event)">
            <IconFluentStarAdd16Regular />
          </BaseIcon>
        </div>
        <div class="grid gap-6">
          <div
            v-for="(opt, i) in question.candidates"
            :key="i"
            class="option border rounded cursor-pointer"
            :class="{
              'text-green-600': submitted && i === question.correctIndex,
              'text-red-600': submitted && i === selectedIndex && i !== question.correctIndex,
            }"
            @click="submitted ? playWordAudio(opt.word.word) : select(i)"
          >
            <span class="">
              <span class="italic">{{ ['A', 'B', 'C', 'D'][i] }}</span>
              <span class="mx-2">[{{ [aShortcutKey, bShortcutKey, cShortcutKey, dShortcutKey][i] }}]</span>
              <TranslationList :word="opt.word" :show-full="false"></TranslationList>
            </span>
            <div
              class="flex items-center gap-2"
              :class="{ 'cursor-pointer': submitted }"
              v-opacity="submitted"
              @click.stop="submitted && playWordAudio(opt.word.word)"
            >
              <span>{{ opt.word.word }}</span>
              <VolumeIcon v-if="submitted" :title="'发音'" :cb="() => playWordAudio(opt.word.word)" />
              <template v-if="submitted">
                <BaseIcon
                  :title="isWordCollect(opt.word) ? $t('uncollect') : $t('collect')"
                  @click.stop="toggleWordCollect(opt.word)"
                >
                  <IconFluentStar16Filled v-if="isWordCollect(opt.word)" />
                  <IconFluentStar16Regular v-else />
                </BaseIcon>
                <BaseIcon :title="$t('collect_to_dict')" @click.stop="openCollectPicker(opt.word, $event)">
                  <IconFluentStarAdd16Regular />
                </BaseIcon>
              </template>
            </div>
          </div>
        </div>

        <div class="mt-6 flex">
          <BaseButton type="primary" @click="next">继续测试[{{ nextShortcutKey }}]</BaseButton>
          <BaseButton type="info" @click="end">结束</BaseButton>
        </div>
      </div>
    </div>
  </BasePage>
</template>

<style scoped>
.option:hover {
  background: var(--color-second);
}
.option {
  min-height: 80px;
}
</style>
