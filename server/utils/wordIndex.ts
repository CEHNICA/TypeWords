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

interface IndexStore {
  cache: Map<string, any> | null
  loading: Promise<Map<string, any>> | null
  ready: boolean
}

// 挂 globalThis：跨 HMR / 跨模块实例保持同一个缓存
const g = globalThis as any as { __twWordIndex?: IndexStore }
const store: IndexStore = (g.__twWordIndex ||= { cache: null, loading: null, ready: false })

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

export async function lookupLocalWord(word: string): Promise<any | null> {
  const key = (word || '').trim().toLowerCase()
  if (!key) return null
  const map = await loadIndex()
  const hit = map.get(key)
  return hit ? { ...hit } : null
}
