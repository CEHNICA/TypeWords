<script setup lang="ts">
/**
 * 本地导入文章
 * ============
 * 上游 master 的文章链路有三处断点，导致「用户自己导入文章」根本走不通：
 *   1. 文章页「创建个人书籍」跳 /book/new → 该路由实际匹配 [id]='new'，
 *      useGetDict 找不到这本书 → router.push('/articles')，点了等于没点；
 *   2. 上游没有「新增文章」的 UI → 就算建成空书，也进不去任何一篇；
 *   3. useGetDict.loadDict() 只在「需要远程 fetch」分支里赋 runtimeStore.editDict，
 *      本地导入的书自带 articles（不需要 fetch）→ editDict 不被赋值 → 详情页是空书。
 *
 * 这里把整条补齐：选本地 txt/md → 复用上游分句器 → 生成 Article（含 sections）
 * → 建一本 custom 书塞进书架 → 落盘 → 首页立刻能点「开始学习」。
 *
 * 复用上游而不是手搓的理由：
 *   - splitEnArticle2 处理了缩写(Mr./U.S.)、数字、千分位、直引号，粘在一起的一整段也能切；
 *   - splitCNArticle2 走 Intl.Segmenter('zh-CN')，中文断句才对；
 *   - genArticleSectionData 生成 sections（练习页逐句高亮/打点全靠它）。
 *
 * 界面结构（2026-11-21 重做，之前那版样式乱：标签左右混排、按钮三种样式、说明臃肿）：
 *   - Header / Body / Footer 三段式，8px 栅格；
 *   - 原文、译文两栏用同一个 CSS Grid，「选择文件」两行严格纵向对齐；
 *   - 同级操作统一成同款描边按钮，主按钮用品牌蓝 #409eff；
 *   - 选中的文件名做成胶囊 tag 贴在标签旁边，不再单起一行状态栏；
 *   - 「自建翻译服务」是低频高级项，默认折叠收起。
 */
import { BaseButton, BaseInput, Textarea, Toast } from '@/base'
import { genArticleSectionData, splitCNArticle2, splitEnArticle2 } from '@/core/hooks/article.ts'
import { useDataSyncPersistence } from '@/core/composables/useDataSyncPersistence.ts'
import { useBaseStore } from '@/core/stores/base.ts'
import { getDefaultArticle, getDefaultDict } from '@/core/types'
import { DictType } from '@/core/types/enum.ts'
import { defineAsyncComponent, ref } from 'vue'

const Dialog = defineAsyncComponent(() => import('@/base/dialog/Dialog.vue'))

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  imported: [dictId: string]
}>()

const base = useBaseStore()
const dataSync = useDataSyncPersistence()

/** 自建翻译服务地址（LibreTranslate / Argos Translate），存 localStorage；空 = 用谷歌 */
const TRANSLATE_ENDPOINT_KEY = 'tw-translate-endpoint'

let bookName = ref('')
let articleTitle = ref('')
let articleTitleTranslate = ref('')
let rawText = ref('')
let rawTranslate = ref('')
let textFileName = ref('')
let translateFileName = ref('')
let saving = ref(false)
let translating = ref(false)
let translateEndpoint = ref(localStorage.getItem(TRANSLATE_ENDPOINT_KEY) || '')

/** 填了自建翻译服务地址就存下来（下次导入还在） */
function onEndpointChange(v: string) {
  translateEndpoint.value = v
  const val = v.trim()
  if (val) localStorage.setItem(TRANSLATE_ENDPOINT_KEY, val)
  else localStorage.removeItem(TRANSLATE_ENDPOINT_KEY)
}

/** 原文 → 句子列表（与 submit() 用的是同一套切分，保证翻译和入库句子一一对应） */
function toSentences(text: string): string[] {
  return splitEnArticle2(text)
    .split('\n\n')
    .flatMap((p) => p.split('\n'))
    .map((s) => s.trim())
    .filter(Boolean)
}

/**
 * 翻译源
 * ======
 * 默认走**谷歌翻译的公开 gtx 接口**（浏览器直连，实测 localhost 页面 fetch 返回 200 且 CORS 放行；
 * 命令行直连这个域名会被 429，所以别想在终端里调）。
 *
 * 填了「自建翻译服务地址」就改走**开源自建**的 LibreTranslate / Argos Translate HTTP 接口：
 *   - LibreTranslate: docker run -p 5000:5000 libretranslate/libretranslate
 *   - Argos Translate: 它是 Python 库，一般包一层 HTTP 服务
 * 两者都是 POST /translate {q, source, target, format:'text'} → {translatedText}
 */
async function translateOne(sentence: string): Promise<string> {
  const custom = (localStorage.getItem(TRANSLATE_ENDPOINT_KEY) || '').trim()
  if (custom) {
    const r = await fetch(custom.replace(/\/+$/, '') + '/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q: sentence, source: 'en', target: 'zh', format: 'text' })
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const j = await r.json()
    const t = (j?.translatedText || j?.translation || '').trim()
    if (!t) throw new Error('返回格式不对')
    return t
  }

  const url =
    'https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=' +
    encodeURIComponent(sentence)
  const r = await fetch(url)
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  const j = await r.json()
  const seg = j?.[0]
  if (!Array.isArray(seg)) throw new Error('返回格式不对')
  const text = seg.map((x: any) => (Array.isArray(x) ? x[0] : '')).join('').trim()
  return text || sentence
}

/** 逐句翻译原文 → 填进译文框（一句一行，和原文句子一一对应） */
async function translateToChinese() {
  if (translating.value) return
  const text = rawText.value.trim()
  if (!text) return Toast.warning('先把原文填上！')

  translating.value = true
  try {
    const sentences = toSentences(text)
    const translated: string[] = []
    // 串行 + 每句间隔 120ms：并发打过去容易被谷歌限流（429）
    for (let i = 0; i < sentences.length; i++) {
      translated.push(await translateOne(sentences[i]))
      if (i < sentences.length - 1) await new Promise((r) => setTimeout(r, 120))
    }
    rawTranslate.value = translated.join('\n')
    Toast.success(`翻译完成：${translated.length} 句`)
  } catch (e: any) {
    Toast.error('翻译失败：' + (e?.message || e) + '（可以自己粘译文）')
  } finally {
    translating.value = false
  }
}

function close() {
  emit('update:modelValue', false)
}

function reset() {
  bookName.value = ''
  articleTitle.value = ''
  articleTitleTranslate.value = ''
  rawText.value = ''
  rawTranslate.value = ''
  textFileName.value = ''
  translateFileName.value = ''
}

/** 读本地文本文件；文件名去掉扩展名当默认标题 */
async function readTextFile(file: File, isTranslate: boolean) {
  const text = await file.text()
  if (isTranslate) {
    rawTranslate.value = text
    translateFileName.value = file.name
  } else {
    rawText.value = text
    textFileName.value = file.name
    if (!articleTitle.value) {
      articleTitle.value = file.name.replace(/\.(txt|md|markdown)$/i, '')
    }
    if (!bookName.value) {
      bookName.value = articleTitle.value
    }
  }
}

function onTextFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) readTextFile(file, false)
  input.value = ''
}

function onTranslateFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) readTextFile(file, true)
  input.value = ''
}

async function submit() {
  if (saving.value) return

  const text = rawText.value.trim()
  if (!text) {
    return Toast.warning('原文不能为空！先选一个 txt / md 文件')
  }
  if (!articleTitle.value.trim()) {
    return Toast.warning('请填写文章标题')
  }
  if (!bookName.value.trim()) {
    return Toast.warning('请填写书籍名（文章会归到这本书下面）')
  }

  saving.value = true
  try {
    // 英文原文：自动断句（复用上游缩写/数字/引号处理）
    const enSentences = toSentences(text)

    // 中文译文：优先「一句一行」逐句对齐；行数对不上才退回上游中文断句器再截断/补空
    let zhSentences: string[] = []
    const rawZh = rawTranslate.value.trim()
    if (rawZh) {
      const zhLines = rawZh
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean)
      if (zhLines.length === enSentences.length) {
        zhSentences = zhLines
      } else {
        const zhText = splitCNArticle2(rawZh)
        zhSentences = zhText
          .split('\n\n')
          .flatMap((p) => p.split('\n'))
          .map((s) => s.trim())
          .filter(Boolean)
          .slice(0, enSentences.length)
        while (zhSentences.length < enSentences.length) zhSentences.push('')
      }
    }

    // 统一成上游的「一句一段」结构：
    // genArticleSectionData 是按「第 i 段 ↔ 译文第 i 段、第 j 句 ↔ 译文第 j 句」配对的，
    // 段落数/句数对不上，译文就会整片错位。
    const articleText = enSentences.join('\n\n')
    const articleTranslate = zhSentences.join('\n\n')

    const article = getDefaultArticle({
      title: articleTitle.value.trim(),
      titleTranslate: articleTitleTranslate.value.trim(),
      text: articleText,
      textTranslate: articleTranslate,
    })
    // 生成 sections：练习页逐句高亮、打点、统计全靠它
    genArticleSectionData(article)

    if (!article.sections?.length) {
      saving.value = false
      return Toast.error('原文解析后没有内容，检查一下文件格式')
    }

    const articles = [article]
    const dict = getDefaultDict({
      id: 'custom-dict-' + Date.now(),
      name: bookName.value.trim(),
      description: `本地导入：${articleTitle.value.trim()}`,
      type: DictType.article,
      language: 'en',
      translateLanguage: 'zh-CN',
      articles,
      length: articles.length,
      custom: true,
      system: false,
      cover: '',
      category: '我的文章',
      tags: ['本地导入'],
    })

    base.article.bookList.push(dict)
    // 切到新书，首页「开始学习」直接练它
    base.article.studyIndex = base.article.bookList.length - 1
    await dataSync.saveDictState()

    Toast.success(`导入成功！《${dict.name}》已加入我的书籍`)
    emit('imported', dict.id)
    reset()
    close()
  } catch (e: any) {
    Toast.error('导入失败：' + (e?.message || e))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog :model-value="props.modelValue" @close="close" :footer="false" :header="false">
    <div class="import-article">
      <!-- Header -->
      <div class="ia-head">
        <div class="ia-title">导入文章</div>
        <div class="ia-sub">选一个 txt / md 当原文，句子会自动断好；译文可选。</div>
      </div>

      <!-- Body -->
      <div class="ia-body">
        <div class="ia-grid2">
          <div class="ia-field">
            <div class="ia-label">书籍名</div>
            <BaseInput v-model="bookName" placeholder="例如：小学英语课文（导入的文章都归到这本书下）" />
          </div>
          <div class="ia-field">
            <div class="ia-label">文章标题</div>
            <BaseInput v-model="articleTitle" placeholder="例如：Lesson 1 Good Morning" />
          </div>
        </div>

        <div class="ia-field">
          <div class="ia-label">标题翻译<span class="ia-flag">可选</span></div>
          <BaseInput v-model="articleTitleTranslate" placeholder="例如：第一课 早上好" />
        </div>

        <!-- 原文 / 译文：同一个 Grid 容器，列宽共享，两行的「选择文件」严格纵向对齐 -->
        <div class="ia-texts">
          <div class="ia-label">
            原文<span class="ia-flag need">必填</span>
            <span v-if="textFileName" class="ia-tag">{{ textFileName }}</span>
          </div>
          <label class="ia-btn">
            选择文件
            <input type="file" accept=".txt,.md,.markdown" class="hidden" @change="onTextFileChange" />
          </label>
          <BaseButton type="info" :loading="translating" @click="translateToChinese">翻译成中文</BaseButton>

          <Textarea
            v-model="rawText"
            :autosize="{ minRows: 6, maxRows: 14 }"
            class="ia-span"
            placeholder="选文件或直接粘贴英文原文，一句一行或整段都行"
          />

          <div class="ia-label">
            译文<span class="ia-flag">可选</span>
            <span v-if="translateFileName" class="ia-tag">{{ translateFileName }}</span>
          </div>
          <label class="ia-btn">
            选择文件
            <input type="file" accept=".txt,.md,.markdown" class="hidden" @change="onTranslateFileChange" />
          </label>
          <span></span>

          <Textarea
            v-model="rawTranslate"
            :autosize="{ minRows: 4, maxRows: 10 }"
            class="ia-span"
            placeholder="选文件或直接粘贴中文译文，写成一句一行就和原文句子一一对应"
          />
        </div>

        <!-- 低频高级项：默认收起 -->
        <details class="ia-advanced">
          <summary>高级设置：自建翻译服务</summary>
          <div class="ia-advanced-body">
            <BaseInput
              :model-value="translateEndpoint"
              placeholder="LibreTranslate / Argos 地址，如 http://localhost:5000；留空就用谷歌"
              @update:model-value="onEndpointChange"
            />
            <div class="ia-hint">填了就走开源自建的翻译服务（LibreTranslate / Argos Translate），留空走谷歌。</div>
          </div>
        </details>
      </div>

      <!-- Footer -->
      <div class="ia-foot">
        <BaseButton type="info" @click="close">取消</BaseButton>
        <BaseButton type="primary" :loading="saving" @click="submit">导入</BaseButton>
      </div>
    </div>
  </Dialog>
</template>

<style scoped lang="scss">
.import-article {
  /* 主按钮换品牌蓝，和项目里 #409eff 的强调色统一 */
  --btn-primary: #409eff;
  --btn-primary-hover: #66b1ff;
  --btn-primary-disabled: #a0cfff;

  display: flex;
  flex-direction: column;
  width: 48rem;
  max-width: 92vw;
  max-height: 80vh;
  min-width: 0;
}

.ia-head {
  padding: 24px 24px 0;
  padding-right: 56px; /* 给右上角关闭按钮让位 */

  .ia-title {
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--color-main-text);
  }

  .ia-sub {
    margin-top: 4px;
    font-size: 0.85rem;
    color: var(--color-main-text);
    opacity: 0.65;
  }
}

.ia-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px 0;
}

.ia-field {
  margin-bottom: 16px;

  .ia-label {
    margin-bottom: 8px;
  }
}

.ia-grid2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  column-gap: 16px;
}

/* 标签 + 操作按钮 */
.ia-label {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 0.85rem;
  line-height: 20px; /* 和 2rem 高的按钮同高，文字基线才对齐 */
  color: var(--color-main-text);
}

.ia-flag {
  font-size: 0.72rem;
  line-height: 1.5;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.06);
  color: var(--color-main-text);
  opacity: 0.7;

  &.need {
    background: rgba(64, 158, 255, 0.12);
    color: #409eff;
    opacity: 1;
  }
}

/* 文件名胶囊 */

.ia-tag {
  display: inline-block;
  max-width: 100%;
  margin-left: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.75rem;
  line-height: 1.5;
  padding: 1px 10px;
  border-radius: 999px;
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

/* 描边按钮：和 BaseButton type=info 同一套观感 */
.ia-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 2rem;
  padding: 0 0.9rem;
  font-size: 0.9rem;
  line-height: 1;
  white-space: nowrap;
  cursor: pointer;
  user-select: none;
  border-radius: 0.3rem;
  border: 1px solid var(--color-main-text);
  background: var(--btn-info, white);
  color: var(--color-main-text);

  &:hover {
    background: var(--btn-info-hover, #eaeaea);
  }
}

/* 原文 / 译文：同一个 Grid 容器，列宽共享，两行的「选择文件」严格纵向对齐 */
.ia-texts {
  display: grid;
  grid-template-columns: 1fr auto auto;
  column-gap: 8px;
  row-gap: 16px;
  align-items: center;

  .ia-span {
    grid-column: 1 / -1;
    width: 100%;
  }
}

.ia-advanced {
  margin-bottom: 16px;
  padding-top: 16px;

  summary {
    cursor: pointer;
    font-size: 0.85rem;
    color: var(--color-main-text);
    opacity: 0.7;
    list-style: none;

    &::-webkit-details-marker {
      display: none;
    }

    &::before {
      content: '▸ ';
    }
  }

  &[open] summary::before {
    content: '▾ ';
  }

  .ia-advanced-body {
    margin-top: 12px;
  }

  .ia-hint {
    margin-top: 8px;
    font-size: 0.78rem;
    color: var(--color-main-text);
    opacity: 0.6;
  }
}

.ia-foot {
  display: flex;
  justify-content: flex-end;
  padding: 16px 24px 24px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}
</style>
