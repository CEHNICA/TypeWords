import { loadForms, loadIndex } from '../utils/wordIndex'

/**
 * 服务启动时预热本地词典索引 + 词形映射表。
 *
 * 不做预热的话：第一个查词请求要现读 20MB JSON + JSON.parse + 建 Map（约 400ms），
 * 用户看到的就是「点完词浮层空一下才出字」。
 * 预热之后索引常驻内存，查词就是纯 O(1) 查表，**零延迟**。
 */
export default defineNitroPlugin(async () => {
  const t0 = Date.now()
  const map = await loadIndex()
  const forms = await loadForms()
  if (map.size) {
    console.log(
      `[word-index] 预热完成：${map.size} 词条 + ${forms.size} 条词形映射，用时 ${Date.now() - t0}ms`
    )
  } else {
    console.warn('[word-index] 索引为空，先跑 node scripts/build-word-index.mjs 生成')
  }
})
