<script setup lang="ts">
/**
 * 点词查义浮层
 * ============
 * 之前：查词打云端 Supabase → 本地没配 apiBase 必然失败 → 弹 **有道整页 iframe**
 *       → 加载外网广告页，慢；而且浮层里塞了一堆按钮（有道/金山 tab + 新窗口打开）。
 *
 * 现在：查词先走**本地离线词库**（本地 dev server 索引 207 份词库 / 3.1 万词，0 延迟）：
 *   - 命中 → 直接显示释义卡片（词性释义 + 例句 + 短语 + 同反义），**不发任何外网请求**；
 *   - 未命中 → 只给两个外链词典按钮（有道 / 金山），**不再自动 iframe 加载外网页面**
 *     （用户要查自己点，弹窗瞬间就出来）。
 *
 * 发音仍走上游的有道 dictvoice（外网音频，失败回退浏览器 TTS）——那是音频资源，不影响释义速度。
 */
import { BaseIcon, Close, VolumeIcon } from '@/base'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useSettingStore } from '@/core/stores/setting.ts'
import { usePlayWordAudio } from '@/core/hooks/sound.ts'
import { closeWordLookup, wordLookupState } from '@/core/hooks/useWordLookup.ts'
import { openWordCollectPicker } from '@/core/hooks/useWordCollectPicker.ts'
import { getDefaultWord } from '@/core/types/func.ts'
import TranslationList from './TranslationList.vue'

const { t: $t } = useI18n()
const settingStore = useSettingStore()
const playWordAudio = usePlayWordAudio()
const popover = ref<HTMLElement | null>(null)

/** 外链词典（只在本地词库查不到时出现，点开走新标签页） */
const externalDictionaries = computed(() => {
  const word = encodeURIComponent(wordLookupState.queryWord)
  return [
    { label: '有道词典', url: `https://dict.youdao.com/result?word=${word}&lang=en` },
    { label: '金山词霸', url: `https://www.iciba.com/word?w=${word}` },
  ]
})

const style = computed(() => ({
  left: `${wordLookupState.x}px`,
  top: `${wordLookupState.y}px`,
}))

const collectTarget = computed(() => {
  if (wordLookupState.data) return wordLookupState.data
  if (wordLookupState.queryWord) return getDefaultWord({ word: wordLookupState.queryWord })
  return null
})

function openCollect(e: MouseEvent) {
  e.stopPropagation()
  const target = collectTarget.value
  if (target) openWordCollectPicker(target, e.currentTarget as HTMLElement)
}

function onDocumentClick(e: MouseEvent) {
  const popover = document.querySelector('.word-lookup-popover')
  if (popover && !popover.contains(e.target as Node)) {
    closeWordLookup()
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    closeWordLookup()
  }
}

function updatePopoverPosition() {
  if (!wordLookupState.visible || !popover.value) return
  const el = popover.value
  const rect = el.getBoundingClientRect()
  const padding = 8
  const left = Math.max(padding, Math.min(wordLookupState.x - rect.width / 2, window.innerWidth - rect.width - padding))
  let top = wordLookupState.y
  if (top + rect.height > window.innerHeight - padding) {
    top = wordLookupState.y - rect.height - 16
  }
  top = Math.max(padding, Math.min(top, window.innerHeight - rect.height - padding))
  el.style.left = `${left}px`
  el.style.top = `${top}px`
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', updatePopoverPosition)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', updatePopoverPosition)
})

watch(
  () => [wordLookupState.visible, wordLookupState.x, wordLookupState.y, wordLookupState.loading, wordLookupState.notFound],
  () => {
    if (!wordLookupState.visible) return
    nextTick(updatePopoverPosition)
  }
)
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="wordLookupState.visible"
        ref="popover"
        class="word-lookup-popover"
        :style="style"
        @click.stop
      >
        <Close class="close-btn" :title="$t('close')" @click="closeWordLookup" />

        <template v-if="wordLookupState.loading">
          <div class="flex items-center gap-2 flex-wrap pr-7">
            <span class="text-lg font-medium">{{ wordLookupState.queryWord }}</span>
            <span class="text-sm color-gray">查询中...</span>
          </div>
        </template>

        <!-- 本地词库命中：直接给释义，不弹任何外网页面 -->
        <template v-else-if="wordLookupState.data">
          <div class="flex items-center gap-1 flex-wrap pr-7">
            <span class="text-lg font-medium">{{ wordLookupState.data.word }}</span>
            <span v-if="settingStore.soundType === 'uk' && wordLookupState.data.phonetic0" class="text-sm color-gray">
              /{{ wordLookupState.data.phonetic0 }}/
            </span>
            <span v-if="settingStore.soundType === 'us' && wordLookupState.data.phonetic1" class="text-sm color-gray">
              /{{ wordLookupState.data.phonetic1 }}/
            </span>
            <VolumeIcon :cb="() => playWordAudio(wordLookupState.data!.word)" />
            <BaseIcon @click="openCollect" :title="$t('collect_to_dict')">
              <IconFluentStarAdd16Regular />
            </BaseIcon>
          </div>

          <TranslationList
            v-if="wordLookupState.data.trans?.length"
            class="mt-2"
            :word="wordLookupState.data"
            :show-full="true"
            :pos-space="false"
          />

          <!-- 命中的是原形（查 asks 命中 ask）→ 标一句原形，别让人以为是新词 -->
          <div v-if="wordLookupState.data.baseWord" class="wl-section">
            <div class="wl-section-title">原形</div>
            <div class="wl-sentence">
              <span class="wl-en">{{ wordLookupState.data.baseWord }}</span>
            </div>
          </div>

          <!-- 例句 -->
          <div v-if="wordLookupState.data.sentences?.length" class="wl-section">
            <div class="wl-section-title">例句</div>
            <div v-for="(s, i) in wordLookupState.data.sentences" :key="i" class="wl-sentence">
              <div class="wl-en">{{ s.c }}</div>
              <div v-if="s.cn" class="wl-cn">{{ s.cn }}</div>
            </div>
          </div>

          <!-- 短语 -->
          <div v-if="wordLookupState.data.phrases?.length" class="wl-section">
            <div class="wl-section-title">短语</div>
            <div v-for="(s, i) in wordLookupState.data.phrases" :key="i" class="wl-sentence">
              <div class="wl-en">{{ s.c }}</div>
              <div v-if="s.cn" class="wl-cn">{{ s.cn }}</div>
            </div>
          </div>

          <!-- 近义 / 同根 -->
          <div v-if="wordLookupState.data.synos?.length" class="wl-section">
            <div class="wl-section-title">近义词</div>
            <div v-for="(s, i) in wordLookupState.data.synos" :key="i" class="wl-sentence">
              <div class="wl-en">
                <span v-if="s.pos" class="wl-pos">{{ s.pos }}</span>
                {{ s.cn }}
              </div>
              <div v-if="s.ws?.length" class="wl-cn">{{ s.ws.join('、') }}</div>
            </div>
          </div>
        </template>

        <!-- 本地词库没收录：给外链词典，不自动加载外网页面 -->
        <template v-else-if="wordLookupState.notFound">
          <div class="flex items-center gap-2 flex-wrap pr-5">
            <span class="text-lg font-medium">{{ wordLookupState.queryWord }}</span>
            <VolumeIcon :simple="true" :cb="() => playWordAudio(wordLookupState.queryWord)" />
            <BaseIcon v-if="collectTarget" @click="openCollect" :title="$t('collect_to_dict')">
              <IconFluentStarAdd16Regular />
            </BaseIcon>
          </div>
          <div class="mt-1 mb-2 flex items-center gap-3 flex-wrap text-sm">
            <span class="color-gray">本地词典未收录</span>
            <a
              v-for="d in externalDictionaries"
              :key="d.url"
              :href="d.url"
              target="_blank"
              rel="noopener noreferrer"
              class="text-link"
            >
              {{ d.label }}
            </a>
          </div>
        </template>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped lang="scss">
.word-lookup-popover {
  position: fixed;
  z-index: 10000;
  box-sizing: border-box;
  width: max-content;
  max-width: min(22rem, calc(100vw - 16px));
  min-width: min(15rem, calc(100vw - 16px));
  max-height: calc(100dvh - 16px);
  overflow: auto;
  background: var(--color-tooltip-bg);
  border: 1px solid var(--color-item-border);
  border-radius: 0.5rem;
  padding: 0.75rem 1rem;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  pointer-events: auto;
}

.wl-section {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--color-item-border);
}

.wl-section-title {
  font-size: 0.75rem;
  opacity: 0.55;
  margin-bottom: 4px;
}

.wl-sentence {
  margin-top: 4px;
  font-size: 0.85rem;
  line-height: 1.5;
}

.wl-en {
  font-weight: 500;
}

.wl-cn {
  opacity: 0.65;
  font-size: 0.8rem;
}

.wl-pos {
  opacity: 0.6;
  margin-right: 4px;
}

.close-btn {
  position: absolute;
  top: 1.1rem;
  right: 1rem;
  z-index: 1;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
