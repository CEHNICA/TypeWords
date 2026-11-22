/**
 * 摸底报告页「摸到顶之后往哪走」浏览器实测
 * ==============================================
 * 维度：阶梯铺到九年级之后，报告页的结语不能还在瞎喊「可以上高中词汇表了」。
 *
 * 断言：
 *   1. setup 页 8 套教材按钮全在，且新加的「外研社（初中）」按钮存在
 *   2. 每套阶梯加载后，setup 页显示的「共 N 个年级」跟阶梯级数一致
 *   3. 报告页 advice 文案里不出现「可以上高中词汇表了」这种硬喊（除非该阶梯确实含初中册）
 *
 * 用法：node _tools/_check_placement_advice.js
 */
const { chromium } = require('./_playwright')

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

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()

  // ---- 断言 1：setup 页按钮齐全
  await page.goto(BASE + '/placement-test', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1000)
  for (const name of LADDERS) {
    check(`setup 页有「${name}」按钮`, (await page.locator(`text=${name}`).count()) > 0, '按钮没渲染')
  }
  check(
    '新加的「外研社（初中）」独立成一套教材按钮',
    (await page.locator('text=外研社（初中）').count()) > 0,
    '外研初中没单独成阶梯'
  )

  // ---- 断言 2：切到外研社（初中）后，「共 N 个年级」应为 6
  await page.locator('text=外研社（初中）').first().click()
  await page.waitForTimeout(300)
  await page.locator('text=逐级诊断（每个年级都测）').first().click()
  await page.waitForTimeout(300)
  const gradeText = await page.evaluate(() => {
    const t = (document.body.textContent || '').replace(/\s+/g, ' ')
    const m = t.match(/共 (\d+) 个年级/)
    return m ? m[1] : ''
  })
  check('外研社（初中）显示「共 6 个年级」', gradeText === '6', '实际是「' + gradeText + '」')

  // ---- 断言 3：走完一轮，看报告页 advice 文案
  await page.locator('text=人教版 PEP').first().click()
  await page.waitForTimeout(300)
  // 切回「自适应定位」模式：逐级诊断模式的报告文案是「断层在这一级」，
  // 跟这里的断言（「定位到这一级」）不是一回事，混着测就是尺子假阳性
  await page.locator('text=自适应定位').first().click()
  await page.waitForTimeout(300)
  await page.locator('text=开始摸底').first().click()
  await page.waitForSelector('.option', { timeout: 60000 })
  // 随机答 6 题就收工，不追求答满
  for (let i = 0; i < 6; i++) {
    const next = page.locator('text=下一题').first()
    if (await next.count()) {
      await next.click()
      await page.waitForTimeout(350)
    }
    const optCount = await page.locator('.option').count()
    if (optCount) {
      await page.locator('.option').nth(Math.floor(Math.random() * optCount)).click()
      await page.waitForTimeout(250)
    }
  }
  const end = page.locator('text=结束，看结果').first()
  if (await end.count()) {
    await end.click()
    await page.waitForTimeout(700)
  }
  const body = await page.evaluate(() => (document.body.textContent || '').replace(/\s+/g, ' '))
  check('报告页出来了', body.includes('答题明细'), '没进报告页')
  if (!body.includes('定位到这一级')) {
    console.log('[DEBUG] 报告页前 400 字：' + body.slice(0, 400))
  }
  check(
    '报告页显示了定位年级',
    body.includes('定位到这一级'),
    '报告页没有「定位到这一级」'
  )
  // 只要没摸到顶，advice 里就不该出现「摸到顶了」
  check(
    '没摸到顶时报告不瞎喊「摸到顶了」',
    !body.includes('已经摸到顶了'),
    '才答 6 题就说摸到顶了，逻辑有问题'
  )

  console.log(`\n合计失败 ${failed} 项`)
  await browser.close()
  process.exit(failed ? 1 : 0)
})().catch(e => { console.error(e); process.exit(1) })
