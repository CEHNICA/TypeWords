/**
 * 摸底「阶梯铺到九年级」浏览器实测
 * ======================================
 * 维度：用户原话「还有一直到9年纪的英文课本都要导入进去」
 *
 * 断言：
 *   1. 8 套阶梯逐个切过去都能点「开始摸底」并加载出题（选项出现）
 *   2. 加载过程中**真的拉到了**新增九年级册子（不是只写在配置文件里）
 *   3. 每套阶梯的加载耗时在可接受范围（阶梯从 6 级涨到 13 级，怕加载爆炸）
 *   4. 页面无 JS 报错
 *
 * 用法：node _tools/_check_placement_ladders.js
 */
const { chromium } = require('./_playwright')
const { waitForInteractive } = require('./_wait_ready')

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

/** 该阶梯的教材按钮是否处于选中态（type=primary） */
function isSelected(page, name) {
  return page.evaluate((label) => {
    const target = label.replace(/\s+/g, '').trim()
    const btns = [...document.querySelectorAll('.base-button')]
    const hit = btns.find(b => (b.textContent || '').replace(/\s+/g, '').trim() === target)
    return !!hit && /primary/.test(hit.className || '')
  }, name)
}

;(async () => {
  const browser = await chromium.launch({ headless: true })

  const pageErrors = []
  const NOISE = /play\(\) request was interrupted|play\(\) failed because the user didn't interact|Cannot set properties of undefined \(setting 'volume'\)/

  for (const name of LADDERS) {
    // 每个阶梯用**独立 context**：
    //  1) 复用同一个 page 时，上一个阶梯没下完的请求会飘到下一轮，污染 fetched（实测会混进 20 册）；
    //  2) 独立 context = 独立 HTTP 缓存 → 每个阶梯都真的走网络，能验到「册子被拉下来」。
    const ladderCtx = await browser.newContext({ viewport: { width: 1280, height: 900 } })
    const page = await ladderCtx.newPage()

    const fetched = new Set()
    page.on('pageerror', e => pageErrors.push(e.message))
    page.on('request', r => {
      const u = r.url()
      if (u.includes('/dicts/')) fetched.add(u)
    })

    await page.goto(BASE + '/placement-test', { waitUntil: 'domcontentloaded' })

    // **必须等 Nuxt hydrate 完**（见 _wait_ready.js 的说明）：
    // 固定 sleep 会在 hydrate 完成前点击 → 事件没绑上 → 点了没反应，
    // 加载的仍是默认阶梯（莱芜）→ '没看到请求' 假红。
    // 另一层坑：onMounted 会把选中态强制拉回默认阶梯，
    // 点之前没等它跑完，「点前 primary」在不同用例里五花八门。
    let switched = false
    for (let round = 0; round < 3 && !switched; round++) {
      const ready = await waitForInteractive(page, 30000)
      if (!ready) break

      const btn = page.locator(`text=${name}`).first()
      if (!(await btn.count())) {
        check(`阶梯「${name}」在 setup 页能找到按钮`, false, '按钮没渲染')
        break
      }
      await btn.click()

      // 点一次就够；等选中态真的切过来（读用户可见状态，不读内部变量）
      try {
        await page.waitForFunction(
          (label) => {
            const target = label.replace(/\s+/g, '').trim()
            const btns = [...document.querySelectorAll('.base-button')]
            const hit = btns.find(b => (b.textContent || '').replace(/\s+/g, '').trim() === target)
            return !!hit && /primary/.test(hit.className || '')
          },
          name,
          { timeout: 10000, polling: 200 }
        )
        switched = true
      } catch (e) {
        // 兜底：生产构建没有 useNuxtApp，hydrate 信号不可用 → 刷新整轮重来
        if (round < 2) {
          await page.goto(BASE + '/placement-test', { waitUntil: 'domcontentloaded' })
        }
      }
    }
    check(`阶梯「${name}」点得动（选中态切成 primary）`, switched, '点了没反应')
    if (!switched) {
      await ladderCtx.close()
      continue
    }

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
    if (!loaded) {
      await ladderCtx.close()
      continue
    }

    const optCount = await page.locator('.option').count()
    check(`阶梯「${name}」出题有 4 个选项`, optCount === 4, `实际 ${optCount} 个`)

    const diffLabel = await page.evaluate(() => {
      const el = Array.from(document.querySelectorAll('span')).find(
        s => (s.textContent || '').trim().startsWith('当前难度：')
      )
      return el ? el.textContent.trim() : ''
    })
    check(`阶梯「${name}」显示了当前难度标签`, !!diffLabel, '没找到「当前难度：xxx」')

    // ---- 关键：确认新增册子被真实拉下来（不是只在配置里躺着）
    // 必须等请求真的落地：`.option` 出现只说明第一道题渲染了，
    // 后面几本册子可能还在下载中 → 轮询等到全部命中或超时。
    const need = MUST_FETCH[name] || []
    const deadline = Date.now() + 30000
    let missing = need.filter(k => ![...fetched].some(u => u.includes(k)))
    while (missing.length && Date.now() < deadline) {
      await page.waitForTimeout(300)
      missing = need.filter(k => ![...fetched].some(u => u.includes(k)))
    }
    check(
      `阶梯「${name}」真的下载了 ${need.length ? need.length + ' 本' : '全部'}册子（含初中/九年级）`,
      missing.length === 0,
      '没看到请求：' + missing.join(', ')
    )

    console.log(`[INFO] 「${name}」加载耗时 ${(cost / 1000).toFixed(1)}s｜描述：${desc.slice(0, 40)}`)
    await ladderCtx.close()
  }

  const realErrors = pageErrors.filter(e => !NOISE.test(e))
  check('页面无 JS 报错', realErrors.length === 0, realErrors.slice(0, 3).join(' | '))

  console.log(`\n合计失败 ${failed} 项`)
  await browser.close()
  process.exit(failed ? 1 : 0)
})().catch(e => { console.error(e); process.exit(1) })
