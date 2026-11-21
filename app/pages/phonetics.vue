<script setup lang="ts">
import { BasePage } from '@/base'
import { PHONEMES, PHONETIC_CATEGORIES, PHONEME_FILTERS, type Phoneme } from '@/core/data/phonetics.ts'

type AudioStatus = 'idle' | 'loading' | 'playing' | 'error'
type FilterId = (typeof PHONEME_FILTERS)[number]['id']

let title = '英语音标学习 - TypeWords'
useSeoMeta({
  title,
  description: '学习英式英语 48 个音标，查看发音要领、口型提示和常见例词，并逐个播放标准音标发音。',
  ogTitle: title,
  ogDescription: '学习英式英语 48 个音标，查看发音要领、口型提示和常见例词。',
})

// 当前筛选：all / vowel / consonant
let filter = $ref<FilterId>('all')
// 显示方式：compact 紧凑 / standard 宽松
let density = $ref<'compact' | 'standard'>('compact')
// 当前展开的音标详情
let current = $ref<Phoneme | null>(null)
// 随机练习模式
let randomMode = $ref(false)
let shuffled = $ref<Phoneme[]>([])
// 详情弹窗里的视频是否加载失败
let videoFailed = $ref(false)

// 音频播放状态
let activeId = $ref<string | null>(null)
let audioStatus = $ref<AudioStatus>('idle')
let errorId = $ref<string | null>(null)

let audioEl: HTMLAudioElement | null = null

const visibleCategories = $computed(() => {
  if (filter === 'all') return PHONETIC_CATEGORIES
  return PHONETIC_CATEGORIES.filter(c => c.family === filter)
})

function phonemesOf(categoryId: string) {
  return PHONEMES.filter(p => p.category === categoryId)
}

function stopAudio() {
  if (audioEl) {
    audioEl.pause()
    audioEl.onplaying = null
    audioEl.onended = null
    audioEl.onerror = null
    audioEl = null
  }
  activeId = null
  audioStatus = 'idle'
}

function playPhoneme(p: Phoneme) {
  if (activeId === p.id && audioStatus === 'playing') {
    stopAudio()
    return
  }
  stopAudio()
  activeId = p.id
  audioStatus = 'loading'
  const el = new Audio(p.audioSrc)
  audioEl = el
  el.onplaying = () => {
    if (audioEl === el) audioStatus = 'playing'
  }
  el.onended = () => {
    if (audioEl === el) {
      activeId = null
      audioStatus = 'idle'
    }
  }
  el.onerror = () => {
    if (audioEl === el) {
      audioStatus = 'error'
      errorId = p.id
    }
  }
  try {
    el.play()?.catch(() => {
      if (audioEl === el) {
        audioStatus = 'error'
        errorId = p.id
      }
    })
  } catch {
    audioStatus = 'error'
    errorId = p.id
  }
}

function openDetail(p: Phoneme) {
  current = p
  videoFailed = false
}

function closeDetail() {
  current = null
  videoFailed = false
}

function replay() {
  if (current) playPhoneme(current)
}

function shuffle(list: Phoneme[]) {
  const arr = [...list]
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
  }
  return arr
}

function enterRandomMode() {
  shuffled = shuffle(PHONEMES)
  randomMode = true
}

function exitRandomMode() {
  randomMode = false
  shuffled = []
}

function playStateLabel(p: Phoneme) {
  if (errorId === p.id) return '音频暂不可用'
  if (activeId === p.id) {
    if (audioStatus === 'loading') return '正在加载'
    if (audioStatus === 'playing') return '正在播放'
  }
  return '点击播放'
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && current) closeDetail()
}

onMounted(() => window.addEventListener('keydown', onKeydown))

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  stopAudio()
})
</script>

<template>
  <BasePage>
    <div class="phonetics-page" :class="density" aria-labelledby="phonetics-title">
      <section class="hero-card">
        <div class="hero-icon" aria-hidden="true">
          <IconBxVolumeFull />
        </div>
        <div class="hero-copy">
          <h1 id="phonetics-title">英语音标</h1>
          <p>20 个元音 + 28 个辅音，点击音标听标准发音，点「详情」看口型演示、发音要领和例词。</p>
        </div>
        <div class="hero-count" aria-label="共 48 个音标">
          <strong>48</strong>
          <span>个音标</span>
        </div>
      </section>

      <div class="line my-2"></div>

      <section class="toolbar-card">
        <div class="toolbar-group">
          <span class="toolbar-label" id="filter-label">音标类型</span>
          <div class="button-list" role="group" aria-labelledby="filter-label">
            <button
              v-for="f in PHONEME_FILTERS"
              :key="f.id"
              type="button"
              class="seg-btn"
              :class="{ active: filter === f.id }"
              :aria-pressed="filter === f.id"
              @click="filter = f.id"
            >
              <span>{{ f.label }}</span>
              <span class="filter-count">{{ f.count }}</span>
            </button>
          </div>
        </div>
        <div class="toolbar-group mode-group">
          <span class="toolbar-label" id="density-label">显示方式</span>
          <div class="button-list" role="group" aria-labelledby="density-label">
            <button
              type="button"
              class="seg-btn"
              :class="{ active: density === 'compact' }"
              :aria-pressed="density === 'compact'"
              @click="density = 'compact'"
            >
              紧凑
            </button>
            <button
              type="button"
              class="seg-btn"
              :class="{ active: density === 'standard' }"
              :aria-pressed="density === 'standard'"
              @click="density = 'standard'"
            >
              宽松
            </button>
          </div>
        </div>
        <div class="toolbar-group random-group">
          <span class="toolbar-label" id="random-label">练习模式</span>
          <div class="button-list" role="group" aria-labelledby="random-label">
            <button type="button" class="seg-btn" :class="{ active: randomMode }" :aria-pressed="randomMode" @click="enterRandomMode">
              <IconFluentArrowShuffle16Regular aria-hidden="true" />
              <span>随机</span>
            </button>
          </div>
        </div>
      </section>

      <div v-if="randomMode" class="random-banner">
        <div class="random-banner-text">
          <IconFluentArrowShuffle16Regular aria-hidden="true" />
          <span>随机练习：已打乱全部 {{ shuffled.length }} 个音标，点击任意音标即可听发音。</span>
        </div>
        <button type="button" class="seg-btn active" @click="exitRandomMode">返回正常模式</button>
      </div>

      <div class="phonetics-browser" :class="{ 'random-mode': randomMode }">
        <div v-if="randomMode" class="phonetics-content random-content">
          <div class="phoneme-grid">
            <article
              v-for="p in shuffled"
              :key="p.id"
              class="phoneme-card"
              :class="{ active: activeId === p.id && audioStatus !== 'error', error: errorId === p.id }"
            >
              <button
                type="button"
                class="phoneme-play-area"
                :aria-label="`播放音标 ${p.symbol}`"
                @click="playPhoneme(p)"
              >
                <span class="phoneme-symbol">{{ p.symbol }}</span>
              </button>
              <button type="button" class="detail-control" :aria-label="`查看音标 ${p.symbol} 的发音详情`" @click="openDetail(p)">
                详情
              </button>
            </article>
          </div>
        </div>

        <div v-else class="phonetics-content">
          <section
            v-for="c in visibleCategories"
            :id="`phoneme-group-${c.id}`"
            :key="c.id"
            class="phoneme-section"
            :aria-labelledby="`phoneme-title-${c.id}`"
          >
            <div class="section-heading">
              <div>
                <h2 :id="`phoneme-title-${c.id}`">{{ c.title }}</h2>
                <p>{{ c.description }}</p>
              </div>
              <span>{{ phonemesOf(c.id).length }} 个</span>
            </div>
            <div class="phoneme-grid">
              <article
                v-for="p in phonemesOf(c.id)"
                :key="p.id"
                class="phoneme-card"
                :class="{ active: activeId === p.id && audioStatus !== 'error', error: errorId === p.id }"
              >
                <button
                  type="button"
                  class="phoneme-play-area"
                  :aria-label="`播放音标 ${p.symbol}`"
                  @click="playPhoneme(p)"
                >
                  <span class="phoneme-symbol">{{ p.symbol }}</span>
                </button>
                <button type="button" class="detail-control" :aria-label="`查看音标 ${p.symbol} 的发音详情`" @click="openDetail(p)">
                  详情
                </button>
              </article>
            </div>
          </section>
        </div>
      </div>

      <!-- 音标详情 -->
      <Teleport to="body">
        <div v-if="current" class="phonetics-modal" role="dialog" aria-modal="true" :aria-label="`音标 ${current.symbol} 详情`" @click.self="closeDetail">
          <div class="phonetics-modal-mask"></div>
          <div class="phonetics-modal-body">
            <button type="button" class="phonetics-modal-close" aria-label="关闭" @click="closeDetail">
              <IconFluentDismiss20Regular aria-hidden="true" />
            </button>
            <div class="phoneme-detail">
              <div class="detail-hero">
                <div class="detail-symbol">{{ current.symbol }}</div>
                <button
                  type="button"
                  class="replay-control"
                  :class="{ error: errorId === current.id }"
                  :aria-label="`播放音标 ${current.symbol}`"
                  @click="replay"
                >
                  <IconBxVolumeFull aria-hidden="true" />
                  <span>{{ playStateLabel(current) }}</span>
                </button>
              </div>

              <div class="detail-section video-section">
                <h3>发音演示</h3>
                <video
                  v-if="!videoFailed"
                  class="phoneme-video"
                  controls
                  playsinline
                  preload="metadata"
                  :src="current.videoSrc"
                  :aria-label="`${current.symbol} 发音演示视频`"
                  @error="videoFailed = true"
                ></video>
                <div v-else class="video-unavailable">
                  <IconFluentEyeOff16Regular aria-hidden="true" />
                  <span>演示视频暂不可用，可先听音频发音</span>
                </div>
              </div>

              <div class="detail-section">
                <h3>发音要领</h3>
                <ul class="tip-list">
                  <li v-for="(tip, i) in current.pronunciationTips" :key="i">{{ tip }}</li>
                </ul>
              </div>

              <div class="detail-section">
                <div class="confusion-note">
                  <IconFluentQuestionCircle20Regular aria-hidden="true" />
                  <p>{{ current.confusionNote }}</p>
                </div>
              </div>

              <div class="detail-section">
                <h3>例词</h3>
                <ul class="example-list">
                  <li v-for="(ex, i) in current.examples" :key="i">
                    <span class="example-word">{{ ex.word }}</span>
                    <span class="example-phonetic">{{ ex.phonetic }}</span>
                    <span class="example-meaning">{{ ex.meaning }}</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </BasePage>
</template>

<style scoped lang="scss">
@use '@/assets/css/phonetics.scss';
</style>
