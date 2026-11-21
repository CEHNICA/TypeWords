/**
 * 摸底测试「答错后信息完整性」浏览器实测
 * ======================================
 * 维度来自用户原话：「我摸底的时候，错误了，其他选项的中文也应该显示。」
 *
 * 断言：
 *   1. 答错后提示区出现「你选的是」，并带上误选词的**英文单词 + 中文释义**
 *   2. 答错后「正确答案」那一行也带英文 + 中文
 *   3. 提交后每个选项行都显示该选项对应的**英文单词**（中文释义要能对上词）
 *   4. 报告「答题明细」里答错的行出现「误选：xxx（中文）」
 *   5. 答对的行**不**出现误选列（别占地方）
 *   6. 导出 CSV 的表头带「误选单词 / 误选释义」两列
 *
 * 用法：node _tools/_check_placement_ui.js
 */
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')

const BASE = process.env.TW_BASE_URL || 'http://localhost:5567'
let failed = 0
function check(name, ok, detail = '') {
  if (!ok) failed++
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + (ok ? '' : '  —— ' + detail))
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const pageErrors = []
  page.on('pageerror', e => pageErrors.push(e.message))
  // 上游既有的音频噪音（连续点选项时 play() 被 pause 打断）不是本轮缺陷，单列出来
  const NOISE = /play\(\) request was interrupted|play\(\) failed because the user didn't interact|Cannot set properties of undefined \(setting 'volume'\)/

  await page.goto(BASE + '/placement-test', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)
  await page.locator('text=开始摸底').first().click()
  await page.waitForSelector('.option', { timeout: 60000 })
  await page.waitForTimeout(400)

  // ---- 找一个能答错的题：点第一个选项，看提交后是否标红
  let wrongInfo = null
  for (let round = 0; round < 12 && !wrongInfo; round++) {
    const optCount = await page.locator('.option').count()
    if (!optCount) break
    await page.locator('.option').nth(0).click()
    await page.waitForTimeout(400)

    const state = await page.evaluate(() => {
      const opts = Array.from(document.querySelectorAll('.option')).map(el => ({
        text: (el.textContent || '').replace(/\s+/g, ' ').trim(),
        cls: el.className || '',
      }))
      const redIdx = opts.findIndex(o => o.cls.includes('text-red-600'))
      const greenIdx = opts.findIndex(o => o.cls.includes('text-green-600'))
      const body = (document.body.textContent || '').replace(/\s+/g, ' ')
      return { opts, redIdx, greenIdx, body }
    })

    if (state.redIdx !== -1 && state.greenIdx !== -1) {
      wrongInfo = state
      // ---- 断言 1：提示区出现「你选的是」
      check(
        '答错后提示区出现「你选的是」',
        state.body.includes('你选的是'),
        '提示区原文：' + state.body.slice(state.body.indexOf('正确答案'), state.body.indexOf('正确答案') + 120)
      )
      // ---- 断言 2：「你选的是」后面带着误选词的英文 + 中文
      const m = state.body.match(/你选的是：\s*([a-zA-Z' -]+?)\s*（([^）]*)）/)
      check(
        '「你选的是」带上了误选词的英文单词 + 中文释义',
        !!m,
        '没匹配到「你选的是：xxx（中文）」'
      )
      if (m) {
        const chosenCn = state.opts[state.redIdx].text.replace(/^[A-D]\[\d+\]/, '').trim()
        check(
          '「你选的是」的中文跟红色选项的中文一致（真的是你选的那条）',
          chosenCn.startsWith(m[2].slice(0, 2)) || chosenCn.includes(m[2].slice(0, 2)),
          `选项行=${chosenCn} / 提示=${m[2]}`
        )
      }
      // ---- 断言 3：每个选项行提交后都带英文单词
      // 注意：英文词可能是单字母（a / I），所以只查「含英文字母」，不能要求 ≥2 个字母
      const optWithEn = state.opts.filter(o => /[a-zA-Z]/.test(o.text.replace(/^[A-D]\[\d+\]/, '')))
      check(
        '提交后每个选项行都显示对应的英文单词',
        optWithEn.length === state.opts.length && state.opts.length >= 3,
        `只有 ${optWithEn.length}/${state.opts.length} 个选项带英文：` +
          state.opts.map(o => o.text).join(' / ')
      )
      // ---- 断言 3b：显示出来的英文单词撇号两侧没有空格（词库里是 "they're"，不是 "they' re"）
      const badApostrophe = state.opts
        .map(o => o.text.replace(/^[A-D]\[\d+\]/, '').trim())
        .filter(t => /\s'\s|\s'|'\s/.test(t))
      check(
        '选项里显示的英文单词撇号两侧没有空格（不是 "they\' re" 这种断词）',
        badApostrophe.length === 0,
        '断词：' + badApostrophe.join(' / ')
      )
      break
    }

    const next = page.locator('text=下一题').first()
    if (await next.count()) {
      await next.click()
      await page.waitForTimeout(500)
    } else break
  }

  if (!wrongInfo) {
    check('能造出一题答错的题（测试前提）', false, '连点 12 次都是对的，摸底逻辑有问题')
    await browser.close()
    process.exit(1)
  }

  // ---- 一路答到报告页（每题随机点一个选项，保证样本里既有答对也有答错）
  for (let i = 0; i < 25; i++) {
    const next = page.locator('text=下一题').first()
    if (!(await next.count())) break
    await next.click()
    await page.waitForTimeout(450)
    const optCount = await page.locator('.option').count()
    if (optCount) {
      await page.locator('.option').nth(Math.floor(Math.random() * optCount)).click()
      await page.waitForTimeout(280)
    }
  }
  const end = page.locator('text=结束，看结果').first()
  if (await end.count()) {
    await end.click()
    await page.waitForTimeout(700)
  }

  const report = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('[data-placement-row]')).map(el => ({
      text: (el.textContent || '').replace(/\s+/g, ' ').trim(),
      cls: el.className || '',
      html: el.innerHTML || '',
    }))
    return { rows, body: (document.body.textContent || '').replace(/\s+/g, ' ') }
  })

  // ---- 断言 4：答题明细里答错的行出现「误选：xxx（中文）」
  check('答题明细确实有行（尺子没瞎）', report.rows.length > 0, '一条明细都没抓到，尺子选择器可能又失效了')
  const wrongRows = report.rows.filter(r => r.text.includes('误选：'))
  check(
    '报告「答题明细」里答错的行出现「误选：xxx（中文）」',
    wrongRows.length > 0,
    `答题明细共 ${report.rows.length} 行，没有一行带误选`
  )
  if (wrongRows.length) {
    check(
      '误选行的中文释义不是空的',
      /误选：\s*[a-zA-Z' -]+?\s*（[^）\s][^）]*）/.test(wrongRows[0].text),
      '误选那一栏是空的：' + wrongRows[0].text
    )
    check(
      '误选用醒目颜色（orange/red）跟正确答案区分开',
      /text-(orange|red)-600/.test(wrongRows[0].html),
      '误选那一栏没有醒目色'
    )
  }
  // ---- 断言 5：答对的行不出现误选列
  const rightRows = report.rows.filter(r => !r.text.includes('误选：'))
  check('答题明细里至少有一行是答对的（尺子没瞎）', rightRows.length > 0, `答对的行 0 条，共 ${report.rows.length} 行`)
  check(
    '答对的行不显示误选列',
    rightRows.every(r => !r.text.includes('误选')),
    '有答对的行冒出了误选内容'
  )

  // ---- 断言 6：导出的 CSV 表头带「误选单词 / 误选释义」两列
  const dl = page.locator('text=导出 CSV（给老师）').first()
  if (await dl.count()) {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }),
      dl.click(),
    ])
    const csvPath = await download.path()
    const fs = require('fs')
    const csv = fs.readFileSync(csvPath, 'utf8')
    check(
      '导出的 CSV 表头带「误选单词 / 误选释义」两列',
      csv.includes('误选单词') && csv.includes('误选释义'),
      'CSV 表头：' + csv.split('\r\n')[0]
    )
    const dataRows = csv.split('\r\n').filter(Boolean).slice(1)
    const wrongRow = dataRows.find(r => r.includes('答错'))
    check(
      'CSV 里答错的那行填了误选词',
      !!wrongRow && /答错","[^"]*","[^"]+"/.test(wrongRow),
      '答错行内容：' + wrongRow
    )
  } else {
    check('报告页有「导出 CSV」按钮', false, '按钮不见了')
  }

  const realErrors = pageErrors.filter(e => !NOISE.test(e))
  const noise = pageErrors.filter(e => NOISE.test(e))
  check(
    '页面无 JS 报错',
    realErrors.length === 0,
    realErrors.join(' | ')
  )
  if (noise.length) {
    console.log('[INFO] 上游既有的音频噪音报错（已豁免，非本轮缺陷）：' + noise.length + ' 条')
  }

  console.log(`\n合计 ${6 + (wrongRows.length ? 3 : 0) + 1} 项左右，失败 ${failed} 项`)
  await browser.close()
  process.exit(failed ? 1 : 0)
})().catch(e => { console.error(e); process.exit(1) })
