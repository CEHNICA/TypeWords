<script setup lang="ts">
/**
 * 本地导入词表
 * ============
 * 上游 master 的词表链路是断的：
 *   1. 词典详情页有「导入」按钮 → nav('/import')，但 /import 页面根本不存在 → 404 死链；
 *   2. 上游只有「手动一个个加词」，没有批量导入；
 *   3. 导出 xlsx 的格式（单词/音标①/音标②/笔记/翻译）和导入应该闭环，但导入端是空的。
 *
 * 这里把整条补齐：选本地 xlsx / xls / csv / txt → 解析 → 预览 → 落地成一本**本地词书**
 * （custom: true，走已有持久化链，不新增 IndexedDB schema，零迁移风险）→ 直接能开始练习。
 *
 * 两种落地方式（同一个组件，一个出口）：
 *   - 不传 targetId：新建一本本地词书（词书名可改，默认取文件名）；
 *   - 传 targetId（词典详情页「导入」死链走这条）：合并进那本词典，同名单词自动跳过。
 *
 * 解析规则见 @/core/utils/custom-word-import.ts（纯函数，单独可测）。
 */
import { BaseButton, BaseInput, Toast } from '@/base'
import { LIB_JS_URL } from '@/core/config/env.ts'
import { useDataSyncPersistence } from '@/core/composables/useDataSyncPersistence.ts'
import { useBaseStore } from '@/core/stores/base.ts'
import { useRuntimeStore } from '@/core/stores/runtime.ts'
import { getDefaultDict, getDefaultWord } from '@/core/types'
import { DictType } from '@/core/types/enum.ts'
import {
  buildWords,
  decodeBuffer,
  detectColumns,
  parseDelimited,
  type BuildWordsResult,
  type ColumnMap,
} from '@/core/utils/custom-word-import.ts'
import { loadJsLib } from '@/core/utils'
import { computed, defineAsyncComponent, ref } from 'vue'

const Dialog = defineAsyncComponent(() => import('@/base/dialog/Dialog.vue'))

const props = defineProps<{ modelValue: boolean; targetId?: string }>()
const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  imported: [dictId: string]
}>()

const base = useBaseStore()
const runtimeStore = useRuntimeStore()
const dataSync = useDataSyncPersistence()

let bookName = ref('')
let fileName = ref('')
let fileEncoding = ref('')
let parsing = ref(false)
let saving = ref(false)

/** 预览用的表头行 */
let headerRow = ref<string[]>([])
/** 预览用的前几行数据 */
let previewRows = ref<string[][]>([])
/** 解析出来的完整词条 */
let parsed = ref<BuildWordsResult>({ words: [], errors: [], duplicates: 0 })
/** 列映射（供「表头识别结果」提示用） */
let columnMap = ref<ColumnMap>({ word: -1, phonetic0: -1, phonetic1: -1, trans: -1, note: -1 })
let hasHeader = ref(false)

const PREVIEW_LIMIT = 8

/**
 * 目标词典（合并模式）。
 *
 * 只有「这本书真的在本地词典列表里」才算合并模式：
 * 上游 dict.vue 的导入入口传的是 runtimeStore.editDict.id，
 * 而内置词典（学过的 CET-4 等）压根不在 base.word.bookList 里 →
 * 早先只判断 props.targetId 的话，会进「合并模式」但找不到目标，
 * 词书名输入框又被隐藏 → 用户卡死在一个没法完成的对话框里。
 */
const targetDict = computed(() => {
  if (!props.targetId) return null
  return base.word.bookList.find(v => String(v.id) === String(props.targetId)) ?? null
})

/**
 * 合并模式：目标词典存在，且是可编辑的（custom 自定义 / system 收藏·错词·已掌握）。
 *
 * 内置词典（CET-4 那些）虽然能被加进 bookList，但存盘时
 * shakeCommonDict 会把非 custom、非 system 词典的 words 整份清空
 * （用的时候再下载），往里塞词等于白干 → 这类目标一律降级成「新建本地词书」。
 */
const isMergeMode = computed(() => {
  const t = targetDict.value
  return !!t && (!!t.custom || !!t.system)
})

/** 目标存在但不能合并（内置词典）→ 提示用户会改成新建 */
const targetIsBuiltin = computed(() => !!targetDict.value && !isMergeMode.value)

/** 传了 targetId 但本地根本没有这本词典 → 同样是降级成新建，但文案不能说成「内置词典」 */
const targetMissing = computed(() => !!props.targetId && !targetDict.value)

function close() {
  emit('update:modelValue', false)
}

function reset() {
  bookName.value = ''
  fileName.value = ''
  fileEncoding.value = ''
  headerRow.value = []
  previewRows.value = []
  parsed.value = { words: [], errors: [], duplicates: 0 }
  columnMap.value = { word: -1, phonetic0: -1, phonetic1: -1, trans: -1, note: -1 }
  hasHeader.value = false
}

/** 解析好的数据 → 预览状态 */
function applyRows(rows: string[][]) {
  if (!rows.length) {
    Toast.error('文件里没有读到任何内容')
    return
  }
  const { map, hasHeader: hh } = detectColumns(rows)
  columnMap.value = map
  hasHeader.value = hh

  if (map.word === -1) {
    Toast.error('没找到「单词」列 —— 表头里要有 单词 / word / 英文 之一')
    return
  }

  const result = buildWords(rows, map, hh)
  parsed.value = result

  headerRow.value = hh ? rows[0] : rows[0].map((_, i) => ['单词', '翻译', '音标', '笔记', '其他'][i] ?? `列${i + 1}`)
  const dataRows = hh ? rows.slice(1) : rows
  previewRows.value = dataRows.slice(0, PREVIEW_LIMIT)

  if (!result.words.length) {
    Toast.error('没解析出有效单词，检查一下文件内容')
    return
  }
  Toast.success(`解析到 ${result.words.length} 个单词`)
}

async function parseXlsx(file: File) {
  const XLSX = await loadJsLib('XLSX', LIB_JS_URL.XLSX)
  const buffer = await file.arrayBuffer()
  const wb = XLSX.read(new Uint8Array(buffer), { type: 'array' })
  const sheetName = wb.SheetNames[0]
  if (!sheetName) {
    Toast.error('这个 Excel 里没有工作表')
    return
  }
  const sheet = wb.Sheets[sheetName]
  const rows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: '', blankrows: false }) as string[][]
  applyRows(rows.map(r => (r ?? []).map(c => String(c ?? ''))))
}

async function parseCsv(file: File) {
  const buffer = await file.arrayBuffer()
  const { text, encoding } = decodeBuffer(buffer)
  fileEncoding.value = encoding
  applyRows(parseDelimited(text))
}

async function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return

  parsing.value = true
  fileName.value = file.name
  // 注意：isMergeMode 是 computed（ref 对象），在 script 里必须写 .value。
  // 写成裸的 isMergeMode 的话 ref 对象恒为 truthy → 这段永远不执行 → 词书名永远空着
  // → 提交时被「给这本词书起个名字」拦下（踩过）。
  if (!isMergeMode.value && !bookName.value) {
    bookName.value = file.name.replace(/\.(xlsx|xls|csv|txt)$/i, '')
  }
  try {
    if (/\.(xlsx|xls)$/i.test(file.name)) await parseXlsx(file)
    else await parseCsv(file)
  } catch (err: any) {
    Toast.error('解析失败：' + (err?.message || err))
    reset()
    fileName.value = file.name
  } finally {
    parsing.value = false
  }
}

/**
 * 目标词典（合并模式）→ 见 targetDict 计算属性。
 * 合并只对「本地已有的自定义词典」生效。
 */
async function submit() {
  if (saving.value) return
  const words = parsed.value.words
  if (!words.length) return Toast.warning('还没有可导入的单词')

  saving.value = true
  try {
    let target = isMergeMode.value ? targetDict.value : null
    let added = words.length
    let skipped = 0

    if (target) {
      // 合并进已有词典：同名单词跳过（不覆盖用户已有的编辑）
      const exist = new Set((target.words ?? []).map(v => String(v.word).toLowerCase()))
      const fresh = words.filter(w => {
        const k = w.word.toLowerCase()
        if (exist.has(k)) {
          skipped++
          return false
        }
        exist.add(k)
        return true
      })
      for (const w of fresh) {
        target.words.push(
          getDefaultWord({
            word: w.word,
            phonetic0: w.phonetic0,
            phonetic1: w.phonetic1,
            trans: w.trans ? [{ pos: '', cn: w.trans }] : [],
            custom: true,
          })
        )
      }
      target.length = target.words.length
      added = fresh.length
    } else {
      const name = bookName.value.trim()
      if (!name) return Toast.warning('给这本词书起个名字')
      if (base.word.bookList.some(v => v.name === name)) {
        return Toast.warning('已经有一本同名词书了，换个名字')
      }
      const dict = getDefaultDict({
        id: 'custom-dict-' + Date.now(),
        enName: 'custom-' + Date.now(),
        name,
        description: `本地导入：${fileName.value}`,
        type: DictType.word,
        language: 'en',
        translateLanguage: 'zh-CN',
        custom: true,
        system: false,
        category: '我的词表',
        tags: ['本地导入'],
        words: words.map(w =>
          getDefaultWord({
            word: w.word,
            phonetic0: w.phonetic0,
            phonetic1: w.phonetic1,
            trans: w.trans ? [{ pos: '', cn: w.trans }] : [],
            custom: true,
          })
        ),
      })
      dict.length = dict.words.length
      base.word.bookList.push(dict)
      // 切到新词书，首页「开始学习」直接练它
      base.word.studyIndex = base.word.bookList.length - 1
      target = dict
    }

    await dataSync.saveDictState()
    runtimeStore.editDict = getDefaultDict(target as any)

    const skippedText = skipped ? `，跳过 ${skipped} 个重复` : ''
    Toast.success(`导入成功：${added} 个单词${skippedText}`)
    emit('imported', String((target as any).id))
    reset()
    close()
  } catch (e: any) {
    Toast.error('导入失败：' + (e?.message || e))
  } finally {
    saving.value = false
  }
}

/** 「表头识别结果」提示文案 */
const columnHint = () => {
  const names: Record<string, string> = { word: '单词', phonetic0: '音标①', phonetic1: '音标②', trans: '翻译', note: '笔记' }
  const hit = Object.entries(columnMap.value)
    .filter(([, idx]) => idx > -1)
    .map(([f]) => names[f])
  return hit.length ? hit.join(' / ') : '未识别到表头'
}
</script>

<template>
  <Dialog :model-value="props.modelValue" @close="close" :footer="false" :header="false">
    <div class="import-word-list">
      <!-- Header -->
      <div class="iw-head">
        <div class="iw-title">导入词表</div>
        <div class="iw-sub">
          支持 xlsx / xls / csv / txt。表头里有「单词」列就能认出来，翻译、音标、笔记可选。
        </div>
      </div>

      <!-- Body -->
      <div class="iw-body">
        <div class="iw-field" v-if="!isMergeMode">
          <div class="iw-label">词书名<span class="iw-flag need">必填</span></div>
          <BaseInput v-model="bookName" placeholder="例如：我的生词本" />
          <!-- 内置词典不能直接塞词（存盘会被清空），如实说明，别让用户以为合并成功了 -->
          <div class="iw-note" v-if="targetMissing">
            找不到这本词典（id：{{ props.targetId }}），已改为新建一本本地词书。
          </div>
          <div class="iw-note" v-else-if="targetIsBuiltin">
            这本内置词典不能直接导入（它的词条是按需下载的，存盘会被清空），
            已改为新建一本本地词书。
          </div>
        </div>

        <div class="iw-field">
          <div class="iw-label">
            词表文件
            <span v-if="fileName" class="iw-tag">{{ fileName }}<span v-if="fileEncoding" class="iw-enc">{{ fileEncoding }}</span></span>
          </div>
          <label class="iw-btn">
            选择文件
            <input type="file" accept=".xlsx,.xls,.csv,.txt" class="hidden" @change="onFileChange" />
          </label>
          <BaseButton v-if="fileName" type="info" @click="reset">换一个文件</BaseButton>
          <span></span>
        </div>

        <div class="iw-preview" v-if="parsed.words.length">
          <div class="iw-label">
            预览（前 {{ previewRows.length }} 行 / 共 {{ parsed.words.length }} 个单词）
            <span class="iw-flag">{{ columnHint() }}</span>
          </div>
          <div class="iw-table-wrap">
            <table class="iw-table">
              <thead>
                <tr>
                  <th v-for="(h, i) in headerRow" :key="'h' + i">{{ h }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, ri) in previewRows" :key="'r' + ri">
                  <td v-for="(c, ci) in row" :key="'c' + ri + '-' + ci">{{ c }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="iw-err" v-if="parsed.errors.length">
            {{ parsed.errors.length }} 行有问题（已跳过）：
            <span v-for="(e, i) in parsed.errors.slice(0, 3)" :key="i">第 {{ e.row }} 行 {{ e.reason }}</span>
            <span v-if="parsed.errors.length > 3">…</span>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="iw-foot">
        <BaseButton type="info" @click="close">取消</BaseButton>
        <BaseButton type="primary" :loading="saving" :disabled="!parsed.words.length" @click="submit">
          {{ isMergeMode ? '合并到当前词典' : '导入' }}
        </BaseButton>
      </div>
    </div>
  </Dialog>
</template>

<style scoped lang="scss">
.import-word-list {
  --btn-primary: #409eff;
  --btn-primary-hover: #66b1ff;
  --btn-primary-disabled: #a0cfff;

  display: flex;
  flex-direction: column;
  width: 46rem;
  max-width: 92vw;
  max-height: 80vh;
  min-width: 0;
}

.iw-head {
  padding: 24px 24px 0;
  padding-right: 56px;

  .iw-title {
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--color-main-text);
  }

  .iw-sub {
    margin-top: 4px;
    font-size: 0.85rem;
    color: var(--color-main-text);
    opacity: 0.65;
  }
}

.iw-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px 0;
}

.iw-field {
  margin-bottom: 16px;
}

.iw-label {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  margin-bottom: 8px;
  font-size: 0.85rem;
  line-height: 20px;
  color: var(--color-main-text);
}

.iw-flag {
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

.iw-tag {
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

.iw-enc {
  margin-left: 6px;
  opacity: 0.7;
}

.iw-btn {
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

.iw-preview {
  margin-bottom: 16px;
}

.iw-table-wrap {
  max-height: 16rem;
  overflow: auto;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 0.3rem;
}

.iw-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;

  th,
  td {
    padding: 6px 10px;
    text-align: left;
    white-space: nowrap;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  }

  th {
    position: sticky;
    top: 0;
    background: rgba(0, 0, 0, 0.03);
    font-weight: 600;
  }

  tr:last-child td {
    border-bottom: none;
  }
}

.iw-err {
  margin-top: 8px;
  font-size: 0.78rem;
  color: #e6a23c;

  span {
    margin-right: 10px;
  }
}

.iw-note {
  margin-top: 6px;
  font-size: 0.78rem;
  line-height: 1.5;
  color: var(--color-main-text);
  opacity: 0.6;
}

.iw-foot {
  display: flex;
  justify-content: flex-end;
  padding: 16px 24px 24px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}
</style>
