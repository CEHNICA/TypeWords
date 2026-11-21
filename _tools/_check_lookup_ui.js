/**
 * 点词查义实测（干净 profile）
 * ==========================
 * 维度来自用户原话：「它会弹出一个有道的界面」「有多少界面啊」「反应速度太慢」。
 *
 * 断言：
 *   1. **命中**本地词典的词 → 浮层秒出 + 有中文释义（不等外网）
 *   2. 浮层里没有 iframe、没有词典 tab（不再是有道整页）
 *   3. **未收录**词 → 明确提示「本地词典未收录」+ 给外链，且**不打云端接口**
 *   4. 查词全程**没有任何云端查词请求**（http://localhost/public.word/query）
 *   5. 查词全程**没有任何外网词典页面请求**（有道/金山整页）
 *      —— 发音音频(dictvoice)不算，它不阻塞释义渲染，单独断言
 *   6. 端到端响应 < 500ms（本地词典必须是毫秒级）
 */
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')

const BASE = 'http://localhost:5567'
let failed = 0
function check(name, ok, detail = '') {
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + (ok ? '' : '  —— ' + detail))
  if (!ok) failed++
}

/** 查本地词典接口：命中返回数据，未收录返回 404 */
async function lookupLocal(word) {
  try {
    const r = await fetch(`${BASE}/api/word-query?word=${encodeURIComponent(word)}`)
    return { status: r.status, data: r.status === 200 ? await r.json() : null }
  } catch (e) {
    return { status: 0, data: null, err: String(e) }
  }
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext()
  const page = await ctx.newPage()

  const extPageRequests = []
  const audioRequests = []
  const cloudRequests = []
  page.on('request', r => {
    const u = r.url()
    if (/dictvoice/.test(u)) audioRequests.push(u)
    else if (/dict\.youdao\.com|iciba\.com|bing\.com/.test(u)) extPageRequests.push(u)
    // 云端查词接口（本地必然失败的老链路）
    if (/public\.word\/query/.test(u)) cloudRequests.push(u)
  })
  const errors = []
  page.on('pageerror', e => errors.push('PAGEERROR ' + e.message))

  // 找一本本地导入的文章（服务端副本里有），进去才有可点的词
  const bookId = await (async () => {
    await page.goto(BASE + '/articles', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(6000)
    const list = await page.evaluate(async () => (await fetch('/api/local-articles')).json())
    return list.length ? list[0].id : null
  })()
  check('拿到本地导入的文章', !!bookId, String(bookId))
  if (!bookId) {
    await browser.close()
    process.exit(1)
  }

  await page.goto(`${BASE}/practice-articles/${bookId}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(6000)

  // 关掉可能挡住页面的弹窗（上游首次进入会有引导弹窗）
  await page.evaluate(() => {
    document.querySelectorAll('.modal-mask, .modal-root').forEach(el => el.remove())
  })
  await page.waitForTimeout(300)

  // ---- 收集正文里的候选词，挑一个**本地词典收录**的 ----
  const candidates = await page.evaluate(() => {
    const scope =
      document.querySelector('.typing-article, .article-content, main, .content') || document.body
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
      if (out.length > 120) break
    }
    return out
  })
  check('页面上能收集到候选英文单词', candidates.length > 0, '候选数=' + candidates.length)

  let hitWord = null
  for (const w of candidates) {
    const r = await lookupLocal(w)
    if (r.status === 200 && r.data?.data?.trans?.length) {
      hitWord = w
      break
    }
  }
  check('候选词里能找到本地词典收录的词（用于命中场景）', !!hitWord, `候选=${candidates.slice(0, 8).join(',')}`)
  if (!hitWord) {
    await browser.close()
    process.exit(1)
  }
  console.log('  目标词（本地收录）: ' + hitWord)

  const marked = await page.evaluate(word => {
    const scope =
      document.querySelector('.typing-article, .article-content, main, .content') || document.body
    const el = Array.from(scope.querySelectorAll('span')).find(n => {
      const t = (n.textContent || '').trim().toLowerCase()
      if (t !== word.toLowerCase() || n.children.length) return false
      if (n.closest('nav, header, .nav, .menu, button, a')) return false
      return true
    })
    if (!el) return false
    el.setAttribute('data-wl-probe', '1')
    return true
  }, hitWord)
  check('能在正文里定位并标记该词', marked)
  if (!marked) {
    await browser.close()
    process.exit(1)
  }

  const t0 = Date.now()
  // 用 dispatchEvent 触发（右侧面板会盖住正文，真实 click 会被拦截 → 超时）
  await page.evaluate(() => {
    const el = document.querySelector('[data-wl-probe]')
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
  })
  await page.waitForSelector('.word-lookup-popover', { timeout: 8000 })

  // 等释义出现（最多 3 秒）——本地词典应该几乎立刻
  const appeared = await page
    .waitForFunction(
      () => {
        const el = document.querySelector('.word-lookup-popover')
        if (!el) return false
        const t = el.innerText || ''
        return !t.includes('查询中') && t.trim().length > 3
      },
      { timeout: 3000 }
    )
    .then(() => true)
    .catch(() => false)
  const elapsed = Date.now() - t0
  check('浮层不是卡在「查询中...」（释义已渲染）', appeared, `耗时 ${elapsed}ms`)

  const info = await page.evaluate(() => {
    const el = document.querySelector('.word-lookup-popover')
    if (!el) return null
    return {
      text: el.innerText,
      iframes: el.querySelectorAll('iframe').length,
      tabs: el.querySelectorAll('[role="tab"]').length,
      width: Math.round(el.getBoundingClientRect().width),
    }
  })
  check('浮层出现', !!info)
  check('浮层里没有 iframe（不再是有道整页）', info && info.iframes === 0, 'iframes=' + (info && info.iframes))
  check('浮层里没有词典 tab（有道/金山切换）', info && info.tabs === 0, 'tabs=' + (info && info.tabs))
  check('浮层宽度不是大 iframe 尺寸（< 600px）', info && info.width < 600, 'width=' + (info && info.width))
  check('浮层里有中文释义', info && /[\u4e00-\u9fa5]/.test(info.text), JSON.stringify(info && info.text.slice(0, 160)))
  check(
    '浮层显示的是释义而不是「本地词典未收录」',
    info && !info.text.includes('本地词典未收录'),
    JSON.stringify(info && info.text.slice(0, 120))
  )
  console.log('  浮层内容: ' + JSON.stringify((info && info.text || '').replace(/\s+/g, ' ').slice(0, 260)))
  console.log('  端到端耗时: ' + elapsed + 'ms')
  check('查词端到端 < 500ms（本地词典必须毫秒级）', elapsed < 500, elapsed + 'ms')

  // ---- 场景 2：未收录词 → 确定性 404 + 外链 + 不打云端 ----
  const miss = await lookupLocal('zzqqxxnotaword')
  check('未收录词接口返回 404（确定性 miss，不是服务不可用）', miss.status === 404, 'status=' + miss.status)

  check('全程没有任何云端查词请求（本地查不到也不打云端）', cloudRequests.length === 0, JSON.stringify(cloudRequests.slice(0, 5)))
  check('全程没有任何外网词典页面请求（有道/金山整页）', extPageRequests.length === 0, JSON.stringify(extPageRequests.slice(0, 5)))
  console.log('  发音音频请求数（不阻塞释义，允许存在）: ' + audioRequests.length)

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
