// 探测跟打页版面：目录抽屉是否遮挡正文、遮罩能不能关掉
const { chromium } = require('./_playwright')
const path = require('path')

const SHOTS = path.join(__dirname, '..', '_shots')
const BASE = 'http://localhost:5567'

;(async () => {
  const b = await chromium.launch({ headless: true })
  const ctx = await b.newContext({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 })
  const p = await ctx.newPage()

  await p.goto(BASE + '/book-list', { waitUntil: 'domcontentloaded' })
  await p.waitForTimeout(2500)
  await p.getByText('莱芜小学英语 三年级上册', { exact: true }).first().click()
  await p.waitForTimeout(2500)
  await p.getByText("Lesson 1 Hi! I'm Jenny", { exact: false }).first().click()
  await p.waitForTimeout(1200)
  await p.locator('.base-button', { hasText: /学习|Learn|Start/i }).first().click()
  await p.waitForTimeout(3500)

  const dump = () =>
    p.evaluate(() => {
      const out = { masks: [], drawers: [], articleRect: null }
      document.querySelectorAll('.modal-mask, .mask, [class*="mask"]').forEach(m => {
        const r = m.getBoundingClientRect()
        const cs = getComputedStyle(m)
        out.masks.push({
          cls: m.className,
          display: cs.display,
          visible: r.width > 0 && r.height > 0,
          rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
          z: cs.zIndex,
          pos: cs.position
        })
      })
      const art = document.querySelector('.article-content')
      if (art) {
        const r = art.getBoundingClientRect()
        out.articleRect = [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]
      }
      // 找出覆盖在正文右侧的可视面板
      const vw = window.innerWidth
      document.querySelectorAll('div,aside,section').forEach(el => {
        const r = el.getBoundingClientRect()
        if (r.width > 120 && r.height > 200 && r.x > vw * 0.45) {
          const cs = getComputedStyle(el)
          if (cs.position === 'fixed' || cs.position === 'absolute') {
            out.drawers.push({
              cls: String(el.className).slice(0, 90),
              pos: cs.position,
              z: cs.zIndex,
              bg: cs.backgroundColor,
              rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]
            })
          }
        }
      })
      out.drawers = out.drawers.slice(0, 8)
      return out
    })

  console.log('=== 初始版面 ===')
  console.log(JSON.stringify(await dump(), null, 1))

  // 关闭「重要提示」
  await p.evaluate(() => {
    const root = document.querySelector('.modal-root')
    const hit = root && Array.from(root.querySelectorAll('button, .base-button')).find(b => /关闭/i.test(b.innerText || ''))
    if (hit) hit.click()
  })
  await p.waitForTimeout(1200)

  console.log('=== 关掉重要提示后 ===')
  console.log(JSON.stringify(await dump(), null, 1))

  // 点工具栏「面板」开关收起目录抽屉
  const clicked = await p.evaluate(() => {
    const svg = document.querySelector('.icon-fluent-text-list-abc-uppercase-ltr-20-regular')
    const btn = svg ? svg.closest('button, div, span') : null
    if (btn) { btn.click(); return 'clicked-svg:' + String(btn.className).slice(0, 50) }
    const icons = Array.from(document.querySelectorAll('svg'))
    const cand = icons.find(s => /text-list|list/i.test(String(s.className)))
    if (cand) { const b = cand.closest('button, div, span'); b.click(); return 'clicked-cand:' + String(cand.className).slice(0, 60) }
    return 'not-found'
  })
  console.log('=== 面板开关 ===', clicked)
  await p.waitForTimeout(1500)
  console.log('=== 点遮罩后 ===')
  console.log(JSON.stringify(await dump(), null, 1))
  await p.screenshot({ path: path.join(SHOTS, 'tb_practice3.png'), fullPage: false })
  const el = p.locator('.article-content').first()
  if (await el.count()) await el.screenshot({ path: path.join(SHOTS, 'tb_article_el2.png') })
  const vis = await p.evaluate(() => {
    const pw = document.querySelector('.panel-wrap')
    return { hasPanel: pw ? pw.className : '(无)', showPanelVisible: pw ? getComputedStyle(pw).backgroundColor : '-' }
  })
  console.log('=== panel 状态 ===', JSON.stringify(vis))

  await b.close()
})()
