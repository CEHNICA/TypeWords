// 核对 word.json 的改动是否只有「重排 + 打 tag」，没别的
const { execSync } = require('child_process')
const fs = require('fs')
const path = require('path')
const ROOT = path.resolve(__dirname, '..')

const oldJ = JSON.parse(execSync('git -C "' + ROOT + '" show HEAD:public/list/word.json', { encoding: 'utf8', maxBuffer: 1e8 }))
const newJ = JSON.parse(fs.readFileSync(path.join(ROOT, 'public', 'list', 'word.json'), 'utf8'))

const om = new Map(oldJ.map(b => [b.id, b]))
const otherChanged = []
let tagChanged = 0
for (const b of newJ) {
  const o = om.get(b.id)
  if (!o) { otherChanged.push('新增册子 ' + b.id); continue }
  const a = JSON.stringify({ ...o, tags: null })
  const c = JSON.stringify({ ...b, tags: null })
  if (a !== c) otherChanged.push('内容变了 ' + b.name)
  if (JSON.stringify(o.tags) !== JSON.stringify(b.tags)) tagChanged++
}
console.log('册数', oldJ.length, '->', newJ.length)
console.log('id 集合一致:', newJ.length === oldJ.length && oldJ.every(b => om.has(b.id)))
console.log('除 tags 外有变化的册子:', otherChanged.length ? otherChanged.join(';') : '无')
console.log('tags 变化册数:', tagChanged)
const oi = oldJ.map(b => b.id), ni = newJ.map(b => b.id)
console.log('顺序变化的位置数:', oi.filter((v, i) => ni[i] !== v).length)
console.log('非青少年分类顺序保持:',
  JSON.stringify(oldJ.filter(b => b.category !== '青少年英语').map(b => b.id)) ===
  JSON.stringify(newJ.filter(b => b.category !== '青少年英语').map(b => b.id)))
const added = newJ.filter(b => (b.tags || []).includes('六~九年级')).map(b => b.name)
console.log('被打 tag 的册数:', added.length)
