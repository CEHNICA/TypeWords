// 跟打页正文截图（元素级），用于视觉模型验收：
// 1) 确认单词之间视觉上有空格
// 2) 确认没有 hover 查词浮层残留（把鼠标挪走后应消失）
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')
const path = require('path')
const fs = require('fs')

const SHOTS = path.join(__dirname, '..', '_shots')
const BASE = 'http://localhost:5567'

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

  // 页面若有遮罩弹窗，先看看是什么
  const modalInfo = await p.evaluate(() => {
    const m = document.querySelector('.modal-root')
    return m ? (m.innerText || '').replace(/\s+/g, ' ').slice(0, 300) : '(无弹窗)'
  })
  console.log('=== modal ===', modalInfo)

  // 关掉上游既有的「重要提示」引导弹窗，拿到干净版面
  const closed = await p.evaluate(() => {
    const root = document.querySelector('.modal-root')
    if (!root) return 'no-modal'
    const btns = Array.from(root.querySelectorAll('button, .base-button, [class*="btn"]'))
    const hit = btns.find(b => /关闭|close|确定|我知道了/i.test((b.innerText || '').trim()))
    if (hit) { hit.click(); return 'clicked:' + (hit.innerText || '').trim() }
    const close = root.querySelector('[class*="close"], .icon-close')
    if (close) { close.click(); return 'clicked-close-icon' }
    return 'no-button-found'
  })
  console.log('=== modal close ===', closed)
  await p.waitForTimeout(1500)

  // 先故意 hover 一个单词，再看浮层是否出现（确认 Elevation 是不是 hover 产物）
  await p.evaluate(() => {
    const el = document.querySelector('.article-content .word .word-wrap')
    if (el) el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))
  })
  await p.waitForTimeout(1200)
  const withHover = await p.evaluate(() => document.body.innerText)
  await p.screenshot({ path: path.join(SHOTS, 'tb_article_hover.png'), fullPage: false })

  // 移开鼠标到页面角落，等浮层消失
  await p.mouse.move(5, 5)
  await p.waitForTimeout(1500)
  const noHover = await p.evaluate(() => document.body.innerText)
  await p.screenshot({ path: path.join(SHOTS, 'tb_article.png'), fullPage: false })

  // 元素级截图：只截正文区域，视觉模型好读
  const el = p.locator('.article-content').first()
  if (await el.count()) {
    await el.screenshot({ path: path.join(SHOTS, 'tb_article_el.png') })
  }
  // 左边篇目列表
  const side = p.locator('.book-list, .article-list, aside').first()
  if (await side.count()) {
    try { await side.screenshot({ path: path.join(SHOTS, 'tb_side.png') }) } catch (e) {}
  }
  await p.screenshot({ path: path.join(SHOTS, 'tb_practice2.png'), fullPage: false })

  fs.writeFileSync(path.join(SHOTS, 'tb_hover.txt'), withHover, 'utf8')
  fs.writeFileSync(path.join(SHOTS, 'tb_nohover.txt'), noHover, 'utf8')

  const cut = s => s.replace(/\s+/g, ' ').slice(0, 700)
  console.log('=== hover 时正文 ===')
  console.log(cut(withHover))
  console.log('=== 移开鼠标后正文 ===')
  console.log(cut(noHover))
  console.log('=== Elevation 出现次数 hover/nohover ===')
  console.log((withHover.match(/Elevation/g) || []).length, (noHover.match(/Elevation/g) || []).length)

  await b.close()
})()
