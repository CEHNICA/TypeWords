/**
 * 构建本地离线查词索引
 * =====================
 * 为什么：点单词查释义原本走 Supabase 云端接口（本地没配 → 必然失败），
 *      失败后弹 **有道整页 iframe** → 加载外网广告页，慢得要死，还一堆按钮。
 *
 * 做法：把 public/dicts/en/word/*.json（207 份本地词库，28 万词条 / 3.2 万唯一词）
 *      离线合并成一份精简索引 data/word-index.json：
 *        word(小写) → { word, phonetic0, phonetic1, trans[], sentences[], phrases[], synos[], src }
 *      服务端读它建内存 Map，查词 O(1)、零网络。
 *
 * 为什么用 Node 而不是 Python：
 *   data/ 在 .gitignore 里（索引不进版本库），换机器/重新 clone 就得能重建。
 *   Node 版只依赖 Node 本身，跟着 pnpm 走，谁 clone 下来都能一条命令重建。
 *
 * 取舍：
 *  - etymology（词源长文）/ relWords（相关词）**不收** → 索引能压到 ~20MB，
 *    查词浮层本来也不显示这俩；
 *  - sentences / phrases / synos 各只留前 2 条 → 够用且体积可控；
 *  - 同一词出现在多份词库里 → **按优先级取第一条**（优先级见 PRIORITY），
 *    高频教辅（CET4/高考中考）优先于冷门考试词书。
 *
 * 用法：
 *    node scripts/build-word-index.mjs            # 构建
 *    node scripts/build-word-index.mjs --stat     # 只看统计，不写文件
 */
import { createReadStream } from 'node:fs'
import { mkdir, readdir, readFile, stat, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const DICT_DIR = join(ROOT, 'public', 'dicts', 'en', 'word')
const OUT_FILE = join(ROOT, 'data', 'word-index.json')

// 优先级：靠前的高频教辅优先（越常用越要准）
const PRIORITY = [
  'CET4_T.json',
  'CET6_T.json',
  'CET-4-frequency.json',
  'GaoKao_3500.json',
  'ZhongKaoHeXin.json',
  'gaokao-yuedu-gaopin.json',
  'GaoKaoZhenTiHeXinGaoPin.json',
  '3000_ClassRoom_English_Words.json',
  '4000_Essential_English_Words-meaning.json',
  'top2000words.json',
  'frequently_used_word01.json',
  'frequently_used_word02.json',
  'Oxford3000.json',
  'Oxford5000.json',
  'Macmillan7000.json',
  'Duolingo_Vocabulary_B1.json',
  'Duolingo_Vocabulary_B2.json',
  'Duolingo_Vocabulary_C1.json',
  'Longman_Communication_3000.json',
  'Merriam_Webster_sVocabularyBuilder.json',
  'ielts-807.json',
  'IELTSKingLu807.json',
  'IELTS_3_T.json',
  'IELTS_XDF_7000.json',
  'HeQiong_IELTS.json',
  'DuckCircle_IELTS.json',
  'IELTS_disorder.json',
  'TOEFL_3_T.json',
  'TOEFL_ZhangHongYan.json',
  'GRE_1500.json',
  'GRE_3_T.json',
  'GRE3000_3_T.json',
  'ZaiYaoNiMing_GRE3000.json',
  'KaoYan_3_T.json',
  'KaoYan_2024.json',
  'PETS_3.json',
  'PETS3-2023.json',
  'PTE_Basic_apeuni.json',
  'PTE_Advanced_apeuni.json',
  'ket2021.json',
  'sat_3_t.json',
  'BEC_2_T.json',
  'BEC_3_T.json',
  'GMAT_3_T.json',
  'TOEIC.json',
  'nce-new-1.json',
  'nce-new-2.json',
  'nce-new-3.json',
  'nce-new-4.json',
  'jiJiao3-1.json',
  'jiJiao3-2.json',
  'jiJiao4-1.json',
  'jiJiao4-2.json',
  'jiJiao5-1.json',
  'jiJiao5-2.json',
  'jiJiao6-1.json',
  'jiJiao6-2.json',
  'jiJiao7-1.json',
  'jiJiao7-2.json',
  'jiJiao8-1.json',
  'jiJiao8-2.json',
  'jiJiao9.json',
  'PEP_SL_XiaoXue3_1_t.json',
  'PEP_SL_XiaoXue4_1_t.json',
  'PEP_SL_XiaoXue5_1_t.json',
  'PEP_SL_XiaoXue6_1_t.json',
  'PEPChuZhong7_1_T.json',
  'PEPChuZhong8_1_T.json',
  'PEPChuZhong9_1_T.json',
  'PEPGaoZhong_1_T.json',
  'PEPGaoZhong_2_T.json',
  'PEPGaoZhong_3_T.json',
  'Newwaiyan7-1.json',
  'Newwaiyan7-2.json',
  'WaiYanSheChuZhong_1_T.json',
  'WaiYanSheChuZhong_2_T.json',
  'WaiYanSheChuZhong_3_T.json',
  'BeiShiGaoZhong_1_T.json',
  'BeiShiGaoZhong_2_T.json',
  'BeiShiGaoZhong_3_T.json',
  'LWCZ-6-1.json',
  'LWCZ-6-2.json',
  'LWCZ-7-1.json',
  'LWCZ-7-2.json',
  'LWCZ-8-1.json',
  'LWCZ-8-2.json',
  'LWCZ-9-1.json',
  'LWXX-3-1.json',
  'LWXX-3-2.json',
  'LWXX-4-1.json',
  'LWXX-4-2.json',
  'LWXX-5-1.json',
  'LWXX-5-2.json',
]

const LIMIT_SENTENCES = 2
const LIMIT_PHRASES = 2
const LIMIT_SYNOS = 2

async function pickFiles() {
  const names = new Set(await readdir(DICT_DIR))
  const ordered = PRIORITY.filter(n => names.has(n))
  const priSet = new Set(PRIORITY)
  const rest = [...names].filter(n => n.endsWith('.json') && !priSet.has(n)).sort()
  return [...ordered, ...rest]
}

/** 把词库条目压成查词浮层要用的最小字段。 */
function slim(it) {
  const trans = []
  for (const t of (it.trans || []).slice(0, 8)) {
    if (!t || typeof t !== 'object') continue
    const cn = String(t.cn || '').trim()
    if (!cn) continue
    trans.push({ pos: String(t.pos || '').trim(), cn })
  }
  if (!trans.length) {
    // 有些词库只有 synos 没有 trans → 从 synos 里兜底
    for (const s of (it.synos || []).slice(0, 8)) {
      if (!s || typeof s !== 'object') continue
      const cn = String(s.cn || '').trim()
      if (!cn) continue
      trans.push({ pos: String(s.pos || '').trim(), cn })
    }
  }

  const sentences = (it.sentences || [])
    .slice(0, LIMIT_SENTENCES)
    .filter(s => s && typeof s === 'object' && String(s.c || '').trim())
    .map(s => ({ c: String(s.c).trim(), cn: String(s.cn || '').trim() }))

  const phrases = (it.phrases || [])
    .slice(0, LIMIT_PHRASES)
    .filter(s => s && typeof s === 'object' && String(s.c || '').trim())
    .map(s => ({ c: String(s.c).trim(), cn: String(s.cn || '').trim() }))

  const synos = (it.synos || [])
    .slice(0, LIMIT_SYNOS)
    .filter(s => s && typeof s === 'object')
    .map(s => ({
      pos: String(s.pos || '').trim(),
      cn: String(s.cn || '').trim(),
      ws: (Array.isArray(s.ws) ? s.ws : []).slice(0, 4).filter(w => typeof w === 'string'),
    }))

  return {
    word: String(it.word || '').trim(),
    phonetic0: String(it.phonetic0 || '').trim(),
    phonetic1: String(it.phonetic1 || '').trim(),
    trans,
    sentences,
    phrases,
    synos,
  }
}

async function main() {
  const statOnly = process.argv.includes('--stat')
  const files = await pickFiles()
  console.log(`词库目录: ${DICT_DIR}`)
  console.log(`词库数量: ${files.length}`)

  const index = {}
  let totalEntries = 0
  const t0 = Date.now()

  for (let i = 0; i < files.length; i++) {
    const name = files[i]
    const path = join(DICT_DIR, name)
    let arr
    try {
      arr = JSON.parse(await readFile(path, 'utf-8'))
    } catch (e) {
      console.log(`[SKIP] ${name}: ${e.message}`)
      continue
    }
    if (!Array.isArray(arr)) continue
    for (const it of arr) {
      if (!it || typeof it !== 'object') continue
      const w = String(it.word || '').trim()
      if (!w) continue
      totalEntries++
      const key = w.toLowerCase()
      if (key in index) continue // 优先级更高的词库已经收了
      const slimIt = slim(it)
      if (!slimIt.trans.length && !slimIt.synos.length) continue
      slimIt.src = name.slice(0, -5)
      index[key] = slimIt
    }
    if ((i + 1) % 20 === 0 || i === files.length - 1) {
      console.log(`  [${i + 1}/${files.length}] ${name}  唯一词=${Object.keys(index).length}  用时=${((Date.now() - t0) / 1000).toFixed(1)}s`)
    }
  }

  console.log('-'.repeat(60))
  console.log(`总词条: ${totalEntries}  唯一词: ${Object.keys(index).length}  用时: ${((Date.now() - t0) / 1000).toFixed(1)}s`)

  if (statOnly) return

  await mkdir(dirname(OUT_FILE), { recursive: true })
  await writeFile(OUT_FILE, JSON.stringify(index), 'utf-8')
  const size = (await stat(OUT_FILE)).size
  console.log(`已写入: ${OUT_FILE}  (${(size / 1024 / 1024).toFixed(1)} MB)`)
}

main().catch(e => {
  console.error(e)
  process.exitCode = 1
})
