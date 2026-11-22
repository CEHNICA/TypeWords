<script setup lang="ts">
/**
 * /import —— 词表导入落地页（上游死链的补丁）
 *
 * 上游 master 的词典详情页有「导入」按钮 → nav('/import', {type:'word', targetId, step:'2'})，
 * 但 app/pages 下**根本没有 import.vue** → 点进去 404。
 * 这里补一个薄壳页：把 query 交给同一个 ImportWordList 组件，
 * 关掉弹窗就退回原来那本词典。
 *
 * 页面本身不露在主导航里（app.vue 已把它列进 noindex 功能页）。
 */
import ImportWordList from '@/components/word/ImportWordList.vue'
import { BasePage } from '@/base'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

/** 只处理词表导入；别的 type 直接退回 */
const isWordImport = computed(() => String(route.query?.type ?? 'word') === 'word')
const targetId = computed(() => String(route.query?.targetId ?? ''))

/**
 * 必须先 false 再在 onMounted 里置 true。
 * 上游 Dialog.vue 是靠 watch(modelValue) 的**变化**来打开的（visible 初始 false，
 * onMounted 只在 modelValue === undefined 时才打开）→ 挂载时直接给 true，
 * watch 不会触发，弹窗永远不出现（踩过）。
 */
let show = ref(false)

onMounted(() => {
  show.value = true
})

watch(show, v => {
  if (v) return
  // 关掉弹窗就退回原来那本词典；直接访问本页没有上一条历史时回词典列表
  if (window.history.state && window.history.state.back) router.back()
  else router.replace('/dict-list')
})

function onImported() {
  router.replace('/dict')
}

useHead({
  title: '导入词表',
  meta: [{ name: 'robots', content: 'noindex, nofollow' }],
})
</script>

<template>
  <BasePage>
    <ImportWordList v-if="isWordImport" v-model="show" :target-id="targetId" @imported="onImported" />
    <div v-else class="import-unsupported">不支持的导入类型</div>
  </BasePage>
</template>

<style scoped lang="scss">
.import-unsupported {
  padding: 2rem;
  text-align: center;
  opacity: 0.7;
}
</style>
