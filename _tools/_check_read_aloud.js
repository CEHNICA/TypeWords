/**
 * 实测：课文朗读是不是「一句一句」。
 *
 * 判据（抓网络请求，不靠听）：
 *   1. 每句在 DOM 里是独立元素（.sentence-item）
 *   2. 点第 N 句的播放按钮 → 发出的音频请求 le 参数只包含**这一句**的文本
 *      （不是整段、不是整篇）
 */
const { chromium } = require('./_playwright')

const BASE = process.env.TW_BASE_URL || 'http://localhost:5567'
const BOOK = process.env.TW_BOOK || '262'
const IDX = parseInt(process.env.TW_IDX || '2', 10)

let fails = 0
function check(cond, msg, extra) {
  console.log((cond ? '[PASS] ' : '[FAIL] ') + msg + (extra ? '  ' + extra : ''))
  if (!cond) fails++
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  const audioReqs = []
  page.on('request', (r) => {
    const u = r.url()
    if (/dictvoice|tts|speech|audio/i.test(u)) {
      const q = (u.match(/[?&](le|audio)=([^&]*)/) || [])[2]
      audioReqs.push({ url: u.slice(0, 200), le: q ? decodeURIComponent(q) : null })
    }
  })

  await page.goto(`${BASE}/book/${BOOK}`, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.common-list-item', { timeout: 30000 })
  // 列表里选一篇（非目录页），正文才会渲染
  await page.locator('.common-list-item').nth(1).click()
  await page.waitForSelector('.sentence-item', { timeout: 30000 })
  await page.waitForTimeout(1200)

  // 1. 每句独立 DOM
  const items = page.locator('.sentence-item')
  const n = await items.count()
  check(n > 5, `句子渲染成独立元素（.sentence-item）`, `共 ${n} 句`)

  // 每句的词数（证明不是整段塞一行）
  const perSentence = await page.evaluate(() =>
    Array.from(document.querySelectorAll('.sentence-item')).slice(0, 12).map((el) => ({
      words: el.querySelectorAll('.word').length,
      text: (el.textContent || '').trim().slice(0, 70),
    }))
  )
  const multi = perSentence.filter((s) => s.words > 25)
  check(multi.length === 0, '没有「一句里塞几十个词」的巨型句', JSON.stringify(multi.slice(0, 3)))

  // 2. 点第 IDX 句的播放按钮，抓音频请求
  const target = items.nth(IDX)
  const before = audioReqs.length
  await target.locator('svg, button').last().click()
  await page.waitForTimeout(2500)

  const fired = audioReqs.slice(before)
  check(fired.length > 0, '点击句子播放按钮确实发起了音频请求', `共 ${fired.length} 个`)

  const withText = fired.filter((r) => r.le && r.le.trim())
  fired.forEach((r) => console.log('   req:', r.url, '| 朗读文本 =', JSON.stringify(r.le)))
  check(withText.length > 0, '音频请求带朗读文本（audio/le 参数）')
  if (withText.length) {
    const le = withText[0].le
    const targetText = perSentence.length > IDX ? perSentence[IDX].text : ''
    console.log('   朗读文本 =', JSON.stringify(le.slice(0, 120)))
    console.log('   该句 DOM =', JSON.stringify(targetText))
    const norm = (s) => (s || '').replace(/\s+/g, '')
    check(
      !!targetText.slice(0, 25) && norm(le).includes(norm(targetText.slice(0, 25))),
      '朗读文本就是这一句本身'
    )
    // 一句的文本长度不该是整段的量级
    check(le.length < 200, '朗读文本长度像「一句」而不是整段/整篇', `长度 ${le.length}`)
    // 也验一下不是整篇：整篇 9_1 有 45 篇，绝对不止 200 字符
    check(!le.includes('An Invention'), '朗读文本不包含别的课文内容')
  }

  await browser.close()
  console.log(fails === 0 ? '\n全部通过' : `\n失败 ${fails} 项`)
  process.exit(fails === 0 ? 0 : 1)
})()
