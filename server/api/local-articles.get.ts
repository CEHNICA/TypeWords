import { readLocalArticles } from '../utils/localArticles'

/**
 * GET /api/local-articles
 * 返回本地导入的文章（服务端副本）。前端文章页用它合并书架。
 */
export default defineEventHandler(async () => {
  return await readLocalArticles()
})
