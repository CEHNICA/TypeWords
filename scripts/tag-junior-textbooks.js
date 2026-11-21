/**
 * 给「青少年英语」分类里六年级到九年级的课本册打 tag「六~九年级」
 * ==================================================
 *
 * 干什么用的：
 *   `/dict-list` 的分组组件 DictGroup.vue 默认只显示第一个 tag 页签
 *   （`currentTag = tagList[0]`）。「青少年英语」分类第一个页签是「通用」，
 *   于是打开页面只看到 4 本高考/中考词，六到九年级的 PEP / 外研 / 冀教
 *   课本册全藏在别的页签后面 —— 用户以为「这几年级的单词没弄上」。
 *
 *   这个脚本给那 30 册打上专属 tag，并把它排到该分类第一个页签，
 *   组内按 (年级, 册序, 教材) 排好：六上 → 六下 → 七上 → … → 九下。
 *
 *   只动 public/list/word.json 这份「本地补全的索引」，不动词库内容、不动前端。
 *
 * 怎么跑：
 *   node scripts/tag-junior-textbooks.js          # 改
 *   node scripts/tag-junior-textbooks.js --check  # 只看会怎么改
 *
 * 改完必须跑： python _tools/check_dict_list.py
 */
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const WORD_JSON = path.join(ROOT, 'public', 'list', 'word.json')

const TAG = '六~九年级'
const CAT_YOUNG = '青少年英语'
const NON_TEXTBOOK_TAGS = ['通用', '新概念英语', '其他']

const CN_NUM = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 }

// 教材识别：按 name 关键词。顺序敏感，先具体后笼统。
// [关键词, 教材序, 教材名]
const TEXTBOOK_RULES = [
  ['新外研', 4, '新外研版'],
  ['外研新起点', 3, '外研新起点'],
  ['外研', 2, '外研版'],
  ['新起点', 1, '人教版新起点'],
  ['人教版', 0, '人教版PEP'],
  ['冀教', 5, '冀教版'],
  ['牛津', 7, '牛津版'],
  ['上海', 6, '上海版'],
]

// 人教 PEP 的册子名只有「六年级上」这种光秃秃的名字，认不出「人教版」三个字，
// 只能靠 enName 认。
const PEP_EN_NAMES = new Set(['san1', 'san2', 'si1', 'si2', 'wu1', 'wu2',
  'liu1', 'liu2', 'qi1', 'qi2', 'ba1', 'ba2', 'jiu'])

function parseTextbook(name, enName) {
  if (PEP_EN_NAMES.has(enName)) return { order: 0, label: '人教版PEP' }
  if (typeof enName === 'string' && enName.startsWith('pep-sl-')) return { order: 1, label: '人教版新起点' }
  for (const [kw, order, label] of TEXTBOOK_RULES) {
    if (name.includes(kw)) return { order, label }
  }
  return null
}

function parseGrade(name) {
  let m = name.match(/冀教\s*([1-9])\s*(上|下)/)
  if (m) return { grade: Number(m[1]), vol: m[2] === '上' ? 1 : 2 }
  m = name.match(/([一二三四五六七八九])\s*年级\s*(全一册|上|下)?/)
  if (m) return { grade: CN_NUM[m[1]], vol: { 上: 1, 下: 2 }[m[2]] ?? 0 }
  m = name.match(/([1-9])\s*年级\s*(上|下)/)
  if (m) return { grade: Number(m[1]), vol: m[2] === '上' ? 1 : 2 }
  return null
}

/** 排序键：年级 → 册序 → 教材 */
function sortKey(b) {
  const name = b.name || ''
  let g = parseGrade(name)
  if (b.enName === 'SHjuniormiddleOxford') g = { grade: 6, vol: 0 }   // 上海初中牛津词汇 = 初中通用
  const tb = parseTextbook(name, b.enName)
  if (!g || !tb) return { grade: 99, vol: 99, order: 99, tb: '?' }
  return { grade: g.grade, vol: g.vol, order: tb.order, tb: tb.label }
}

function isTarget(b) {
  if (b.category !== CAT_YOUNG) return false
  const tags = b.tags || []
  if (tags.some(t => NON_TEXTBOOK_TAGS.includes(t))) return false
  if ((b.name || '').includes('高中')) return false
  const g = parseGrade(b.name || '')
  const grade = b.enName === 'SHjuniormiddleOxford' ? 6 : (g ? g.grade : null)
  if (grade === null || grade < 6 || grade > 9) return false
  return !!parseTextbook(b.name || '', b.enName)
}

function main() {
  const checkOnly = process.argv.includes('--check')
  const raw = fs.readFileSync(WORD_JSON, 'utf8')
  const data = JSON.parse(raw)

  const young = data.filter(b => b.category === CAT_YOUNG)
  const targets = young.filter(isTarget)

  if (targets.length !== 30) {
    console.error(`[ABORT] 识别到 ${targets.length} 册六~九年级课本册，预期 30 册 —— 判定规则可能坏了，先查`)
    process.exit(1)
  }

  const tagged = targets
    .map(b => ({ b, k: sortKey(b) }))
    .sort((x, y) =>
      x.k.grade - y.k.grade || x.k.vol - y.k.vol || x.k.order - y.k.order ||
      x.b.id - y.b.id)

  console.log(`识别到六~九年级课本册 ${targets.length} 册，排好序后：`)
  tagged.forEach(({ b, k }, i) => {
    console.log(`  ${String(i + 1).padStart(2)}. ${b.name.padEnd(22)} ${b.enName.padEnd(24)} ` +
      `年级${k.grade} 册${k.vol} ${k.tb}  tags=${JSON.stringify(b.tags)}`)
  })

  if (checkOnly) {
    console.log('\n(--check 只看不动)')
    return
  }

  // 1) 打 tag：放在 tags[0]，这样它就是这个册子贡献的第一个页签
  for (const { b } of tagged) {
    const rest = (b.tags || []).filter(t => t !== TAG)
    b.tags = [TAG, ...rest]
  }

  // 2) 重排「青少年英语」分类：打标的按年级排前面，其余保持原相对顺序
  const taggedIds = new Set(tagged.map(({ b }) => b.id))
  const restYoung = young.filter(b => !taggedIds.has(b.id))
  const newYoung = tagged.map(({ b }) => b).concat(restYoung)

  // 3) 写回文件，保持其它分类的位置不变
  let idx = 0
  const out = data.map(b => (b.category === CAT_YOUNG ? newYoung[idx++] : b))
  if (idx !== newYoung.length) {
    console.error('[ABORT] 重排后册数对不上')
    process.exit(1)
  }

  const text = JSON.stringify(out, null, 2) + '\n'
  fs.writeFileSync(WORD_JSON, text, 'utf8')
  console.log(`\n[OK] 已写入 ${WORD_JSON}`)
  console.log(`     青少年英语分类：${newYoung.length} 册（前 ${tagged.length} 册为「${TAG}」）`)
}

main()
