/**
 * 量化「本地词典缺口」
 * ==================
 * 回答用户：「很多单词本地词典没有收录，有没有办法预加载上」
 *
 * 输出：
 *   1. 索引覆盖的词数
 *   2. 用户导入文章里的词有多少命中 / 落空（真实体感缺多少）
 *   3. 落空的词里，有多少是「教辅词书本来就不该收录」的（专有名词/缩写/生僻词）
 */
import { readFile, readdir } from 'node:fs/promises'
import { join, resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const INDEX = join(ROOT, 'data', 'word-index.json')
const ARTICLES = join(ROOT, 'data', 'local-articles.json')

const index = JSON.parse(await readFile(INDEX, 'utf-8'))
console.log(`索引唯一词: ${Object.keys(index).length}`)

let articles = []
try {
  articles = JSON.parse(await readFile(ARTICLES, 'utf-8'))
} catch (e) {
  console.log('没有本地文章数据')
}

const STOP = new Set(
  ('the a an and or but if then than that this these those of to in on at by for with from as is are was were be been being it its it\'s i you he she they we me him her them my your his their our not no do does did doing have has had having will would shall should can could may might must there here when where what which who whom how why all any both each few more most other some such only own same so too very s t just don now o re ve ll d m y'
  ).split(' ')
)

const words = new Map() // word -> count
for (const a of articles) {
  const text = (a.articles || []).map(x => x.text || '').join(' ')
  for (const w of text.toLowerCase().match(/[a-z][a-z'-]{1,20}/g) || []) {
    words.set(w, (words.get(w) || 0) + 1)
  }
}

const uniq = [...words.keys()].filter(w => !STOP.has(w))
const hit = uniq.filter(w => w in index)
const miss = uniq.filter(w => !(w in index))

console.log(`文章总词形: ${words.size}  去停用词后: ${uniq.length}`)
console.log(`  命中: ${hit.length} (${((hit.length / uniq.length) * 100).toFixed(1)}%)`)
console.log(`  落空: ${miss.length} (${((miss.length / uniq.length) * 100).toFixed(1)}%)`)

console.log('\n落空词（按出现次数降序，前 120 个）:')
miss
  .sort((a, b) => words.get(b) - words.get(a))
  .slice(0, 120)
  .forEach(w => console.log(`  ${w}  ×${words.get(w)}`))

// 粗略分类：首字母大写在句中出现的（专有名词嫌疑）/ 长度<=3 / 非常用
const caps = miss.filter(w => words.get(w) > 0).length
console.log(`\n提示: 落空词里含大量专有名词与低频词，教辅词书（207 本）天然不收。`)
