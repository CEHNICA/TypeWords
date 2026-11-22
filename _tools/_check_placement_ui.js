/**
 * 摸底页浏览器实测尺子
 * ==================================================
 *
 * 老问题：答题循环里随机点选项，偶尔 5 题全错 → 「答题明细里至少有一行是答对的」红。
 * 再往前还有两处尺子自己的毛病（比 flaky 更可恨）：
 *   ① 用拼接文本正则去猜「末尾的英文单词」→ "all right" 这种带空格的词只取到 "right"，假红。
 *   ② 断言用 [a-zA-Z' -] 匹配英文 → 词库里 U+2019 弯撇号（we’ll）匹配不上，假红。
 *
 * 现在的做法：
 *   - 正确选项从 **Vue 组件状态** 读：`.option` 元素的 `__vueParentComponent.parent.setupState.question`
 *     里有 `correctIndex` 和 `candidates` —— 不用猜、100% 确定。
 *   - 第 1 题**故意答错**（挑一个 != correctIndex 的）→ 造出「误选」样本；
 *     其余题**全部答对** → 造出「答对」样本。两条断言都不用赌随机。
 *   - 英文单词从提交后追加的 `.bg-third` 芯片 span 里取，不解析拼接文本。
 */
const { chromium } = require('./_playwright')

const BASE = process.env.TW_BASE_URL || 'http://localhost:5567'
// 英文单词里可能带 ASCII 撇号、弯撇号（U+2019）、连字符和空格
const EN_TOKEN = "[A-Za-z'’\\- ]"

let failed = 0
function check(name, ok, detail = '') {
  if (!ok) failed++
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + (ok ? '' : '  —— ' + detail))
}
function info(name, detail = '') {
  console.log('[INFO] ' + name + (detail ? '  —— ' + detail : ''))
}

/** 开始摸底：dev server 忙的时候偶发点不动，重试几轮 */
async function startTest(page) {
  for (let attempt = 1; attempt <= 4; attempt++) {
    const btn = page.locator('text=开始摸底').first()
    try {
      if (await btn.count()) await btn.click({ timeout: 8000 })
    } catch (e) { /* 按钮还没渲染好，下一轮再试 */ }
    try {
      await page.waitForSelector('.option', { timeout: 20000 })
      return true
    } catch (e) {
      info('开始摸底超时，重试', '第 ' + attempt + ' 轮')
      await page.waitForTimeout(1500)
    }
  }
  return false
}

/** 从 Vue 组件状态读当前题：正确项下标 + 题面 + 各选项文本 */
async function readQuestion(page) {
  return await page.evaluate(() => {
    const el = document.querySelector('.option')
    let inst = el && el.__vueParentComponent
    let q = null
    while (inst && !q) {
      try {
        const raw = inst.setupState && inst.setupState.question
        const s = raw && raw.__v_isRef ? raw.value : raw
        if (s && typeof s === 'object' && Array.isArray(s.candidates)) q = s
      } catch (e) { /* 某些实例没有 setupState */ }
      inst = inst.parent
    }
    const stem = (document.querySelector('.text-4xl span')?.textContent || '').trim()
    const opts = Array.from(document.querySelectorAll('.option')).map(o =>
      (o.textContent || '').replace(/\s+/g, ' ').trim()
    )
    return {
      correctIndex: q ? q.correctIndex : -1,
      stem,
      opts,
      fromState: !!q,
    }
  })
}

/** 提交后抓选项状态：哪个红、哪个绿、每个选项的英文芯片、提示区原文 */
async function collectState(page) {
  return await page.evaluate(() => {
    const opts = Array.from(document.querySelectorAll('.option')).map(el => ({
      text: (el.textContent || '').replace(/\s+/g, ' ').trim(),
      cls: el.className || '',
      // 提交后追加的英文单词是个独立的小芯片 span（带底色 bg-third），中文在它前一个 span 里
      en: (el.querySelector('.bg-third')?.textContent || '').trim(),
    }))
    const body = (document.body.textContent || '').replace(/\s+/g, ' ')
    return {
      opts,
      redIdx: opts.findIndex(o => o.cls.includes('text-red-600')),
      greenIdx: opts.findIndex(o => o.cls.includes('text-green-600')),
      body,
    }
  })
}

;(async () => {
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await ctx.newPage()
  const pageErrors = []
  page.on('pageerror', e => pageErrors.push(e.message))
  const NOISE = /play\(\) request was interrupted|play\(\) failed because the user didn't interact|Cannot set properties of undefined \(setting 'volume'\)/

  await page.goto(BASE + '/placement-test', { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1200)

  if (!(await startTest(page))) {
    const body = (await page.evaluate(() => document.body.textContent || '')).replace(/\s+/g, ' ').slice(0, 300)
    check('能进入摸底答题（测试前提）', false, '点了「开始摸底」但一直没出现选项，页面正文：' + body)
    await browser.close()
    process.exit(1)
  }
  await page.waitForTimeout(400)

  // ---- 第 1 题：故意答错，造出「误选」样本
  let wrongInfo = null
  for (let round = 0; round < 12 && !wrongInfo; round++) {
    const q = await readQuestion(page)
    const n = q.opts.length
    if (!n) break
    // correctIndex 已知 → 挑一个必然错的；未知就点第 0 个
    const wrongIdx = q.correctIndex >= 0 && q.correctIndex < n ? (q.correctIndex + 1) % n : 0
    await page.locator('.option').nth(wrongIdx).click()
    await page.waitForTimeout(400)

    const state = await collectState(page)
    if (state.redIdx !== -1) {
      wrongInfo = state
      const k = state.body.indexOf('正确答案')
      check('答错后提示区出现「你选的是」', state.body.includes('你选的是'),
        '提示区原文：' + (k >= 0 ? state.body.slice(k, k + 120) : state.body.slice(0, 120)))
      const sel = state.body.slice(state.body.indexOf('你选的是'))
      check('「你选的是」带上了误选词的英文单词 + 中文释义',
        new RegExp('你选的是：\\s*' + EN_TOKEN + '+?\\s*（[^）\\s][^）]*）').test(sel),
        '原文：' + sel.slice(0, 100))
      const redEn = state.opts[state.redIdx].en || ''
      const selEn = (sel.match(/你选的是：\s*(.+?)\s*（/) || [])[1] || ''
      check('「你选的是」的英文跟红色选项的英文一致（真的是你选的那条）',
        !!redEn && !!selEn && redEn.toLowerCase() === selEn.trim().toLowerCase(),
        `红项英文=${redEn} 提示区=${sel.slice(0, 60)}`)
      const optWithEn = state.opts.filter(o => o.en)
      check('提交后每个选项行都显示对应的英文单词',
        optWithEn.length === state.opts.length && state.opts.length >= 3,
        `只有 ${optWithEn.length}/${state.opts.length} 个选项带英文：` + state.opts.map(o => o.text).join(' / '))
      const badApostrophe = state.opts.map(o => o.en).filter(t => /\s'\s|\s'|'\s/.test(t))
      check('选项里显示的英文单词撇号两侧没有空格（不是 "they\' re" 这种断词）',
        badApostrophe.length === 0, '断词：' + badApostrophe.join(' / '))
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

  // ---- 其余题：全部按组件状态里的 correctIndex 答对（确定性，不赌随机）
  let answeredRight = 0
  let answeredWrong = 0
  let stateUnknown = 0
  for (let i = 0; i < 25; i++) {
    const next = page.locator('text=下一题').first()
    if (!(await next.count())) break
    await next.click()
    await page.waitForTimeout(450)
    const optCount = await page.locator('.option').count()
    if (!optCount) continue

    const q = await readQuestion(page)
    let target = -1
    if (q.correctIndex >= 0 && q.correctIndex < optCount) {
      target = q.correctIndex
    } else {
      stateUnknown++
      info('这一题没读到 correctIndex（组件状态不可达），退回随机点', '题面=' + q.stem)
      target = Math.floor(Math.random() * optCount)
    }
    await page.locator('.option').nth(target).click()
    await page.waitForTimeout(280)

    const st = await collectState(page)
    if (st.redIdx !== -1) answeredWrong++
    else if (st.greenIdx !== -1) answeredRight++
  }
  info('按状态答对的题数', String(answeredRight))
  info('按状态答错的题数', String(answeredWrong))
  if (stateUnknown) info('没读到组件状态的题数', String(stateUnknown))

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

  check('答题明细确实有行（尺子没瞎）', report.rows.length > 0, '一条明细都没抓到，尺子选择器可能又失效了')
  const wrongRows = report.rows.filter(r => r.text.includes('误选：'))
  check('报告「答题明细」里答错的行出现「误选：xxx（中文）」', wrongRows.length > 0, `答题明细共 ${report.rows.length} 行，没有一行带误选`)
  if (wrongRows.length) {
    check('误选行的中文释义不是空的',
      new RegExp('误选：\\s*' + EN_TOKEN + '+?\\s*（[^）\\s][^）]*）').test(wrongRows[0].text),
      '误选那一栏是空的：' + wrongRows[0].text)
    check('误选用醒目颜色（orange/red）跟正确答案区分开',
      /text-(orange|red)-600/.test(wrongRows[0].html), '误选那一栏没有醒目色')
  }

  // ---- 答对的行不出现误选列
  const rightRows = report.rows.filter(r => !r.text.includes('误选：'))
  check('答题明细里至少有一行是答对的（尺子没瞎）', rightRows.length > 0, `答对的行 0 条，共 ${report.rows.length} 行`)
  check('答对的行不显示误选列', rightRows.every(r => !r.text.includes('误选')), '有答对的行冒出了误选内容')

  // ---- 导出的 CSV 表头带「误选单词 / 误选释义」两列
  const dl = page.locator('text=导出 CSV（给老师）').first()
  if (await dl.count()) {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 15000 }),
      dl.click(),
    ])
    const csvPath = await download.path()
    const fs = require('fs')
    const csv = fs.readFileSync(csvPath, 'utf8')
    check('导出的 CSV 表头带「误选单词 / 误选释义」两列', csv.includes('误选单词') && csv.includes('误选释义'), 'CSV 表头：' + csv.split('\r\n')[0])
    const dataRows = csv.split('\r\n').filter(Boolean).slice(1)
    const wrongRow = dataRows.find(r => r.includes('答错'))
    check('CSV 里答错的那行填了误选词', !!wrongRow && /答错","[^"]*","[^"]+"/.test(wrongRow), '答错行内容：' + wrongRow)
  } else {
    check('报告页有「导出 CSV」按钮', false, '按钮不见了')
  }

  const realErrors = pageErrors.filter(e => !NOISE.test(e))
  check('页面无 JS 报错', realErrors.length === 0, realErrors.join(' | '))
  const noiseSeen = pageErrors.length - realErrors.length
  if (noiseSeen) info('上游既有的音频噪音报错（已豁免，非本轮缺陷）：' + noiseSeen + ' 条')

  await browser.close()
  console.log('\n失败 ' + failed + ' 项')
  process.exit(failed ? 1 : 0)
})().catch(e => { console.error(e); process.exit(1) })
