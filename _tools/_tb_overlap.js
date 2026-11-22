// 找出到底谁遮住了正文：列出所有 fixed/sticky 元素 + 与正文矩形的重叠
const { chromium } = require('./_playwright')
const path = require('path')
const BASE = 'http://localhost:5567'
const SHOTS = path.join(__dirname, '..', '_shots')

;(async () => {
  const b = await chromium.launch({ headless: true })
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()
  await p.goto(BASE + '/book-list', { waitUntil: 'domcontentloaded' })
  await p.waitForTimeout(2500)
  await p.getByText('莱芜小学英语 三年级上册', { exact: true }).first().click()
  await p.waitForTimeout(2500)
  await p.getByText("Lesson 1 Hi! I'm Jenny", { exact: false }).first().click()
  await p.waitForTimeout(1200)
  await p.locator('.base-button', { hasText: /学习|Learn|Start/i }).first().click()
  await p.waitForTimeout(3500)
  await p.evaluate(() => {
    const root = document.querySelector('.modal-root')
    const hit = root && Array.from(root.querySelectorAll('button, .base-button')).find(x => /关闭/i.test(x.innerText || ''))
    if (hit) hit.click()
  })
  await p.waitForTimeout(1200)

  const info = await p.evaluate(() => {
    const art = document.querySelector('.article-content')
    const ar = art ? art.getBoundingClientRect() : null
    const out = { article: ar ? [ar.x, ar.y, ar.width, ar.height] : null, fixed: [], overlaps: [] }
    document.querySelectorAll('*').forEach(el => {
      const cs = getComputedStyle(el)
      const r = el.getBoundingClientRect()
      if (r.width < 5 || r.height < 5) return
      if (cs.position === 'fixed' || cs.position === 'sticky' || cs.position === 'absolute') {
        out.fixed.push({
          tag: el.tagName,
          cls: String(el.className).slice(0, 70),
          pos: cs.position,
          z: cs.zIndex,
          bg: cs.backgroundColor,
          rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
          text: (el.innerText || '').replace(/\s+/g, ' ').slice(0, 40)
        })
      }
    })
    // 命中测试：文章正文中心点上最上面的元素是谁
    if (ar) {
      const pts = [
        [ar.x + 20, ar.y + 20],
        [ar.x + ar.width - 60, ar.y + 20],
        [ar.x + ar.width - 60, ar.y + 60],
        [ar.x + 200, ar.y + 40]
      ]
      pts.forEach(([x, y], i) => {
        const els = document.elementsFromPoint(x, y).slice(0, 4).map(e => ({
          tag: e.tagName,
          cls: String(e.className).slice(0, 60),
          pos: getComputedStyle(e).position,
          z: getComputedStyle(e).zIndex,
          text: (e.innerText || '').replace(/\s+/g, ' ').slice(0, 40)
        }))
        out.overlaps.push({ pt: [Math.round(x), Math.round(y)], els })
      })
    }
    out.fixed = out.fixed.slice(0, 25)
    return out
  })
  console.log(JSON.stringify(info, null, 1))
  await b.close()
})()
