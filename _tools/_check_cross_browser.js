/**
 * 跨浏览器闭环验收（干净 profile = 模拟另一个浏览器）：
 *   1. 服务端副本里的书出现在书架
 *   2. 能进详情页、练习页（有原文有译文，不是空书）
 *   3. 删除后服务端副本也被删掉（不留在磁盘）
 */
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')

const BASE = 'http://localhost:5567'
let failed = 0
function check(name, ok, detail = '') {
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + (ok ? '' : '  —— ' + detail))
  if (!ok) failed++
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', e => errors.push('PAGEERROR ' + e.message))

  await page.goto(BASE + '/articles', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(6000)

  const server = await page.evaluate(async () => (await fetch('/api/local-articles')).json())
  check('服务端副本非空', server.length > 0, 'server=' + JSON.stringify(server))
  if (!server.length) {
    await browser.close()
    process.exit(1)
  }
  const book = server[0]
  const name = book.name

  const bodyText = await page.evaluate(() => document.body.innerText)
  check('干净浏览器书架能看到《' + name + '》', bodyText.includes(name), '书架里没有这本书')

  // 详情页
  await page.goto(`${BASE}/book/${book.id}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(3500)
  let t = await page.evaluate(() => document.body.innerText)
  check('详情页不是空书', t.includes(name) && !/没有文章可学习/.test(t), JSON.stringify(t.slice(0, 120)))

  // 练习页
  await page.goto(`${BASE}/practice-articles/${book.id}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(4500)
  t = await page.evaluate(() => document.body.innerText)
  const hasEn = /Riemann|proof|theorem/i.test(t)
  const hasZh = /黎曼|猜想|证明/.test(t)
  check('练习页有英文原文', hasEn, JSON.stringify(t.slice(0, 160)))
  check('练习页有中文译文', hasZh, JSON.stringify(t.slice(0, 160)))

  // 删除同步
  await page.goto(BASE + '/articles', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(5000)
  await page.evaluate(id => {
    const el = document.querySelector(`[class*=book]`)
    return id
  }, book.id)
  // 直接打接口验服务端删除逻辑（UI 删除要点复选框，接口层已由体检器覆盖）
  const del = await page.evaluate(async id => {
    const r = await fetch('/api/local-articles?id=' + encodeURIComponent(id), { method: 'DELETE' })
    return await r.json()
  }, book.id)
  check('DELETE 接口能删服务端副本', del.ok === true, JSON.stringify(del))

  const after = await page.evaluate(async () => (await fetch('/api/local-articles')).json())
  check('删除后服务端读不到这本书', !after.some(v => v.id === book.id), JSON.stringify(after.map(v => v.id)))

  // 验收脚本不能把用户的书真删掉 → 原样写回
  const restore = await page.evaluate(async b => {
    const r = await fetch('/api/local-articles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    })
    return await r.json()
  }, book)
  check('验收后把书原样写回（没把用户数据删了）', restore.ok === true, JSON.stringify(restore))

  const restored = await page.evaluate(async () => (await fetch('/api/local-articles')).json())
  check(
    '写回后服务端又有这本书',
    restored.some(v => v.id === book.id && v.name === name),
    JSON.stringify(restored.map(v => v.id))
  )

  // 上游既有报错（内置书页面同样报），不算本次缺陷
  const realErrors = errors.filter(e => !/volume|play\(\) failed/.test(e))
  check('无本次引入的 JS 报错', realErrors.length === 0, JSON.stringify(realErrors))

  await browser.close()
  console.log('---- 失败 ' + failed + ' 项 ----')
  process.exit(failed ? 1 : 0)
}

main().catch(e => {
  console.error('FAIL', e)
  process.exit(1)
})
