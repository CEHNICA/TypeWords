// 摸底：词库清单 vs 磁盘文件 vs 课本年级覆盖
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const dictDir = path.join(root, 'public', 'dicts', 'en', 'word')
const listPath = path.join(root, 'public', 'list', 'word.json')

const list = JSON.parse(fs.readFileSync(listPath, 'utf8'))
console.log('list/word.json 条目数：', list.length)

const onDisk = fs.readdirSync(dictDir).filter(f => f.endsWith('.json'))
const byUrl = new Map(list.map(it => [it.url, it]))

// 1) 磁盘上有但清单里没有 → 界面里选不到
const orphan = onDisk.filter(f => !byUrl.has(f))
// 2) 清单里有但磁盘上没有 → 点了会 404
const missingFile = list.filter(it => !onDisk.includes(it.url))
console.log('\n磁盘有但清单没有（界面选不到）：', orphan.length)
orphan.forEach(f => console.log('  ', f))
console.log('清单有但磁盘没有（点了 404）：', missingFile.length)
missingFile.forEach(it => console.log('  ', it.url, it.name))

// 3) 课本类词库的年级覆盖
const gradeRe = /(ChuZhong|GaoZhong|XiaoXue|LWCZ|LWXX|jiJiao|waiyan|Ne[w]?waiyan|Newwaiyan|BeiShi|WaiYanShe|Shangxue|junior|beijing)/
const textbooks = list.filter(it => gradeRe.test(it.url + it.name))
console.log('\n课本类词库条目：', textbooks.length)
const byFamily = new Map()
for (const it of textbooks) {
  const key = it.url.replace(/-?\d.*$/, '')
  if (!byFamily.has(key)) byFamily.set(key, [])
  byFamily.get(key).push(it.url)
}
for (const [k, v] of [...byFamily].sort()) {
  console.log(' ', k.padEnd(22), v.length + '册', '|', v.sort().join(' '))
}

// 4) 每个词库的实际词数
const counts = {}
for (const f of onDisk) {
  try {
    const j = JSON.parse(fs.readFileSync(path.join(dictDir, f), 'utf8'))
    counts[f] = (Array.isArray(j) ? j : j.words || []).length
  } catch { counts[f] = -1 }
}
console.log('\n课本类词库词数：')
for (const it of textbooks.sort((a, b) => a.url.localeCompare(b.url))) {
  console.log(`  ${it.url.padEnd(30)} ${String(counts[it.url]).padStart(6)}  ${it.name}`)
}
