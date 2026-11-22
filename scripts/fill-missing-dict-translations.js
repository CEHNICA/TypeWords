/*
给六~九年级词库里「无释义」的词条补中文释义
================================================

分两步：
  1. 复用：从全库其它词书的同名词条搬释义（零成本、无误）
  2. 翻译：剩下的走 Google 翻译（浏览器页面内 fetch，并发池）

用法：
  node scripts/fill-missing-dict-translations.js --probe
  node scripts/fill-missing-dict-translations.js            # dry-run
  node scripts/fill-missing-dict-translations.js --apply    # 真写盘
*/
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const LIST = path.join(ROOT, 'public', 'list', 'word.json')
const WORD_DIR = path.join(ROOT, 'public', 'dicts', 'en', 'word')
const CACHE_FILE = path.join(ROOT, 'data', 'dict-translations.json')
const BASE = 'http://localhost:5567'

let page = null

/** 归一化：把省略号、多空格、全角括号统一，便于跨书匹配 */
function norm(s) {
  return (s || '')
    .toLowerCase()
    .replace(/[.…]+/g, ' ')
    .replace(/[（(]/g, ' ').replace(/[）)]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function cnOf(w) {
  const syn = w.synos || []
  const parts = []
  for (const s of syn) {
    const cn = (s.cn || '').trim()
    if (!cn) continue
    const pos = (s.pos || '').trim()
    parts.push(pos ? `${pos} ${cn}` : cn)
  }
  return parts.join('；')
}

async function translateInPage(items, conc) {
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

async function main() {
  const args = process.argv.slice(2)
  const apply = args.includes('--apply')
  const probe = args.includes('--probe')
  const concIdx = args.indexOf('--conc')
  const CONC = concIdx >= 0 ? Number(args[concIdx + 1]) : 10

  const list = JSON.parse(fs.readFileSync(LIST, 'utf8'))
  const targets = list.filter(d => (d.tags || []).some(t => t.includes('六') && t.includes('九')))
  console.log('目标册数', targets.length)

  // 1) 复用索引：全库所有有释义的词
  const reuse = new Map()
  for (const d of list) {
    const f = path.join(WORD_DIR, d.url)
    if (!fs.existsSync(f)) continue
    const arr = JSON.parse(fs.readFileSync(f, 'utf8'))
    for (const w of arr) {
      const cn = cnOf(w)
      if (!cn) continue
      const k = norm(w.word)
      if (!k) continue
      if (!reuse.has(k)) reuse.set(k, cn)
    }
  }
  console.log('复用索引词数', reuse.size)

  // 2) 找出缺释义的词条
  const missing = []   // {dict, file, idx, word}
  const perDict = []
  for (const d of targets) {
    const f = path.join(WORD_DIR, d.url)
    if (!fs.existsSync(f)) continue
    const arr = JSON.parse(fs.readFileSync(f, 'utf8'))
    let n = 0
    for (let i = 0; i < arr.length; i++) {
      if (cnOf(arr[i])) continue
      n++
      const w = arr[i].word || ''
      const key = norm(w)
      if (reuse.has(key)) continue
      missing.push({ dict: d.name, file: f, idx: i, word: w, key })
    }
    perDict.push({ name: d.name, file: f, missing: n, total: arr.length })
  }
  const totalMissing = perDict.reduce((s, x) => s + x.missing, 0)
  console.log('六~九年级缺释义词条总数', totalMissing)
  for (const x of perDict) console.log('  ', x.name, x.missing, '/', x.total)

  if (probe) {
    await page?.close?.()
    const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')
    const b = await chromium.launch({ headless: true })
    page = await (await b.newContext()).newPage()
    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 30000 })
    const sample = missing.slice(0, 8).map(x => x.word)
    console.log('样本', sample)
    console.log(await translateInPage(sample, 4))
    await b.close()
    return
  }

  // 3) 翻译缺失的
  const cache = fs.existsSync(CACHE_FILE)
    ? JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'))
    : {}
  const uniq = []
  const seen = new Set()
  for (const m of missing) {
    if (cache[m.key]) continue
    if (seen.has(m.key)) continue
    seen.add(m.key)
    uniq.push(m.word)
  }
  console.log('待翻译唯一词', uniq.length)

  const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')
  const b = await chromium.launch({ headless: true })
  page = await (await b.newContext()).newPage()
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 30000 })

  let failed = 0
  const BATCH = 300
  for (let i = 0; i < uniq.length; i += BATCH) {
    const chunk = uniq.slice(i, i + BATCH)
    const res = await translateInPage(chunk, CONC)
    res.forEach((v, idx) => {
      if (v) cache[norm(chunk[idx])] = v
      else failed++
    })
    fs.mkdirSync(path.dirname(CACHE_FILE), { recursive: true })
    fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 1), 'utf8')
    console.log(`  ${Math.min(i + BATCH, uniq.length)}/${uniq.length} 失败${failed}`)
  }

  // 4) 回填
  const changed = new Map()
  for (const m of missing) {
    const cn = reuse.get(m.key) || cache[m.key]
    if (!cn) continue
    if (!changed.has(m.file)) changed.set(m.file, [])
    changed.get(m.file).push({ idx: m.idx, cn })
  }
  for (const [file, items] of changed) {
    const arr = JSON.parse(fs.readFileSync(file, 'utf8'))
    for (const it of items) {
      if (cnOf(arr[it.idx])) continue
      arr[it.idx].synos = [{ cn: it.cn }]
    }
    if (apply) {
      fs.writeFileSync(file, JSON.stringify(arr, null, 2) + '\n', 'utf8')
    }
  }
  console.log(apply ? `已写盘，涉及 ${changed.size} 个词书` : `DRY-RUN：会改 ${changed.size} 个词书（加 --apply 真写）`)
  await b.close()
}

main().catch(e => { console.error('失败:', e && e.message); process.exit(1) })
