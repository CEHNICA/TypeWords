import { readLocalArticles, writeLocalArticles } from '../utils/localArticles'

/**
 * POST /api/local-articles
 * 存一本本地导入的文章（服务端副本）。
 *
 * body: { id, name, description?, language?, translateLanguage?, articles: [{title,titleTranslate,text,textTranslate}] }
 * 同 id 覆盖（重复导入同一本书不会堆一堆）。
 */
export default defineEventHandler(async event => {
  const body: any = await readBody(event).catch(() => null)
  if (!body?.id || !body?.name) {
    throw createError({ statusCode: 400, statusMessage: '缺少 id 或 name' })
  }

  const list = await readLocalArticles()
  const entry = {
    id: String(body.id),
    name: String(body.name),
    description: body.description || '',
    language: body.language || 'en',
    translateLanguage: body.translateLanguage || 'zh-CN',
    type: 'article',
    custom: true,
    system: false,
    cover: '',
    category: body.category || '我的文章',
    tags: Array.isArray(body.tags) ? body.tags : ['本地导入'],
    articles: (Array.isArray(body.articles) ? body.articles : []).map((a: any) => ({
      title: a.title || '',
      titleTranslate: a.titleTranslate || '',
      text: a.text || '',
      textTranslate: a.textTranslate || '',
    })),
    updatedAt: new Date().toISOString(),
  }

  const idx = list.findIndex(v => v.id === entry.id)
  if (idx > -1) list[idx] = entry
  else list.push(entry)

  await writeLocalArticles(list)
  return { ok: true, count: list.length, id: entry.id }
})
