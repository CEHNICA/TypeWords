/**
 * 复习页「英文后面紧跟着的中文」浏览器实测尺子
 * =============================================
 *
 * 用户原话：「复习一本书的时候，英语后面紧跟着的中文和课本上的不一样」。
 *
 * 这个尺子验的是**页面真实渲染出来的中文**，不是我们自己的数据层：
 *   1) 打开 /book-review → 选莱芜册 → 进入复习
 *   2) 每答一题，页面会摊开「这一题的四个单词（选项 ↔ 英文）」对照表
 *      —— .detail-row 里 .detail-en = 英文、.detail-cn = 页面显示的中文
 *   3) 把抓到的 (英文, 中文) 逐条和课本 PDF 抽出来的课本词表对
 *
 * 数据层由 _tools/check_textbook_trans.py 对账归零，这里再验一遍
 * 「页面确实显示的是它」，避免「数据对了但页面根本没读这份数据」的假绿。
 */
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.env.TW_BASE_URL || 'http://localhost:5567'
const ROOT = path.resolve(__dirname, '..')
const WL_FILE = path.join(ROOT, 'data', 'textbook-wordlists.json')

/** 莱芜 13 册 = ladder 'lw' 的 steps 顺序（app/core/data/placement.ts） */
const CHIP_BIDS = ['LWXX_3_1', 'LWXX_3_2', 'LWXX_4_1', 'LWXX_4_2', 'LWXX_5_1', 'LWXX_5_2',
  'LWCZ_6_1', 'LWCZ_6_2', 'LWCZ_7_1', 'LWCZ_7_2', 'LWCZ_8_1', 'LWCZ_8_2', 'LWCZ_9_1']

/** 答几题（每题 4 个词，样本量 = 4 × N） */
const QUESTION_COUNT = Number(process.env.TW_QUESTIONS || 12)

let failed = 0
function check(name, ok, detail = '') {
  if (!ok) failed++
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + (ok ? '' : '  —— ' + detail))
}
function info(name, detail = '') {
  console.log('[INFO] ' + name + (detail ? '  —— ' + detail : ''))
}

/** 和 book-review.vue 的 shortTrans 完全一致（取第一段 + 14 字截断） */
function short(cn) {
  const first = String(cn || '').split(/[；;]/)[0].trim()
  const cut = first.length > 14 ? first.slice(0, 14) + '…' : first
  return cut
}

async function main() {
  if (!fs.existsSync(WL_FILE)) {
    console.log('[FAIL] 缺课本词表缓存 data/textbook-wordlists.json')
    process.exit(1)
  }
  const allWl = JSON.parse(fs.readFileSync(WL_FILE, 'utf-8'))

  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(String(e)))

  await page.goto(BASE + '/book-review', { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.book-chip', { timeout: 30000 })
  // 等词库清单加载完（chip 上出现词数、「已选 N 册」出现），否则点 chip 会打在还没初始化的列表上
  await page.waitForFunction(
    () => /已选\s*13\s*册\s*·\s*约\s*[1-9]/.test(document.body.innerText || ''),
    null, { timeout: 30000 },
  )

  const chips = await page.locator('.book-chip').all()
  const chipTexts = []
  for (let i = 0; i < chips.length; i++) {
    chipTexts.push(((await chips[i].innerText()) || '').replace(/\s+/g, ' ').trim())
  }
  info('册子 chip 数', String(chips.length))
  info('chip 列表', chipTexts.join(' | '))
  check('chip 数与莱芜 13 册一致', chips.length === CHIP_BIDS.length, String(chips.length))
  if (chips.length !== CHIP_BIDS.length) { await browser.close(); process.exit(1) }

  // 目标册：小学五年级上册（课本口径差异最多的册之一）
  const idx = CHIP_BIDS.indexOf('LWXX_5_1')
  check('定位到小学五上 chip', idx >= 0 && chipTexts[idx].includes('五年级上'), chipTexts[idx] || '')

  // 页面默认全选 13 册 —— 干扰项会来自别的册，课本口径就不是同一套了。
  // 先取消全选，再只勾目标册。
  await page.locator('.base-button:has-text("取消全选")').first().click({ timeout: 10000 })
  await page.waitForFunction(() => document.querySelectorAll('.book-chip.on').length === 0, null, { timeout: 10000 })
  await chips[idx].click({ timeout: 10000 })
  await page.waitForFunction(() => document.querySelectorAll('.book-chip.on').length === 1, null, { timeout: 10000 })
  check('只选中目标册', (await page.locator('.book-chip.on').count()) === 1,
    'on=' + (await page.locator('.book-chip.on').count()))
  await page.waitForTimeout(300)

  // 开始复习（按钮文案可能是「开始复习」或「继续（已过 n 个词）」）
  // BaseButton 渲染的是 div.base-button，不是 <button>
  const startBtn = page.locator('.base-button:has-text("开始复习"), .base-button:has-text("继续")').first()
  await startBtn.click({ timeout: 15000 })
  // 词库下载 + 解析 + 出题，等第一道题出来
  await page.waitForSelector('.option', { timeout: 90000 })

  const bid = CHIP_BIDS[idx]
  const book = allWl[bid] || {}
  info('目标册', chipTexts[idx] + ' → ' + bid + '（课本词表 ' + Object.keys(book).length + ' 词）')

  const pairs = []      // { en, cn }
  const bookLabels = new Set()
  for (let q = 0; q < QUESTION_COUNT; q++) {
    // 读「当前册子」
    const label = await page.evaluate(() => {
      const el = [...document.querySelectorAll('span')].find((s) =>
        (s.textContent || '').trim().startsWith('当前册子：'))
      return el ? el.textContent.trim().replace('当前册子：', '').trim() : ''
    })
    if (label) bookLabels.add(label)

    // 点第一个选项 = 提交
    const opt = page.locator('.option').first()
    if (!(await opt.count())) break
    await opt.click({ timeout: 8000 })
    const expandBtn = page.locator('.base-button:has-text("展开对照")').first()
    if (await expandBtn.count()) {
      await expandBtn.click({ timeout: 5000 }).catch(() => {})
    }
    await page.waitForSelector('.detail-row', { timeout: 8000 }).catch(() => {})

    const got = await page.evaluate(() => {
      const out = []
      document.querySelectorAll('.detail-row').forEach((el) => {
        const en = (el.querySelector('.detail-en')?.textContent || '').trim()
        const cn = (el.querySelector('.detail-cn')?.textContent || '').trim()
        if (en) out.push({ en, cn })
      })
      return out
    })
    pairs.push(...got)

    // 下一题
    const nextBtn = page.locator('.base-button:has-text("下一个")').first()
    if (!(await nextBtn.count())) break
    await nextBtn.click({ timeout: 8000 }).catch(() => {})
    await page.waitForTimeout(350)
  }

  info('抓到的 (英文,中文) 对', String(pairs.length))
  info('页面上出现过的册子标签', [...bookLabels].join(' | '))

  check('页面上抓到了词条行', pairs.length > 0, '行数 ' + pairs.length)

  let matched = 0
  let mismatched = 0
  const samples = []
  const seen = new Set()
  for (const p of pairs) {
    const k = p.en + '\u0000' + p.cn
    if (seen.has(k)) continue
    seen.add(k)
    if (!Object.prototype.hasOwnProperty.call(book, p.en)) continue   // 课本词表没这个词 → 不判
    matched++
    const want = short(book[p.en])
    if (want !== p.cn) {
      mismatched++
      if (samples.length < 10) samples.push(`${p.en}: 页面=${p.cn} 课本=${want}`)
    }
  }

  info('对上课本词表的样本', 'matched ' + matched + ' / 总样本 ' + pairs.length)
  info('样本抽样', samples.length
    ? samples.join(' | ')
    : [...seen].slice(0, 3).map((k) => k.replace('\u0000', ' → ')).join(' | '))
  check('样本量够（>= 20 对）', matched >= 20, 'matched ' + matched)
  check('页面中文全部等于课本口径', mismatched === 0,
    '不一致 ' + mismatched + ' 条：' + samples.join(' | '))
  check('页面无 JS 报错', errors.length === 0, errors.slice(0, 2).join(' | '))

  await browser.close()
  console.log('-' * 50)
  console.log('失败项合计: ' + failed)
  process.exit(failed ? 1 : 0)
}

main().catch((e) => { console.error(e); process.exit(1) })
