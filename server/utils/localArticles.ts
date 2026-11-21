import { promises as fs } from 'node:fs'
import { dirname, join } from 'node:path'

/**
 * 本地导入文章（服务端副本）
 * =================================
 * 为什么需要这个接口：
 *   「导入文章」原本只写浏览器 IndexedDB → **换个浏览器/换台电脑就没了**。
 *   用户在同一台机器上换浏览器打开（Edge / Chrome / 内置浏览器），书架是空的，
 *   看起来像「导入失败」。
 *
 * 这里把导入的文章再存一份到**服务端磁盘**（data/local-articles.json），
 * 前端每次进文章页都会拉一遍并合并进书架 →
 *   - 任何浏览器打开同一台 dev server 都能看到这些文章；
 *   - 清浏览器缓存也不丢；
 *   - 导入的那台浏览器仍然保留本地副本，学习进度照常存。
 *
 * 只在本机 dev server 上有意义（单机单人），所以不做鉴权。
 * 静态部署（没有 server runtime）时接口 404，前端静默降级为「只存本浏览器」。
 */
export const LOCAL_ARTICLES_FILE = join(process.cwd(), 'data', 'local-articles.json')

export async function readLocalArticles(): Promise<any[]> {
  try {
    const raw = await fs.readFile(LOCAL_ARTICLES_FILE, 'utf-8')
    const list = JSON.parse(raw)
    return Array.isArray(list) ? list : []
  } catch {
    return []
  }
}

export async function writeLocalArticles(list: any[]) {
  await fs.mkdir(dirname(LOCAL_ARTICLES_FILE), { recursive: true })
  await fs.writeFile(LOCAL_ARTICLES_FILE, JSON.stringify(list, null, 2), 'utf-8')
}
