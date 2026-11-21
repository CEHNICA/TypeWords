import { reactive } from 'vue'
import type { Word } from '../types'
import { resolveWordLookup, stripWordPunctuation } from '../utils/wordLookup.ts'

export const wordLookupState = reactive({
  visible: false,
  loading: false,
  notFound: false,
  queryWord: '',
  data: null as Word | null,
  x: 0,
  y: 0,
})

/** 请求序号：连续点不同单词时，只有最后一次的结果能写进状态（防竞态串词）。 */
let requestSeq = 0

function updatePosition(target: HTMLElement) {
  const rect = target.getBoundingClientRect()
  wordLookupState.x = rect.left + rect.width / 2
  wordLookupState.y = rect.bottom + 8
}

async function fetchWordData(rawWord: string, seq: number) {
  const result = await resolveWordLookup(rawWord)
  // 期间用户又点了别的词 → 丢弃这次结果
  if (seq !== requestSeq) return

  if (!result.query) {
    wordLookupState.notFound = true
    wordLookupState.loading = false
    wordLookupState.data = null
    return
  }

  wordLookupState.queryWord = result.query
  wordLookupState.data = result.data
  wordLookupState.notFound = !result.data
  wordLookupState.loading = false
}

export function closeWordLookup() {
  wordLookupState.visible = false
  // 让在途请求的结果失效，关闭后再点别的词不会被旧结果覆盖
  requestSeq++
}

export async function lookupWord(e: MouseEvent, rawWord: string, playAudio?: (word: string) => void) {
  e.stopPropagation()
  const target = e.currentTarget as HTMLElement | null
  if (!target) return

  const seq = ++requestSeq
  updatePosition(target)
  wordLookupState.visible = true
  wordLookupState.loading = true
  wordLookupState.notFound = false
  wordLookupState.data = null

  const stripped = stripWordPunctuation(rawWord)
  // 先把词显示出来，别让浮层空着等接口
  if (stripped) wordLookupState.queryWord = stripped

  if (stripped) {
    playAudio?.(stripped)
  }

  await fetchWordData(rawWord, seq)
  if (seq === requestSeq && wordLookupState.visible && target.isConnected) {
    updatePosition(target)
  }
}

export function useWordLookup() {
  return {
    state: wordLookupState,
    lookupWord,
    close: closeWordLookup,
  }
}
