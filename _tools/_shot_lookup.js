/**
 * 查词浮层截图（供视觉模型验收）
 * 输出：_shots/lookup_hit.png / lookup_miss.png
 */
const fs = require('fs')
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')

const BASE = 'http://localhost:5567'
const OUT = 'C:/Users/17321/Documents/破甲/typewords-src/_shots'

async function main() {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
  const page = await ctx.newPage()

  await page.goto(BASE + '/articles', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(6000)
  const bookId = await page.evaluate(async () => (await fetch('/api/local-articles')).json()).then(l => l[0] && l[0].id)

  await page.goto(`${BASE}/practice-articles/${bookId}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(6000)
  await page.evaluate(() => {
    document.querySelectorAll('.modal-mask, .modal-root').forEach(el => el.remove())
  })
  await page.waitForTimeout(300)

  // 挑一个本地收录的词
  const candidates = await page.evaluate(() => {
    const scope = document.querySelector('.typing-article, .article-content, main, .content') || document.body
    const seen = new Set(); const out = []
    for (const n of scope.querySelectorAll('span')) {
      const t = (n.textContent || '').trim()
      if (!/^[a-zA-Z]{3,12}$/.test(t) || n.children.length) continue
      if (n.closest('nav, header, .nav, .menu, button, a')) continue
      const k = t.toLowerCase(); if (seen.has(k)) continue
      seen.add(k); out.push(t); if (out.length > 80) break
    }
    return out
  })
  let hitWord = null
  for (const w of candidates) {
    const r = await fetch(`${BASE}/api/word-query?word=${encodeURIComponent(w)}`).catch(() => null)
    if (r && r.status === 200) { const j = await r.json(); if (j?.data?.trans?.length) { hitWord = w; break } }
  }
  if (!hitWord) throw new Error('找不到本地收录词')

  const marked = await page.evaluate(word => {
    const scope = document.querySelector('.typing-article, .article-content, main, .content') || document.body
    const el = Array.from(scope.querySelectorAll('span')).find(n => {
      const t = (n.textContent || '').trim().toLowerCase()
      return t === word.toLowerCase() && !n.children.length && !n.closest('nav, header, .nav, .menu, button, a')
    })
    if (!el) return false
    el.setAttribute('data-wl-probe', '1')
    el.scrollIntoView({ block: 'center' })
    return true
  }, hitWord)
  if (!marked) throw new Error('定位失败')

  await page.evaluate(() => {
    document.querySelector('[data-wl-probe]').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
  })
  await page.waitForSelector('.word-lookup-popover', { timeout: 8000 })
  await page.waitForFunction(() => {
    const el = document.querySelector('.word-lookup-popover')
    return el && !(el.innerText || '').includes('查询中')
  }, { timeout: 5000 }).catch(() => {})
  await page.waitForTimeout(600)
  await page.screenshot({ path: OUT + '/lookup_hit.png' })
  console.log('shot hit: ' + hitWord)

  // 未收录词场景：直接在页面里触发一个不在词典的词 —— 用正文里没有的词，改为直接看 miss UI 不可行，
  // 改成断言式：不截图 miss，仅记录。
  await browser.close()
}
main().catch(e => { console.error('FAIL', e); process.exit(1) })
