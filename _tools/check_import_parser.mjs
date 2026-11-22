/**
 * 本地词表导入 —— 解析层单测尺子
 * ==================================================
 *
 * 为什么单独一个尺子：
 *   解析层（app/core/utils/custom-word-import.ts）是纯函数、零依赖，
 *   边界用例（引号、字段内换行、BOM、GBK、坏行、重复词、表头识别）浏览器实测看不见，
 *   但恰恰最容易错。所以这里用 Node 直接 import TS 源码跑断言。
 *
 * Node 24 原生支持 type stripping，直接 import .ts 即可（--experimental-strip-types 已默认开启）。
 * 用法：node _tools/check_import_parser.mjs
 */
import {
  parseDelimited,
  detectColumns,
  buildWords,
  matchField,
  normalizeHeader,
  guessDelimiter,
  isValidWord,
  decodeBuffer,
} from '../app/core/utils/custom-word-import.ts'

let failed = 0
function check(name, ok, detail = '') {
  if (!ok) failed++
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + (ok ? '' : '  —— ' + detail))
}
function eq(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected)
  check(name, ok, ok ? '' : '实际=' + JSON.stringify(actual) + ' 期望=' + JSON.stringify(expected))
}

// ---------- 1. 表头归一化 ----------
eq('归一化去空格', normalizeHeader('  单 词  '), '单词')
eq('归一化去 BOM', normalizeHeader('\uFEFF单词'), '单词')
eq('归一化转小写', normalizeHeader('Word'), 'word')

// ---------- 2. 表头别名匹配 ----------
eq('中文「单词」→ word', matchField('单词'), 'word')
eq('中文「音标①」→ phonetic0', matchField('音标①'), 'phonetic0')
eq('中文「音标②」→ phonetic1', matchField('音标②'), 'phonetic1')
eq('中文「翻译」→ trans', matchField('翻译'), 'trans')
eq('英文 word → word', matchField('word'), 'word')
eq('英文 Word（大小写）→ word', matchField('Word'), 'word')
eq('音标①变体「音标」→ phonetic0', matchField('音标'), 'phonetic0')
eq('认不出的表头 → null', matchField('随便写的'), null)
eq('空表头 → null', matchField(''), null)

// ---------- 3. 分隔符探测 ----------
eq('逗号分隔', guessDelimiter('a,b,c'), ',')
eq('制表符分隔', guessDelimiter('a\tb\tc'), '\t')
eq('分号分隔', guessDelimiter('a;b;c'), ';')
eq('单列 → 空串', guessDelimiter('hello'), '')

// ---------- 4. 文本解析 ----------
eq(
  '基本 CSV 解析',
  parseDelimited('word,trans\napple,苹果'),
  [
    ['word', 'trans'],
    ['apple', '苹果'],
  ]
)
eq(
  '引号字段含逗号',
  parseDelimited('"hello, world",x'),
  [['hello, world', 'x']]
)
eq(
  '引号内 "" 转义成单个引号',
  parseDelimited('"say ""hi""",y'),
  [['say "hi"', 'y']]
)
eq(
  '字段内换行',
  parseDelimited('"line1\nline2",z'),
  [['line1\nline2', 'z']]
)
eq(
  'CRLF 行尾',
  parseDelimited('a,b\r\nc,d'),
  [
    ['a', 'b'],
    ['c', 'd'],
  ]
)
eq('BOM 被剥掉', parseDelimited('\uFEFFword,trans'), [['word', 'trans']])
eq('空行被丢掉', parseDelimited('a,b\n\n\nc,d'), [
  ['a', 'b'],
  ['c', 'd'],
])
eq(
  '末尾字段为空也保留',
  parseDelimited('a,b,'),
  [['a', 'b', '']]
)

// ---------- 5. 列识别 ----------
{
  const { map, hasHeader } = detectColumns([
    ['单词', '音标', '翻译', '笔记'],
    ['apple', '/ˈæpəl/', '苹果', '备注'],
  ])
  eq('有表头时 hasHeader=true', hasHeader, true)
  eq('单词列下标', map.word, 0)
  eq('音标列下标', map.phonetic0, 1)
  eq('翻译列下标', map.trans, 2)
  eq('笔记列下标', map.note, 3)
}
{
  // 无表头：第 0 列当单词、第 1 列当翻译
  const { map, hasHeader } = detectColumns([
    ['apple', '苹果'],
    ['banana', '香蕉'],
  ])
  eq('无表头时 hasHeader=false', hasHeader, false)
  eq('无表头时 word 列=0', map.word, 0)
  eq('无表头时 trans 列=1', map.trans, 1)
}
{
  // 同一字段被多列命中 → 取第一列
  const { map } = detectColumns([
    ['单词', 'word', '翻译'],
    ['apple', 'apple2', '苹果'],
  ])
  eq('重复字段取第一列', map.word, 0)
}

// ---------- 6. 单词合法性 ----------
check('合法单词 apple', isValidWord('apple'))
check('合法单词 带撇号', isValidWord("don't"))
check('非法：纯数字', !isValidWord('123'))
check('非法：空串', !isValidWord(''))
check('非法：纯符号', !isValidWord('---'))
check('非法：超长', !isValidWord('a'.repeat(65)))
check('合法：64 字符', isValidWord('a'.repeat(64)))

// ---------- 7. 坏行 / 重复词 ----------
{
  const rows = [
    ['单词', '翻译'],
    ['apple', '苹果'],
    ['123', '数字'],
    ['apple', '重复'],
    ['banana', '香蕉'],
  ]
  const { map, hasHeader } = detectColumns(rows)
  const r = buildWords(rows, map, hasHeader)
  eq('有效单词 2 个', r.words.length, 2)
  eq('坏行 2 条（纯数字 + 重复）', r.errors.length, 2)
  eq('重复计数 1', r.duplicates, 1)
  eq('坏行原因含「重复」', r.errors[1].reason.includes('重复'), true)
  eq('坏行原因含字母要求', r.errors[0].reason.length > 0, true)
  eq('单词已小写去重键不影响取值', r.words[0].word, 'apple')
  eq('翻译被带上', r.words[0].trans, '苹果')
}
{
  // 大小写不同算同一个词
  const rows = [
    ['单词'],
    ['Apple'],
    ['apple'],
  ]
  const { map, hasHeader } = detectColumns(rows)
  const r = buildWords(rows, map, hasHeader)
  eq('大小写不同算重复', r.duplicates, 1)
  eq('只保留第一个', r.words.length, 1)
}
{
  // 空单词行直接跳过，不算坏行
  const rows = [
    ['单词'],
    ['apple'],
    [''],
  ]
  const { map, hasHeader } = detectColumns(rows)
  const r = buildWords(rows, map, hasHeader)
  eq('空单词行不报错', r.errors.length, 0)
  eq('空单词行不计数为重复', r.duplicates, 0)
}
{
  // 音标/笔记列被正确取到
  const rows = [
    ['单词', '音标①', '音标②', '笔记'],
    ['apple', '/a/', '/b/', 'note1'],
  ]
  const { map, hasHeader } = detectColumns(rows)
  const r = buildWords(rows, map, hasHeader)
  eq('音标① 取到', r.words[0].phonetic0, '/a/')
  eq('音标② 取到', r.words[0].phonetic1, '/b/')
  eq('笔记 取到', r.words[0].note, 'note1')
}

// ---------- 8. 编码回退 ----------
{
  const utf8 = new TextEncoder().encode('单词,翻译\napple,苹果')
  const r1 = decodeBuffer(utf8.buffer)
  eq('UTF-8 解码', r1.text.includes('苹果'), true)
  eq('UTF-8 标记', r1.encoding.includes('UTF-8') || r1.encoding.includes('utf-8'), true)
}
{
  // GBK：先造一个非法 UTF-8 序列，再手工构造 GBK 字节
  // "中文" 的 GBK 编码 = D6 D0 CE C4
  const gbk = new Uint8Array([0xd6, 0xd0, 0xce, 0xc4])
  const r2 = decodeBuffer(gbk.buffer)
  eq('GBK 回退解码出中文', r2.text, '中文')
  eq('GBK 有编码标记', /gbk/i.test(r2.encoding), true)
}

console.log('')
console.log('-'.repeat(60))
console.log('失败项合计: ' + failed)
process.exit(failed ? 1 : 0)
