import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

/**
 * 本地离线查词索引
 * ==================
 * 查词原本走云端 Supabase 接口（本地没配 → 必然失败），
 * 失败后弹 **有道整页 iframe** → 加载外网广告页，慢，而且界面一堆按钮。
 *
 * 这里把本地 207 份词库离线合并成一份精简索引（scripts/build-word-index.mjs 生成）：
 *   data/word-index.json  →  word(小写) → { word, phonetic0/1, trans[], sentences[], phrases[], synos[], src }
 *
 * 服务端读一次进内存 Map，查词 O(1)、**零网络**。
 * 索引文件不在版本库（.gitignore 的 /data/），没构建过就 404 → 前端静默降级。
 *
 * ⚠️ 两个必须记住的坑：
 *  1. 缓存变量必须挂在 **globalThis** 上。Nuxt dev 的 HMR 会重置模块级变量，
 *     挂模块级 = 每次热更新都重新解析 20MB JSON（实测每次请求多 250ms）。
 *  2. `cache` 必须真的赋值。早先只 `return map` 没 `cache = map`，
 *     结果每个请求都重读磁盘重解析 —— dev.log 里「已加载 31748 个词条」刷十几遍就是它。
 */

const INDEX_FILE = join(process.cwd(), 'data', 'word-index.json')
const FORMS_FILE = join(process.cwd(), 'data', 'word-forms.txt')

interface IndexStore {
  cache: Map<string, any> | null
  loading: Promise<Map<string, any>> | null
  ready: boolean
  forms: Map<string, string> | null
  formsLoading: Promise<Map<string, string>> | null
}

// 挂 globalThis：跨 HMR / 跨模块实例保持同一个缓存
const g = globalThis as any as { __twWordIndex?: IndexStore }
const store: IndexStore = (g.__twWordIndex ||= {
  cache: null,
  loading: null,
  ready: false,
  forms: null,
  formsLoading: null,
})

export async function loadIndex(): Promise<Map<string, any>> {
  if (store.cache) return store.cache
  if (store.loading) return store.loading

  store.loading = (async () => {
    try {
      if (!existsSync(INDEX_FILE)) {
        console.warn('[word-index] 索引不存在，先跑 node scripts/build-word-index.mjs')
        return new Map()
      }
      const raw = await readFile(INDEX_FILE, 'utf-8')
      const obj = JSON.parse(raw)
      const map = new Map<string, any>()
      for (const [k, v] of Object.entries(obj)) map.set(k, v)
      store.cache = map // ← 关键：必须写回缓存，否则每次请求都重解析
      store.ready = true
      console.log(`[word-index] 已加载 ${map.size} 个词条`)
      return map
    } catch (e: any) {
      console.warn('[word-index] 索引加载失败', e)
      return new Map()
    } finally {
      store.loading = null
    }
  })()

  return store.loading
}

/**
 * 加载词形映射表（形变 → 原形）
 * ====================================
 * 教辅词书只收**原形**（ask / year / thing），用户文章里全是屈折形态
 * （asks / years / things / guided / shows）→ 直接查必落空。
 * 构建期预生成映射表（scripts/augment-word-index.mjs），查词 miss 时回退到原形取释义。
 */
export async function loadForms(): Promise<Map<string, string>> {
  if (store.forms) return store.forms
  if (store.formsLoading) return store.formsLoading

  store.formsLoading = (async () => {
    try {
      if (!existsSync(FORMS_FILE)) {
        console.warn('[word-index] 词形表不存在，先跑 node scripts/augment-word-index.mjs')
        return new Map()
      }
      // 纯文本格式：每行 "form<TAB>base"，比 JSON 小 3~4 倍、解析也快
      // **必须按 TAB 切**：base 可能是含空格的短语，按空格切会切错
      const raw = await readFile(FORMS_FILE, 'utf-8')
      const map = new Map<string, string>()
      for (const line of raw.split('\n')) {
        if (!line) continue
        const sp = line.indexOf('\t')
        if (sp <= 0) continue
        map.set(line.slice(0, sp), line.slice(sp + 1))
      }
      store.forms = map
      console.log(`[word-index] 已加载 ${map.size} 条词形映射`)
      return map
    } catch (e: any) {
      console.warn('[word-index] 词形表加载失败', e)
      return new Map()
    } finally {
      store.formsLoading = null
    }
  })()

  return store.formsLoading
}

/** 索引是否就绪（构建过且加载成功）。未就绪 → 服务端返回 503，前端才不会误判成「词典没这个词」。 */
export function isIndexReady(): boolean {
  return store.ready
}

/**
 * 确保索引已加载（首次会读盘 + 解析 20MB JSON，约 400ms），返回是否就绪。
 * 服务端接口必须走这个，**不能只看 isIndexReady()** —— 那个在首次加载前恒为 false，
 * 那样会导致「第一个查词的请求永远 503，之后才正常」。
 */
export async function ensureIndex(): Promise<boolean> {
  await loadIndex()
  return store.ready
}

/**
 * 查词（本地离线词典）
 * ====================
 * 命中顺序有讲究：
 *   1. 精确命中**教辅词书**的条目 → 直接用；
 *   2. 精确命中 **CC-CEDICT** 的条目 → 但如果这个词是某个教辅原形的变形
 *      （guiding → guide），**优先给教辅释义**：
 *      CC-CEDICT 里 "Guiding" 是贵州地名「贵定县」，直接用会把用户带沟里；
 *   3. 精确没命中 → 走词形映射回退到原形（asks → ask）。
 */
export async function lookupLocalWord(word: string): Promise<any | null> {
  const key = (word || '').trim().toLowerCase()
  if (!key) return null
  const map = await loadIndex()
  const forms = await loadForms()

  const hit = map.get(key)
  if (hit) {
    if (hit.src === 'CC-CEDICT') {
      const base = forms.get(key)
      if (base && base !== key) {
        const baseEntry = map.get(base)
        if (baseEntry && baseEntry.src !== 'CC-CEDICT') {
          return { ...baseEntry, word: key, baseWord: base }
        }
      }
    }
    return { ...hit }
  }

  // 形变未收录 → 回退到原形（asks → ask），返回条目里带上 baseWord 让前端标注
  const base = forms.get(key)
  if (base) {
    const baseEntry = map.get(base)
    if (baseEntry) return { ...baseEntry, word: key, baseWord: base }
  }
  return null
}
