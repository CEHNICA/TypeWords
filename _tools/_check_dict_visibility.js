// 逐个分类、逐个标签页点开，把每个标签下真正可见的册子全扒出来
const { chromium } = require('./_playwright')
const path = require('path')
const fs = require('fs')
const BASE = 'http://localhost:5567'
const OUT = path.join(__dirname, '..', '_shots')

;(async () => {
  const b = await chromium.launch({ headless: true })
  const ctx = await b.newContext({ viewport: { width: 1600, height: 1000 } })
  const p = await ctx.newPage()
  const errors = []
  p.on('pageerror', e => errors.push('PAGEERROR: ' + e.message))
  await p.goto(BASE + '/dict-list', { waitUntil: 'domcontentloaded' })
  await p.waitForTimeout(2500)

  const groups = await p.$$('.tags')
  console.log('分类组数 =', groups.length)
  const report = []
  for (let gi = 0; gi < groups.length; gi++) {
    const cat = await groups[gi].evaluate(el => {
      const c = el.parentElement.querySelector('.category')
      return c ? c.textContent.trim() : '?'
    })
    const tags = await groups[gi].evaluate(el => Array.from(el.querySelectorAll('.tag')).map(t => t.textContent.trim()))
    console.log(`\n=== ${cat} === 标签: ${tags.join(' | ')}`)
    for (let ti = 0; ti < tags.length; ti++) {
      await groups[gi].$$eval('.tag', (els, i) => els[i].click(), ti)
      await p.waitForTimeout(350)
      const books = await groups[gi].evaluate(el => {
        const root = el.parentElement.parentElement
        const wrap = root.querySelector('.flex.gap-4.flex-wrap') || root.lastElementChild
        return Array.from(wrap.children).map(c => c.textContent.replace(/\s+/g, ' ').trim())
      })
      console.log(`  [${tags[ti]}] ${books.length} 册 :: ${books.join(' ; ')}`)
      report.push({ cat, tag: tags[ti], books })
    }
  }
  fs.writeFileSync(path.join(OUT, 'dict_visibility.json'), JSON.stringify(report, null, 2), 'utf8')
  console.log('\npageerrors:', errors.slice(0, 5).join(' | ') || '(无)')
  await b.close()
})()
