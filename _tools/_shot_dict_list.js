// 给「青少年英语」分组截个图，供视觉模型验收
const { chromium } = require('./_playwright')
const path = require('path')
const BASE = 'http://localhost:5567'
const OUT = path.join(__dirname, '..', '_shots')

;(async () => {
  const b = await chromium.launch({ headless: true })
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1100 }, deviceScaleFactor: 1 })
  const p = await ctx.newPage()
  await p.goto(BASE + '/dict-list', { waitUntil: 'domcontentloaded' })
  await p.waitForTimeout(2500)
  // 滚到「青少年英语」那一组
  const handle = await p.evaluateHandle(() => {
    const el = Array.from(document.querySelectorAll('.category')).find(e => e.textContent.includes('青少年英语'))
    return el ? el.parentElement.parentElement : null
  })
  const el = handle.asElement()
  if (el) {
    await el.scrollIntoViewIfNeeded()
    await p.waitForTimeout(600)
    await el.screenshot({ path: path.join(OUT, 'dict_young.png') })
    console.log('已截图 dict_young.png')
  } else {
    console.log('没找到青少年英语分组')
  }
  await p.screenshot({ path: path.join(OUT, 'dict_list_full.png'), fullPage: true })
  console.log('已截图 dict_list_full.png')
  await b.close()
})()
