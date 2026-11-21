const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')
const path = require('path')
const fs = require('fs')

const SHOTS = path.join(__dirname, '..', '_shots')
const BASE = 'http://localhost:5567'

;(async () => {
  const b = await chromium.launch({ headless: true })
  const ctx = await b.newContext({ viewport: { width: 1280, height: 900 } })
  const p = await ctx.newPage()
  const errors = []
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  p.on('pageerror', e => errors.push('PAGEERROR: ' + e.message))

  await p.goto(BASE + '/book-list', { waitUntil: 'domcontentloaded' })
  await p.waitForTimeout(2500)
  await p.screenshot({ path: path.join(SHOTS, 'tb_booklist.png'), fullPage: true })

  // 进第一本莱芜课本书
  await p.getByText('莱芜小学英语 三年级上册', { exact: true }).first().click()
  await p.waitForTimeout(2500)
  console.log('url after book click =', p.url())
  await p.screenshot({ path: path.join(SHOTS, 'tb_book.png'), fullPage: true })

  // 选中第一篇课文
  const item = p.getByText("Lesson 1 Hi! I'm Jenny", { exact: false }).first()
  await item.click()
  await p.waitForTimeout(1500)
  await p.screenshot({ path: path.join(SHOTS, 'tb_book_selected.png'), fullPage: true })

  // 点「学习」按钮
  const btns = await p.evaluate(() =>
    Array.from(document.querySelectorAll('.base-button')).map(b => (b.innerText || '').trim())
  )
  console.log('buttons =', JSON.stringify(btns))
  const learnBtn = p.locator('.base-button', { hasText: /学习|Learn|Start/i }).first()
  await learnBtn.click()
  await p.waitForTimeout(3500)
  console.log('url after learn click =', p.url())
  await p.screenshot({ path: path.join(SHOTS, 'tb_practice.png'), fullPage: true })
  const t3 = await p.evaluate(() => document.body.innerText)
  fs.writeFileSync(path.join(SHOTS, 'tb_practice.txt'), t3, 'utf8')
  console.log('--- 跟打页文本（前 1800 字）---')
  console.log(t3.slice(0, 1800))

  console.log('--- console errors ---')
  console.log(errors.slice(0, 10).join('\n') || '(无)')
  await b.close()
})()
