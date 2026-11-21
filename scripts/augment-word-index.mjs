/**
 * 扩充本地离线词典：CC-CEDICT 补缺 + 预生成词形映射
 * ================================================
 * 为什么：
 *   用户反馈「很多单词本地词典没有收录」。实测那篇导入文章里 **27% 的词落空**，
 *   落空的大头是两类：
 *     1) **词形变化**：asks / years / things / guided / shows / provides …
 *        教辅词书只收原形（ask / year / thing / guide / show / provide），查变形必落空；
 *     2) **专有名词与低频派生词**：riemann / claude / mathematicians / automorphic …
 *        207 本教辅词书天然不收。
 *
 * 两条补法（都本地、零外网、零版权风险）：
 *   A. **词形映射表**（data/word-forms.json）：对每个已收录词预生成常见屈折形态，
 *      查词 miss 时回退到原形取释义，浮层标注「原形 xxx」。
 *   B. **CC-CEDICT**（公共领域中英词典，CC BY-SA 4.0，mdbg.net 官方导出）：
 *      补专有名词、派生词、缩写，**只补教辅词书没有的**，不覆盖已有释义。
 *
 * 用法：
 *   node scripts/augment-word-index.mjs            # 合并 + 写文件
 *   node scripts/augment-word-index.mjs --stat     # 只看统计
 */
import { existsSync } from 'node:fs'
import { mkdir, readFile, readdir, stat, writeFile } from 'node:fs/promises'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { gunzipSync } from 'node:zlib'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const INDEX_FILE = join(ROOT, 'data', 'word-index.json')
const FORMS_FILE = join(ROOT, 'data', 'word-forms.txt')
const CEDICT_FILE = join(ROOT, 'data', 'cedict.txt.gz')
const DICT_DIR = join(ROOT, 'public', 'dicts', 'en')

const POS_MAP = [
  ['vt.', 'vt.'],
  ['vi.', 'vi.'],
  ['adj.', 'adj.'],
  ['adv.', 'adv.'],
  ['prep.', 'prep.'],
  ['conj.', 'conj.'],
  ['pron.', 'pron.'],
  ['num.', 'num.'],
  ['int.', 'int.'],
  ['interj.', 'interj.'],
  ['abbr.', 'abbr.'],
  ['n.', 'n.'],
  ['v.', 'v.'],
]

/** 从释义文本里猜词性：CC-CEDICT 释义常以 "n." / "vt." 之类开头 */
function guessPos(def) {
  const head = def.trim().slice(0, 12)
  for (const [k] of POS_MAP) if (head.toLowerCase().startsWith(k)) return k
  return ''
}

/** 释义清洗：压掉多余空白、去掉拼音括号残留 */
function cleanDef(s) {
  return s
    .replace(/\[.*?\]/g, '')
    .replace(/\s*\(\s*\)\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 80)
}

/**
 * 解析 CC-CEDICT → Map<英文小写, {pos, cn}[]>
 *
 * mdbg 官方导出的行格式：
 *   繁體 簡體 [拼音] /English/ /定义1/定义2/      ← 有英文对应词
 *   繁體 簡體 [拼音] /英文长句定义/                 ← 无英文对应词（这行没价值，跳过）
 * 所以英文 key 取**第一个斜杠字段**，且必须是像样的英文词/短语
 * （纯字母、≤3 词、不含括号数字）；中文释义取第二个斜杠字段，没有就用简体词本身。
 */
function parseCedict(txt) {
  const map = new Map()
  let rows = 0
  let properRows = 0
  // **坑**：文件是 CRLF，split('\n') 后每行尾部还带 \r；
  // 而 JS 正则的 `.` 不匹配 \r（行终止符），`...$` 会整行匹配失败。先把 CRLF 规整掉。
  for (const line of txt.replace(/\r\n/g, '\n').split('\n')) {
    if (!line || line[0] === '#') continue
    const m = line.match(/^(\S+)\s+(\S+)\s+\[[^\]]*\]\s*\/([^/]*)\/(.*)$/)
    if (!m) continue
    const [, trad, simp, eng, rest] = m
    const e = eng.trim()
    const defs = rest
      .replace(/^\//, '')
      .split('/')
      .map(s => cleanDef(s))
      .filter(Boolean)

    // ---- 路径 1：英文对应词本身就是个像样的单词/短语 ----
    if (/^[A-Za-z][A-Za-z\s'-]{0,38}$/.test(e) && !e.includes('(') && e.split(/\s+/).length <= 3) {
      const cn = (defs[0] || cleanDef(simp) || cleanDef(trad)).slice(0, 80)
      if (cn) {
        rows++
        const key = e.toLowerCase()
        let arr = map.get(key)
        if (!arr) map.set(key, (arr = []))
        if (arr.length < 3) arr.push({ pos: guessPos(cn), cn })
        continue
      }
    }

    // ---- 路径 2：专名（人名地名）----
    // CC-CEDICT 里专名的英文字段是长定义："Bernhard Riemann (1826–1866), German mathematician"
    // 中文在「简体词」那一列（黎曼）。取逗号前首部、每个词都大写开头的那个词做 key。
    const head = e
      .split('(')[0]
      .split(',')[0]
      .trim()
    const m2 = head.match(/^([A-Za-z][A-Za-z'.\-]*(?:\s+[A-Za-z][A-Za-z'.\-]*)*)\s*(\([^)]*\))?$/)
    if (!m2) continue
    const parts = m2[1].split(/\s+/)
    if (!parts.every(p => /^[A-Z]/.test(p))) continue // 不是全大写开头 → 不是专名
    const key = parts[parts.length - 1].toLowerCase()
    if (key.length < 3) continue
    const cn = (cleanDef(simp) || cleanDef(trad)).slice(0, 40)
    if (!cn) continue
    properRows++
    let arr = map.get(key)
    if (!arr) map.set(key, (arr = []))
    if (arr.length < 3) arr.push({ pos: '', cn })
  }
  return { map, rows, properRows }
}

/**
 * 常见不规则动词 / 名词 / 形容词变体
 * 规则生成不了这些：begin→began、take→taken、see→saw/seen、child→children……
 * 没有它们，用户文章里的 began / taken / children 永远查不到。
 */
const IRREGULAR = {
  begin: ['began', 'begun', 'begins', 'beginning'],
  take: ['took', 'taken', 'takes', 'taking'],
  see: ['saw', 'seen', 'sees', 'seeing'],
  go: ['went', 'gone', 'goes', 'going'],
  come: ['came', 'comes', 'coming'],
  get: ['got', 'gotten', 'gets', 'getting'],
  give: ['gave', 'given', 'gives', 'giving'],
  make: ['made', 'makes', 'making'],
  write: ['wrote', 'written', 'writes', 'writing'],
  say: ['said', 'says', 'saying'],
  know: ['knew', 'known', 'knows', 'knowing'],
  think: ['thought', 'thinks', 'thinking'],
  find: ['found', 'finds', 'finding'],
  tell: ['told', 'tells', 'telling'],
  become: ['became', 'becomes', 'becoming'],
  leave: ['left', 'leaves', 'leaving'],
  feel: ['felt', 'feels', 'feeling'],
  bring: ['brought', 'brings', 'bringing'],
  buy: ['bought', 'buys', 'buying'],
  catch: ['caught', 'catches', 'catching'],
  teach: ['taught', 'teaches', 'teaching'],
  eat: ['ate', 'eaten', 'eats', 'eating'],
  drink: ['drank', 'drunk', 'drinks', 'drinking'],
  speak: ['spoke', 'spoken', 'speaks', 'speaking'],
  break: ['broke', 'broken', 'breaks', 'breaking'],
  drive: ['drove', 'driven', 'drives', 'driving'],
  choose: ['chose', 'chosen', 'chooses', 'choosing'],
  grow: ['grew', 'grown', 'grows', 'growing'],
  throw: ['threw', 'thrown', 'throws', 'throwing'],
  draw: ['drew', 'drawn', 'draws', 'drawing'],
  wear: ['wore', 'worn', 'wears', 'wearing'],
  fly: ['flew', 'flown', 'flies', 'flying'],
  forget: ['forgot', 'forgotten', 'forgets', 'forgetting'],
  run: ['ran', 'runs', 'running'],
  swim: ['swam', 'swum', 'swims', 'swimming'],
  sing: ['sang', 'sung', 'sings', 'singing'],
  sleep: ['slept', 'sleeps', 'sleeping'],
  build: ['built', 'builds', 'building'],
  send: ['sent', 'sends', 'sending'],
  spend: ['spent', 'spends', 'spending'],
  lose: ['lost', 'loses', 'losing'],
  meet: ['met', 'meets', 'meeting'],
  pay: ['paid', 'pays', 'paying'],
  sell: ['sold', 'sells', 'selling'],
  sit: ['sat', 'sits', 'sitting'],
  stand: ['stood', 'stands', 'standing'],
  understand: ['understood', 'understands', 'understanding'],
  lead: ['led', 'leads', 'leading'],
  fight: ['fought', 'fights', 'fighting'],
  seek: ['sought', 'seeks', 'seeking'],
  deal: ['dealt', 'deals', 'dealing'],
  mean: ['meant', 'means', 'meaning'],
  bear: ['bore', 'borne', 'bears', 'bearing'],
  beat: ['beaten', 'beats', 'beating'],
  bite: ['bitten', 'bites', 'biting'],
  blow: ['blew', 'blown', 'blows', 'blowing'],
  burn: ['burnt', 'burns', 'burning'],
  fall: ['fell', 'fallen', 'falls', 'falling'],
  feed: ['fed', 'feeds', 'feeding'],
  flee: ['fled', 'flees', 'fleeing'],
  freeze: ['froze', 'frozen', 'freezes', 'freezing'],
  hide: ['hid', 'hidden', 'hides', 'hiding'],
  lend: ['lent', 'lends', 'lending'],
  light: ['lit', 'lights', 'lighting'],
  ride: ['rode', 'ridden', 'rides', 'riding'],
  ring: ['rang', 'rung', 'rings', 'ringing'],
  rise: ['rose', 'risen', 'rises', 'rising'],
  shake: ['shook', 'shaken', 'shakes', 'shaking'],
  steal: ['stole', 'stolen', 'steals', 'stealing'],
  stick: ['stuck', 'sticks', 'sticking'],
  sting: ['stung', 'stings', 'stinging'],
  strike: ['struck', 'strikes', 'striking'],
  swear: ['swore', 'sworn', 'swears', 'swearing'],
  sweep: ['swept', 'sweeps', 'sweeping'],
  swing: ['swung', 'swings', 'swinging'],
  tear: ['tore', 'torn', 'tears', 'tearing'],
  wake: ['woke', 'woken', 'wakes', 'waking'],
  weave: ['wove', 'woven', 'weaves', 'weaving'],
  lay: ['laid', 'laying'],
  hit: ['hit', 'hitting'],
  cut: ['cut', 'cutting'],
  put: ['put', 'putting'],
  set: ['set', 'setting'],
  shut: ['shut', 'shutting'],
  spread: ['spread', 'spreading'],
  lay2: [],
  win: ['won', 'wins', 'winning'],
  write2: [],
  child: ['children'],
  man: ['men'],
  woman: ['women'],
  person: ['people'],
  foot: ['feet'],
  tooth: ['teeth'],
  goose: ['geese'],
  mouse: ['mice'],
  life: ['lives'],
  wife: ['wives'],
  leaf: ['leaves'],
  knife: ['knives'],
  half: ['halves'],
  better: ['better', 'best'],
  good: ['better', 'best'],
  bad: ['worse', 'worst'],
  many: ['more', 'most'],
  much: ['more', 'most'],
  little: ['less', 'least'],
  far: ['farther', 'furthest', 'further', 'furthest'],
  old: ['older', 'oldest', 'elder', 'eldest'],
}

/**
 * 词形生成：对已收录的原形，生成常见屈折形态 → 原形
 * 规则保守：宁可漏，不产出错误映射（错映射会给出错误释义，比查不到更糟）。
 */
function generateForms(words) {
  const forms = {}
  const add = (f, base, force = false) => {
    if (!f || f === base) return
    if (!force && f in forms) return
    forms[f] = base
  }
  const VOWELS = 'aeiou'
  const isVowel = c => VOWELS.includes(c)
  const last = w => w[w.length - 1]
  const prev = w => w[w.length - 2]
  const doubleable = w =>
    w.length >= 3 &&
    !isVowel(last(w)) &&
    isVowel(prev(w)) &&
    !'wxy'.includes(last(w)) &&
    // 以 "ic" 结尾的词走 ic→ck 规则（mimic→mimicking），别再双写 c
    !w.endsWith('ic')

  // ---- 不规则变体先写（优先级最高）----
  // 例：lead→led。规则生成不出，只能靠表；而且词库里可能有脏条目（如 "le"）抢映射。
  for (const [base, variants] of Object.entries(IRREGULAR)) {
    if (!words.includes(base)) continue
    for (const v of variants) add(v, base, true)
  }

  for (const base of words) {
    // **只对单词做形态生成**：CC-CEDICT 里混着短语条目（according to / guided tour），
    // 对短语生成形态毫无意义，还会产出 "guided tourred" 这种垃圾。
    if (base.includes(' ') || base.includes("'")) continue
    // 名词复数 / 第三人称
    if (base.endsWith('y') && base.length > 2 && !isVowel(prev(base))) {
      add(base.slice(0, -1) + 'ies', base)
    } else if (/(s|x|z|ch|sh)$/.test(base)) {
      add(base + 'es', base)
    } else if (base.endsWith('o')) {
      add(base + 'es', base)
    } else {
      add(base + 's', base)
    }
    // 过去式
    if (base.endsWith('ic')) {
      // mimic → mimicked（ic → ck + ed）
      add(base.slice(0, -1) + 'cked', base)
    } else if (base.endsWith('e')) {
      add(base + 'd', base)
    } else if (base.endsWith('y') && base.length > 2 && !isVowel(prev(base))) {
      add(base.slice(0, -1) + 'ied', base)
    } else {
      add(base + 'ed', base)
      if (doubleable(base)) add(base + last(base) + 'ed', base)
    }
    // 进行时
    if (base.endsWith('ic')) {
      // mimic → mimicking（ic → ck + ing）
      add(base.slice(0, -1) + 'cking', base)
    } else if (base.endsWith('ee')) {
      // see → seeing（双 e 保留）
      add(base + 'ing', base)
    } else if (base.endsWith('ie')) {
      // lie → lying（去 e）
      add(base.slice(0, -2) + 'ying', base)
      add(base + 'ing', base)
    } else if (base.endsWith('e')) {
      // make → making（去 e）
      add(base.slice(0, -1) + 'ing', base)
      add(base + 'ing', base)
    } else if (base.endsWith('y') && base.length > 2 && !isVowel(prev(base))) {
      // simplify → simplifying（去 e + ing）
      add(base.slice(0, -1) + 'ying', base)
      add(base + 'ing', base)
    } else {
      add(base + 'ing', base)
      if (doubleable(base)) add(base + last(base) + 'ing', base)
    }
    // 比较级 / 最高级
    if (base.endsWith('e')) {
      add(base + 'r', base)
      add(base + 'st', base)
    } else if (base.endsWith('y') && base.length > 2 && !isVowel(prev(base))) {
      add(base.slice(0, -1) + 'ier', base)
      add(base.slice(0, -1) + 'iest', base)
    } else {
      add(base + 'er', base)
      add(base + 'est', base)
      if (doubleable(base)) {
        add(base + last(base) + 'er', base)
        add(base + last(base) + 'est', base)
      }
    }
    // 副词
    if (base.endsWith('y') && base.length > 2 && !isVowel(prev(base))) {
      add(base.slice(0, -1) + 'ily', base)
    } else if (base.endsWith('le')) {
      add(base.slice(0, -1) + 'y', base)
    } else {
      add(base + 'ly', base)
    }
    // 名词所有格
    add(base + "'s", base)
    add(base + "'", base)
  }

  // 不规则变体（已在前面优先写入）
  return forms
}

const CEDICT_URL = 'https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz'

/** 没词典文件就下一次（CC-CEDICT 公共领域中英词典，CC BY-SA 4.0） */
async function ensureCedict() {
  if (existsSync(CEDICT_FILE)) return true
  console.log('CC-CEDICT 未下载，正在下载（约 4MB，公共领域词典）...')
  try {
    const res = await fetch(CEDICT_URL)
    if (!res.ok) {
      console.warn(`CC-CEDICT 下载失败：HTTP ${res.status}，跳过扩充（词形映射照常生成）`)
      return false
    }
    const buf = Buffer.from(await res.arrayBuffer())
    await writeFile(CEDICT_FILE, buf)
    console.log(`CC-CEDICT 下载完成：${(buf.length / 1024 / 1024).toFixed(1)} MB`)
    return true
  } catch (e) {
    console.warn('CC-CEDICT 下载失败：', e?.message || e)
    return false
  }
}

async function main() {
  const statOnly = process.argv.includes('--stat')
  const index = JSON.parse(await readFile(INDEX_FILE, 'utf-8'))
  console.log(`原索引唯一词: ${Object.keys(index).length}`)

  // ---------- B. CC-CEDICT 补缺 ----------
  let cedictStats = { skipped: true }
  if (!statOnly) await ensureCedict()
  if (existsSync(CEDICT_FILE)) {
    const txt = gunzipSync(await readFile(CEDICT_FILE)).toString('utf8')
    const { map, rows, properRows } = parseCedict(txt)
    let added = 0
    for (const [key, arr] of map) {
      if (key in index) continue
      const trans = arr.slice(0, 3).map(x => ({ pos: x.pos, cn: x.cn }))
      if (!trans.length) continue
      index[key] = {
        word: key,
        phonetic0: '',
        phonetic1: '',
        trans,
        sentences: [],
        phrases: [],
        synos: [],
        src: 'CC-CEDICT',
      }
      added++
    }
    cedictStats = { rows, properRows, uniq: map.size, added, skipped: false }
    console.log(
      `CC-CEDICT: 词条行=${rows} 专名行=${properRows} 英文唯一词=${map.size} → 新增=${added}（不覆盖已有）`
    )
  } else {
    console.log('CC-CEDICT 未下载，跳过（放到 data/cedict.txt.gz）')
  }

  // ---------- A. 词形映射 ----------
  const keys = Object.keys(index)
  const forms = generateForms(keys)
  console.log(`词形映射: ${Object.keys(forms).length} 条（覆盖 ${keys.length} 个原形）`)

  // ---------- 覆盖率自测 ----------
  const probes = [
    'ask', 'asks', 'asked', 'asking', 'year', 'years', 'thing', 'things', 'show', 'shows',
    'provide', 'provides', 'mathematicians', 'riemann', 'guiding', 'guided',
    'use', 'uses', 'used', 'try', 'tried', 'tries', 'decades', 'taken', 'began', 'seeing',
    'claude', 'theta', 'fourier', 'children', 'men', 'women',
  ]
  const covered = probes.filter(w => w in index || w in forms)
  console.log(`样本词覆盖: ${covered.length}/${probes.length} → ${covered.join(' ')}`)
  const uncovered = probes.filter(w => !(w in index || w in forms))
  if (uncovered.length) console.log(`样本未覆盖: ${uncovered.join(' ')}`)

  if (statOnly) return

  await mkdir(dirname(INDEX_FILE), { recursive: true })
  await writeFile(INDEX_FILE, JSON.stringify(index), 'utf-8')
  const size1 = (await stat(INDEX_FILE)).size
  // 词形表用「每行 form<TAB>base」的纯文本，比 JSON 小 3~4 倍、解析也快。
  // **必须用 TAB 分隔**：base 里可能有空格（短语条目），用空格切会切错并覆盖别的映射。
  const formsText = Object.entries(forms).map(([f, b]) => `${f}\t${b}`).join('\n')
  await writeFile(FORMS_FILE, formsText, 'utf-8')
  const size2 = (await stat(FORMS_FILE)).size
  console.log('-'.repeat(60))
  console.log(
    `已写入 索引 ${(size1 / 1024 / 1024).toFixed(1)} MB（${keys.length} 词）/ 词形表 ${(size2 / 1024 / 1024).toFixed(1)} MB（${Object.keys(forms).length} 条）`
  )
}

main().catch(e => {
  console.error(e)
  process.exitCode = 1
})
