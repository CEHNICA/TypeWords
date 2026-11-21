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

let bookName = ref('')
let articleTitle = ref('')
let articleTitleTranslate = ref('')
let rawText = ref('')
let rawTranslate = ref('')
let textFileName = ref('')
let translateFileName = ref('')
let saving = ref(false)

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
    const enText = splitEnArticle2(text)
    // 摊平成句子列表：上游是「段落用 \n\n、段内句子用 \n」
    const enSentences: string[] = enText
      .split('\n\n')
      .flatMap((p) => p.split('\n'))
      .map((s) => s.trim())
      .filter(Boolean)

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
  <Dialog :model-value="props.modelValue" @close="close" :footer="false">
    <div class="import-article">
      <div class="title text-xl mb-1">导入文章</div>
      <div class="text-sm color-gray mb-4">
        选一个 txt / md 文件当原文（一句话一行或整段都行，会自动断句）；译文可以再选一个中文文件，也可以直接粘。译文写成一句一行，就和原文句子一一对应。
      </div>

      <div class="flex gap-4">
        <div class="grow">
          <div class="text-sm color-gray mb-1">书籍名</div>
          <BaseInput v-model="bookName" placeholder="例如：小学英语课文" />
        </div>
        <div class="grow">
          <div class="text-sm color-gray mb-1">文章标题</div>
          <BaseInput v-model="articleTitle" placeholder="例如：Lesson 1 Good Morning" />
        </div>
      </div>

      <div class="text-sm color-gray mt-3 mb-1">标题翻译（可选）</div>
      <BaseInput v-model="articleTitleTranslate" placeholder="例如：第一课 早上好" />

      <div class="flex items-center justify-between mt-4 mb-1">
        <div class="text-sm color-gray">原文（必填）</div>
        <label class="base-button normal text cursor-pointer">
          选择文件
          <input type="file" accept=".txt,.md,.markdown" class="hidden" @change="onTextFileChange" />
        </label>
      </div>
      <Textarea v-model="rawText" :autosize="false" class="h-40" placeholder="选文件或直接粘贴英文原文" />

      <div class="flex items-center justify-between mt-4 mb-1">
        <div class="text-sm color-gray">译文（可选，一句一行，和原文句子一一对应）</div>
        <label class="base-button normal text cursor-pointer">
          选择文件
          <input type="file" accept=".txt,.md,.markdown" class="hidden" @change="onTranslateFileChange" />
        </label>
      </div>
      <Textarea v-model="rawTranslate" :autosize="false" class="h-28" placeholder="选文件或直接粘贴中文译文" />

      <div class="text-sm color-gray mt-3">
        已选原文：{{ textFileName || '（未选）' }} ｜ 译文：{{ translateFileName || '（未选）' }}
      </div>

      <div class="flex gap-3 justify-end mt-4">
        <BaseButton type="info" @click="close">取消</BaseButton>
        <BaseButton type="primary" :loading="saving" @click="submit">导入</BaseButton>
      </div>
    </div>
  </Dialog>
</template>

<style scoped lang="scss">
.import-article {
  width: 46rem;
  max-width: 90vw;
}
</style>
