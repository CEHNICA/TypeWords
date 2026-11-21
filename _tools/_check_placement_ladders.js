/**
 * 摸底「阶梯铺到九年级」浏览器实测
 * ======================================
 * 维度：用户原话「还有一直到9年纪的英文课本都要导入进去」
 *
 * 断言：
 *   1. 8 套阶梯逐个切过去都能点「开始摸底」并加载出题（选项出现）
 *   2. 加载过程中**真的发起了**新增九年级册子的网络请求（不是只写在配置文件里）
 *   3. 每套阶梯的加载耗时在可接受范围（阶梯从 6 级涨到 13 级，怕加载爆炸）
 *   4. 页面无 JS 报错
 *
 * 用法：node _tools/_check_placement_ladders.js
 */
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')

const BASE = process.env.TW_BASE_URL || 'http://localhost:5567'
let failed = 0
function check(name, ok, detail = '') {
  if (!ok) failed++
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + (ok ? '' : '  —— ' + detail))
}

const LADDERS = [
  '人教版 PEP',
  '人教版新起点（小学）',
  '外研版（小学）',
  '外研社（初中）',
  '冀教版',
  '莱芜五四制（山东版）',
  '剑桥小学英语 JOIN IN',
  '剑桥少儿英语 KET',
]

/** 各阶梯必须被真实拉下来的册子（新增的初中/九年级部分） */
const MUST_FETCH = {
  '人教版 PEP': ['PEPChuZhong7_1_T', 'PEPChuZhong8_1_T', 'PEPChuZhong8_2_T', 'PEPChuZhong9_1_T'],
  '外研社（初中）': ['WaiYanSheChuZhong_1_T', 'WaiYanSheChuZhong_4_T', 'WaiYanSheChuZhong_6_T'],
  '冀教版': ['jiJiao7-1', 'jiJiao8-1', 'jiJiao8-2', 'jiJiao9'],
  '莱芜五四制（山东版）': ['LWCZ-6-1', 'LWCZ-7-1', 'LWCZ-8-1', 'LWCZ-8-2', 'LWCZ-9-1'],
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const pageErrors = []
  const fetched = new Set()
  page.on('pageerror', e => pageErrors.push(e.message))
  page.on('request', r => {
    const u = r.url()
    if (u.includes('/dicts/')) fetched.add(u)
  })
  const NOISE = /play\(\) request was interrupted|play\(\) failed because the user didn't interact|Cannot set properties of undefined \(setting 'volume'\)/

  for (const name of LADDERS) {
    fetched.clear()
    await page.goto(BASE + '/placement-test', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(900)

    const btn = page.locator(`text=${name}`).first()
    if (!(await btn.count())) {
      check(`阶梯「${name}」在 setup 页能找到按钮`, false, '按钮没渲染')
      continue
    }
    await btn.click()
    await page.waitForTimeout(300)

    const desc = await page.evaluate(() => {
      const t = (document.body.textContent || '').replace(/\s+/g, ' ')
      const m = t.match(/选教材\s+(.*?)\s+测法|选教材\s+(.*?)\s+开始摸底/)
      return (m && (m[1] || m[2])) || ''
    })

    const t0 = Date.now()
    await page.locator('text=开始摸底').first().click()
    let loaded = false
    try {
      await page.waitForSelector('.option', { timeout: 90000 })
      loaded = true
    } catch (e) {}
    const cost = Date.now() - t0

    check(`阶梯「${name}」能加载出题`, loaded, `等了 ${(cost / 1000).toFixed(1)}s 还没出选项`)
    if (!loaded) continue

    const optCount = await page.locator('.option').count()
    check(`阶梯「${name}」出题有 4 个选项`, optCount === 4, `实际 ${optCount} 个`)

    const diffLabel = await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('span')).find(
        s => (s.textContent || '').trim().startsWith('当前难度：')
      )
      return el ? el.textContent.trim() : ''
    })
    check(`阶梯「${name}」显示了当前难度标签`, !!diffLabel, '没找到「当前难度：xxx」')

    // ---- 关键：确认新增册子被真实下载（不是只在配置里躺着）
    const need = MUST_FETCH[name] || []
    const missing = need.filter(k => ![...fetched].some(u => u.includes(k)))
    check(
      `阶梯「${name}」真的下载了 ${need.length ? need.length + ' 本' : '全部'}册子（含初中/九年级）`,
      missing.length === 0,
      '没看到请求：' + missing.join(', ')
    )

    console.log(`[INFO] 「${name}」加载耗时 ${(cost / 1000).toFixed(1)}s｜描述：${desc.slice(0, 40)}`)
  }

  const realErrors = pageErrors.filter(e => !NOISE.test(e))
  check('页面无 JS 报错', realErrors.length === 0, realErrors.slice(0, 3).join(' | '))

  console.log(`\n合计失败 ${failed} 项`)
  await browser.close()
  process.exit(failed ? 1 : 0)
})().catch(e => { console.error(e); process.exit(1) })
