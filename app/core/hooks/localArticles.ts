/**
 * 本地导入文章 ↔ 服务端副本
 * ==========================
 * 问题：「导入文章」原本只写浏览器 IndexedDB → **换个浏览器打开就是空书架**
 *      （同一台机器，Edge / Chrome / 内置浏览器 各有各的 IndexedDB）。
 *
 * 做法：导入成功后把书再 POST 给本地 dev server（data/local-articles.json），
 *      文章页每次打开都 GET 一遍并合并进书架 →
 *      - 任何浏览器打开同一个 dev server 都能看到这些文章；
 *      - 清缓存不丢；
 *      - 导入的那台浏览器仍然留本地副本，学习进度照常存。
 *
 * 静态部署（没有 server runtime）时接口 404，这里静默降级为「只存本浏览器」。
 */
import { genArticleSectionData } from '@/core/hooks/article.ts'
import { useBaseStore } from '@/core/stores/base.ts'
import { getDefaultArticle, getDefaultDict } from '@/core/types'

/** 拉服务端副本，合并进当前书架；返回新合并了几本 */
export async function mergeServerArticles(): Promise<number> {
  const base = useBaseStore()
  try {
    const res = await fetch('/api/local-articles')
    if (!res.ok) return 0
    const list = await res.json()
    if (!Array.isArray(list) || !list.length) return 0

    let merged = 0
    for (const d of list) {
      // 本地已经有（这台浏览器导入过）→ 不覆盖，保留本地的学习进度
      if (base.article.bookList.some(v => v.id === d.id)) continue

      const articles = (d.articles || []).map((a: any) => {
        const art = getDefaultArticle({
          title: a.title,
          titleTranslate: a.titleTranslate,
          text: a.text,
          textTranslate: a.textTranslate,
        })
        // sections 不落盘（上游设计），运行时重算，练习页逐句高亮/打点全靠它
        genArticleSectionData(art)
        return art
      })

      base.article.bookList.push(
        getDefaultDict({
          ...d,
          articles,
          length: articles.length,
          custom: true,
          system: false,
        })
      )
      merged++
    }
    return merged
  } catch (e: any) {
    console.warn('[local-articles] 服务端不可用，只用本地副本', e)
    return 0
  }
}

/**
 * 把本机已有的「本地导入书」补推到服务端。
 *
 * 场景：书是**之前**在某个浏览器导入的（那时还没这个服务端副本机制），
 *      现在换浏览器打开还是看不到 → 打开文章页时把本地这本推上去，
 *      之后所有浏览器都能看到。
 *
 * 只推 custom 书（本地导入的），系统内置书本来就是走 public/list/*.json 全网共享的。
 * 服务端已有同 id 的书不重复推（导入时 syncArticleToServer 已经写过了）。
 */
export async function pushLocalArticlesToServer(): Promise<number> {
  const base = useBaseStore()
  const local = base.article.bookList.filter(v => v.custom && !v.system && v.articles?.length)
  if (!local.length) return 0

  try {
    const res = await fetch('/api/local-articles')
    if (!res.ok) return 0
    const exist = new Set<string>(((await res.json()) || []).map((v: any) => v.id))

    let pushed = 0
    for (const d of local) {
      if (exist.has(d.id)) continue
      if (await syncArticleToServer(d)) pushed++
    }
    return pushed
  } catch (e: any) {
    console.warn('[local-articles] 推送本机书籍到服务端失败', e)
    return 0
  }
}

/** 删除书时同步删掉服务端副本（不然换浏览器还看得见幽灵书） */
export async function removeArticleFromServer(id: string): Promise<boolean> {
  try {
    await $fetch('/api/local-articles', { method: 'DELETE', query: { id } })
    return true
  } catch (e: any) {
    console.warn('[local-articles] 删除服务端副本失败', e)
    return false
  }
}

/** 导入成功后把书同步到服务端；失败不打扰用户（本地那份照常能用） */
export async function syncArticleToServer(dict: any): Promise<boolean> {
  try {
    await $fetch('/api/local-articles', {
      method: 'POST',
      body: {
        id: dict.id,
        name: dict.name,
        description: dict.description,
        language: dict.language,
        translateLanguage: dict.translateLanguage,
        category: dict.category,
        tags: dict.tags,
        articles: (dict.articles || []).map((a: any) => ({
          title: a.title,
          titleTranslate: a.titleTranslate,
          text: a.text,
          textTranslate: a.textTranslate,
        })),
      },
    })
    return true
  } catch (e: any) {
    console.warn('[local-articles] 同步到服务端失败，只存本浏览器', e)
    return false
  }
}
