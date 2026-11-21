import { readLocalArticles, writeLocalArticles } from '../utils/localArticles'

/**
 * DELETE /api/local-articles?id=xxx
 * 删掉服务端副本（用户在文章页删书时同步调用）。
 *
 * 不删的话：书从本机书架消失，但服务端副本还在 →
 *   - 换台浏览器打开还会看到（幽灵书）；
 *   - 再次 push 时又被当成「服务端已有」跳过，永远删不干净。
 */
export default defineEventHandler(async event => {
  const id = getQuery(event).id
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: '缺少 id' })
  }

  const list = await readLocalArticles()
  const next = list.filter(v => v.id !== String(id))
  if (next.length !== list.length) {
    await writeLocalArticles(next)
  }
  return { ok: true, removed: list.length - next.length, count: next.length }
})
