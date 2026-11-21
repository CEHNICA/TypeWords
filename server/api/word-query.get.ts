import { ensureIndex, lookupLocalWord } from '../utils/wordIndex'

/**
 * GET /api/word-query?word=xxx
 * 本地离线查词：查本地词库索引，零网络。
 *
 * 状态码语义（前端靠这个区分「没这个词」和「服务不可用」）：
 *   200 → 命中
 *   404 → 词典服务正常，但这个词没收录 → 前端**直接给外链**，别再打云端
 *   503 → 索引没构建 / 服务端不可用 → 前端才走云端兜底
 */
export default defineEventHandler(async event => {
  const word = String(getQuery(event).word || '').trim()
  if (!word) {
    throw createError({ statusCode: 400, statusMessage: '缺少 word' })
  }

  // 必须 await ensureIndex()：首次加载前 isIndexReady() 恒为 false，
  // 那样第一个查词请求会永远 503。
  if (!(await ensureIndex())) {
    throw createError({ statusCode: 503, statusMessage: '本地词典索引未就绪' })
  }

  const data = await lookupLocalWord(word)
  if (!data) {
    throw createError({ statusCode: 404, statusMessage: '本地词典未收录' })
  }
  return { success: true, data }
})
