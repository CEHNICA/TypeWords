/**
 * 给莱芜课本课文补中文译文（逐句）
 * ==================================================
 *
 * 干什么用的：
 *   上游的课文是从课本 PDF 提取的英文原文，**没有中文译文**，
 *   跟打页的译文区整块不显示（`textTranslate` 为空 → `v-if="showTranslate && selectArticle.textTranslate"` 直接不渲染）。
 *
 *   怎么翻的：
 *   走 Google 翻译的免费接口 `translate.googleapis.com/translate_a/single?client=gtx`。
 *   **必须从浏览器页面里发请求** —— 从 PowerShell 直连会被 429 限流（出口 IP），
 *   浏览器里 fetch 同一个地址返回 200 且 CORS 放行。
 *   **必须逐句串行 + 句间 120ms** —— 并发会被限流。
 *
 *   重复句走缓存（小学课文 "Hello!" 这种重复率很高，能省掉大批请求）。
 *   每批翻完立刻增量写盘，中断后重跑会从缓存续上。
 *
 * 怎么跑：
 *   node scripts/translate-article-sentences.js            # 全量
 *   node scripts/translate-article-sentences.js --probe    # 只测 8 句能不能翻
 *   node scripts/translate-article-sentences.js --batch 200
 *
 * 译完必须跑： python _tools/check_article_sentences.py
 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const ARTICLE_DIR = path.join(ROOT, 'public', 'dicts', 'en', 'article')
const CACHE_FILE = path.join(ROOT, 'data', 'article-translations.json')
const BASE = 'http://localhost:5567'

const BOOKS = [
  'LWXX_3_1', 'LWXX_3_2', 'LWXX_4_1', 'LWXX_4_2', 'LWXX_5_1', 'LWXX_5_2',
  'LWCZ_6_1', 'LWCZ_6_2', 'LWCZ_7_1', 'LWCZ_7_2', 'LWCZ_8_1', 'LWCZ_8_2', 'LWCZ_9_1',
]

/** 把 text 按「段落 → 句」拆开（与 genArticleSectionData 一致） */
function splitText(text) {
  return text
    .split('\n\n')
    .filter(p => p.trim())
    .map(p => p.split('\n').filter(s => s.trim()))
}

function loadCache() {
  if (!fs.existsSync(CACHE_FILE)) return {}
  try {
    return JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'))
  } catch {
    return {}
  }
}

function saveCache(cache) {
  fs.mkdirSync(path.dirname(CACHE_FILE), { recursive: true })
  fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 1), 'utf8')
}

/** 页面内执行：并发池翻译（并发 CONC，实测 20 路无 429，吞吐 ~26 句/s） */
async function translateInPage(items, conc = 10) {
  return await page.evaluate(async ({ list, conc }) => {
    const sleep = ms => new Promise(r => setTimeout(r, ms))
    const out = new Array(list.length).fill('')
    let idx = 0
    async function worker() {
      while (true) {
        const i = idx++
        if (i >= list.length) return
        const q = list[i]
        let res = ''
        let ok = false
        for (let attempt = 0; attempt < 3 && !ok; attempt++) {
          try {
            const url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=' +
              encodeURIComponent(q)
            const r = await fetch(url)
            if (!r.ok) throw new Error('HTTP ' + r.status)
            const j = await r.json()
            res = (j[0] || []).map(x => (x && x[0]) || '').join('').trim()
            ok = !!res
          } catch (e) {
            res = ''
            await sleep(1200 * (attempt + 1))
          }
        }
        out[i] = res
      }
    }
    await Promise.all(Array.from({ length: Math.min(conc, list.length || 1) }, worker))
    return out
  }, { list: items, conc })
}

let page = null

async function main() {
  const args = process.argv.slice(2)
  const probe = args.includes('--probe')
  const batchIdx = args.indexOf('--batch')
  const BATCH = batchIdx >= 0 ? Number(args[batchIdx + 1]) : 400
  const concIdx = args.indexOf('--conc')
  const CONC = concIdx >= 0 ? Number(args[concIdx + 1]) : 10

  const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')
  const b = await chromium.launch({ headless: true })
  const ctx = await b.newContext()
  page = await ctx.newPage()
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 30000 })

  if (probe) {
    const t0 = Date.now()
    const r = await translateInPage(['Hello! I am Li Ming.', 'The radio changed the world.', 'Good morning!'])
    console.log('耗时', Date.now() - t0, 'ms')
    console.log(JSON.stringify(r, null, 2))
    await b.close()
    return
  }

  const cache = loadCache()
  const stats = { total: 0, cached: 0, translated: 0, failed: 0 }
  const startedAt = Date.now()

  for (const book of BOOKS) {
    const file = path.join(ARTICLE_DIR, book + '.json')
    if (!fs.existsSync(file)) continue
    const arts = JSON.parse(fs.readFileSync(file, 'utf8'))
    const arr = Array.isArray(arts) ? arts : [arts]

    // 收集本册所有待翻句
    const need = []
    for (let ai = 0; ai < arr.length; ai++) {
      const a = arr[ai]
      const paras = splitText(a.text || '')
      const keys = []
      for (const para of paras) for (const s of para) keys.push(s)
      stats.total += keys.length + 1 // +1 = 标题
      for (const k of keys) if (cache[k]) stats.cached++
      need.push({ ai, a, paras, keys, title: (a.title || '').trim() })
    }

    // 批量翻译（去重）
    const uniq = []
    const seen = new Set()
    for (const item of need) {
      if (item.title && !cache[item.title] && !seen.has(item.title)) { seen.add(item.title); uniq.push(item.title) }
      for (const k of item.keys) {
        if (!cache[k] && !seen.has(k)) { seen.add(k); uniq.push(k) }
      }
    }
    for (let i = 0; i < uniq.length; i += BATCH) {
      const chunk = uniq.slice(i, i + BATCH)
      const res = await translateInPage(chunk, CONC)
      res.forEach((v, idx) => {
        if (v) { cache[chunk[idx]] = v; stats.translated++ } else { stats.failed++ }
      })
      saveCache(cache)
      const done = Math.min(i + BATCH, uniq.length)
      const pct = uniq.length ? ((done / uniq.length) * 100).toFixed(1) : '100'
      const mins = ((Date.now() - startedAt) / 60000).toFixed(1)
      console.log(`[${book}] ${done}/${uniq.length} 唯一句 (${pct}%)  已翻${stats.translated} 缓存${stats.cached} 失败${stats.failed}  用时${mins}分`)
    }

    // 回填：标题 + 正文（段落 \n\n，句 \n）
    for (const item of need) {
      const a = item.a
      if (a.title && !a.titleTranslate) {
        a.titleTranslate = cache[(a.title || '').trim()] || ''
      }
      const paras = item.paras
      const transParas = paras.map(para => para.map(s => (cache[s] || '').trim()).join('\n'))
      a.textTranslate = transParas.join('\n\n')
    }
    fs.writeFileSync(file, JSON.stringify(arr, null, 2) + '\n', 'utf8')
    console.log(`[${book}] 已写盘`)
  }

  saveCache(cache)

  // 收尾重试：把仍然没翻成功的句子再跑一遍
  const missing = []
  for (const bk of BOOKS) {
    const file = path.join(ARTICLE_DIR, bk + '.json')
    if (!fs.existsSync(file)) continue
    const arr = JSON.parse(fs.readFileSync(file, 'utf8'))
    const seen = new Set()
    for (const a of arr) {
      const t = (a.title || '').trim()
      if (t && !cache[t] && !seen.has(t)) { seen.add(t); missing.push(t) }
      for (const para of (a.text || '').split('\n\n')) {
        for (const line of para.split('\n')) {
          const s = line.trim()
          if (s && !cache[s] && !seen.has(s)) { seen.add(s); missing.push(s) }
        }
      }
    }
  }
  if (missing.length) {
    console.log(`\n收尾重试 ${missing.length} 句…`)
    for (let i = 0; i < missing.length; i += 200) {
      const chunk = missing.slice(i, i + 200)
      const res = await translateInPage(chunk, 6)
      res.forEach((v, idx) => { if (v) cache[chunk[idx]] = v })
      saveCache(cache)
      console.log(`  重试 ${Math.min(i + 200, missing.length)}/${missing.length}`)
    }
  }

  // 收尾重试后，把所有册重新回填写盘一次（重试成功的句子补上空位）
  for (const bk of BOOKS) {
    const file = path.join(ARTICLE_DIR, bk + '.json')
    if (!fs.existsSync(file)) continue
    const arr = JSON.parse(fs.readFileSync(file, 'utf8'))
    for (const a of arr) {
      const t = (a.title || '').trim()
      if (t && !a.titleTranslate) a.titleTranslate = cache[t] || ''
      const paras = splitText(a.text || '')
      a.textTranslate = paras.map(para => para.map(s => (cache[s] || '').trim()).join('\n')).join('\n\n')
    }
    fs.writeFileSync(file, JSON.stringify(arr, null, 2) + '\n', 'utf8')
  }

  console.log('\n完成：总句', stats.total, '新翻', stats.translated, '命中缓存', stats.cached, '失败', stats.failed,
    '用时', ((Date.now() - startedAt) / 60000).toFixed(1), '分')
  await b.close()
}

main().catch(e => {
  console.error('失败:', e && e.message)
  process.exit(1)
})
