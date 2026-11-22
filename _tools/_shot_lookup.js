/**
 * 查词浮层截图（视觉模型验收用）
 * 输出：_shots/lookup_hit.png（普通命中）、_shots/lookup_form.png（变形词命中，看「原形」标注）
 *
 * 注意：每次截图都**重新加载页面** —— 浮层是 Teleport 出来的，手动 remove 节点会让
 * Vue 的 visible 状态和 DOM 脱节，下一次点击就不冒泡了。
 */
const fs = require('fs')
const { chromium } = require('./_playwright')

const BASE = 'http://localhost:5567'
const path = require('path')
const OUT = path.join(__dirname, '..', '_shots')

async function main() {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
  const page = await ctx.newPage()

  await page.goto(BASE + '/articles', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(6000)
  const bookId = await page
    .evaluate(async () => (await fetch('/api/local-articles')).json())
    .then(l => l[0] && l[0].id)

  await page.goto(`${BASE}/practice-articles/${bookId}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(6000)
  await page.evaluate(() => {
    document.querySelectorAll('.modal-mask, .modal-root').forEach(el => el.remove())
  })
  await page.waitForTimeout(300)

  const candidates = await page.evaluate(() => {
    const scope = document.querySelector('.typing-article, .article-content, main, .content') || document.body
    const seen = new Set()
    const out = []
    for (const n of scope.querySelectorAll('span')) {
      const t = (n.textContent || '').trim()
      if (!/^[a-zA-Z]{3,12}$/.test(t) || n.children.length) continue
      if (n.closest('nav, header, .nav, .menu, button, a')) continue
      const k = t.toLowerCase()
      if (seen.has(k)) continue
      seen.add(k)
      out.push(t)
      if (out.length > 80) break
    }
    return out
  })

  // 找一个「命中原形、且是变形」的词（接口返回 baseWord）→ 展示「原形」标注
  let formWord = null
  let plainWord = null
  for (const w of candidates) {
    const r = await fetch(`${BASE}/api/word-query?word=${encodeURIComponent(w)}`).catch(() => null)
    if (!r || r.status !== 200) continue
    const j = await r.json()
    if (!formWord && j?.data?.baseWord) formWord = w
    if (!plainWord && !j?.data?.baseWord) plainWord = w
  }
  console.log('变形词样本:', formWord, '| 普通命中:', plainWord)

  const shoot = async (word, file) => {
    if (!word) return
    // 每次都重新加载页面，保证浮层状态干净
    await page.goto(`${BASE}/practice-articles/${bookId}`, { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(5000)
    await page.evaluate(() => {
      document.querySelectorAll('.modal-mask, .modal-root').forEach(el => el.remove())
    })
    await page.waitForTimeout(300)

    const ok = await page.evaluate(w => {
      const scope = document.querySelector('.typing-article, .article-content, main, .content') || document.body
      const el = Array.from(scope.querySelectorAll('span')).find(n => {
        const t = (n.textContent || '').trim().toLowerCase()
        return t === w.toLowerCase() && !n.children.length && !n.closest('nav, header, .nav, .menu, button, a')
      })
      if (!el) return false
      el.setAttribute('data-wl-probe', '1')
      el.scrollIntoView({ block: 'center' })
      return true
    }, word)
    if (!ok) return console.log('定位失败:', word)
    await page.evaluate(() => {
      document.querySelector('[data-wl-probe]').dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
    })
    await page.waitForSelector('.word-lookup-popover', { timeout: 8000 })
    await page
      .waitForFunction(() => {
        const el = document.querySelector('.word-lookup-popover')
        return el && !(el.innerText || '').includes('查询中')
      }, { timeout: 5000 })
      .catch(() => {})
    await page.waitForTimeout(500)
    await page.screenshot({ path: OUT + '/' + file })
    const text = await page.evaluate(() => document.querySelector('.word-lookup-popover')?.innerText || '')
    console.log(`shot ${file}: ` + JSON.stringify(text.replace(/\s+/g, ' ').slice(0, 220)))
  }

  await shoot(plainWord, 'lookup_hit.png')
  await shoot(formWord, 'lookup_form.png')

  await browser.close()
}
main().catch(e => {
  console.error('FAIL', e)
  process.exit(1)
})
