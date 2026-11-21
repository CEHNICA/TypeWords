/**
 * 扩充后覆盖率实测
 * 跑之前那篇导入文章，看还有多少词查不到
 */
import { readFile } from 'node:fs/promises'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const index = JSON.parse(await readFile(join(ROOT, 'data', 'word-index.json'), 'utf-8'))
const forms = new Map(
  (await readFile(join(ROOT, 'data', 'word-forms.txt'), 'utf-8'))
    .split('\n')
    .filter(Boolean)
    .map(l => {
      const sp = l.indexOf('\t')
      return [l.slice(0, sp), l.slice(sp + 1)]
    })
)
const articles = JSON.parse(await readFile(join(ROOT, 'data', 'local-articles.json'), 'utf-8'))

const STOP = new Set(
  ('the a an and or but if then than that this these those of to in on at by for with from as is are was were be been being it its i you he she they we me him her them my your his their our not no do does did doing have has had having will would shall should can could may might must there here when where what which who whom how why all any both each few more most other some such only own same so too very just don now o re ve ll d m y'
  ).split(' ')
)

const words = new Map()
for (const a of articles) {
  const text = (a.articles || []).map(x => x.text || '').join(' ')
  for (const w of text.toLowerCase().match(/[a-z][a-z'-]{1,20}/g) || []) {
    words.set(w, (words.get(w) || 0) + 1)
  }
}
const uniq = [...words.keys()].filter(w => !STOP.has(w))
const hit = uniq.filter(w => w in index)
const viaForm = uniq.filter(w => !(w in index) && forms.get(w) && forms.get(w) in index)
const miss = uniq.filter(w => !(w in index) && !(forms.get(w) && forms.get(w) in index))

console.log(`文章词（去停用词）: ${uniq.length}`)
console.log(`  索引直接命中: ${hit.length} (${((hit.length / uniq.length) * 100).toFixed(1)}%)`)
console.log(`  词形回退命中: ${viaForm.length} (${((viaForm.length / uniq.length) * 100).toFixed(1)}%)`)
console.log(`  仍查不到: ${miss.length} (${((miss.length / uniq.length) * 100).toFixed(1)}%)`)
console.log(`\n词形回退救回的词: ${viaForm.join(', ')}`)
console.log(`\n仍落空: ${miss.join(', ')}`)
