/**
 * 摸底测试「答错后」界面截图（视觉验收用）
 */
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')
const path = require('path')

const BASE = process.env.TW_BASE_URL || 'http://localhost:5567'
const SHOTS = path.join(__dirname, '..', '_shots')

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  await page.goto(BASE + '/placement-test', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  await page.locator('text=开始摸底').first().click()
  await page.waitForSelector('.option', { timeout: 60000 })
  await page.waitForTimeout(400)

  // 答错一题
  for (let i = 0; i < 12; i++) {
    await page.locator('.option').nth(0).click()
    await page.waitForTimeout(400)
    const wrong = await page.evaluate(() =>
      Array.from(document.querySelectorAll('.option')).some(el =>
        (el.className || '').includes('text-red-600')
      )
    )
    if (wrong) break
    const next = page.locator('text=下一题').first()
    if (await next.count()) { await next.click(); await page.waitForTimeout(500) }
  }
  await page.screenshot({ path: path.join(SHOTS, 'placement_wrong.png'), fullPage: true })

  // 走到报告页
  for (let i = 0; i < 15; i++) {
    const next = page.locator('text=下一题').first()
    if (!(await next.count())) break
    await next.click()
    await page.waitForTimeout(450)
    if (await page.locator('.option').count()) {
      await page.locator('.option').nth(1).click()
      await page.waitForTimeout(250)
    }
  }
  const end = page.locator('text=结束，看结果').first()
  if (await end.count()) { await end.click(); await page.waitForTimeout(700) }
  await page.screenshot({ path: path.join(SHOTS, 'placement_report.png'), fullPage: true })

  console.log('shot ok')
  await browser.close()
})().catch(e => { console.error(e); process.exit(1) })
