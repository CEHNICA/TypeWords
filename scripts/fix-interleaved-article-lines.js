/*
定点修复 4 处「逐字交错」的课文乱序句
======================================

根因：课本 PDF 里有些版块是**两栏并排**（左边歌谣/正文 + 右边注释框），
extract-textbook-articles.py 的行合并把两栏的字符按 x 坐标交错拼一起，
产出 "HWeh jautm ap lso ut nodf efur nth!e sun." 这种鬼东西。

修复：这里直接用 **PDF 原文**（已人工核对过）替换掉乱序行，不重跑整个提取流程。

涉及：
  LWXX_3_2 #21  → "He jumps under the sun." + "What a lot of fun!"
  LWXX_4_1 #12  → "What a magic box!"
  LWCZ_8_1 #21  → PDF page 95 完整原文（3 句）
  LWCZ_9_1 #30  → "A class yearbook is usually a book of photos and memories that students create at the end of the school year to remember their time at school."

用法： node scripts/fix-interleaved-article-lines.js [--dry-run]
*/
const fs = require('fs')
const path = require('path')

const ROOT = path.resolve(__dirname, '..')
const DIR = path.join(ROOT, 'public', 'dicts', 'en', 'article')

// 修复表：文件 -> 段落（以 \n\n 分）-> 行号 -> 新内容
// 新内容若含 \n，表示替换成多行（会被拆成多句）
const FIXES = [
  {
    book: 'LWXX_3_2',
    idx: 21,
    // 定位用的原行前缀
    find: 'HWeh jautm ap lso ut nodf efur nth!e sun.',
    replace: [
      'He jumps under the sun.',
      'What a lot of fun!',
    ],
    source: '小学五四-三年级下册.pdf p54（两栏交错，PDF 原文：He jumps under the sun. / What a lot of fun!）',
  },
  {
    book: 'LWXX_4_1',
    idx: 12,
    find: 'OWpheant, ac lmosaeg.ic box!',
    replace: ['What a magic box!'],
    source: '小学五四-四年级上册.pdf p46 y=659 x=126',
  },
  {
    book: 'LWCZ_8_1',
    idx: 21,
    find: 'Millions of germs from one sneeze can travel up to about 8 metres at a speed of 160 kilometres per hpoeoupr!leT hberesea tgheer mins tchaons est agye rimn sth, eth aeiyr, caannd gife ot tshicekr If you sneeze, always cover your nose and mouth.',
    replace: [
      'Millions of germs from one sneeze can travel up to about 8 metres at a speed of 160 kilometres per hour!',
      'These germs can stay in the air, and if other people breathe in those germs, they can get sick too.',
      'If you sneeze, always cover your nose and mouth.',
    ],
    source: '初中五四-八年级上册.pdf p95 y=325~414',
  },
  {
    book: 'LWCZ_9_1',
    idx: 30,
    find: 'A class yearbook is usually am beomookr ioefs p thhoatto sst uadnedn ts create at the end of the school year to remember their time at school.',
    replace: [
      'A class yearbook is usually a book of photos and memories that students create at the end of the school year to remember their time at school.',
    ],
    source: '初中五四-九年级全一册.pdf p140 x=346 注释框',
  },
  {
    book: 'LWXX_5_1',
    idx: 21,
    find: 'C··amabaio dLuuetn p6a2 pAe.rD.',
    replace: [
      'This is Cai Lun. He was born in about 62 A.D.',
      'What did he do?',
      'He made paper.',
    ],
    source: '小学五四-五年级上册.pdf p78（三栏人物卡 Sima Qian / Cai Lun / Sun Simiao 被逐字交错）',
  },
  {
    book: 'LWXX_5_1',
    idx: 21,
    find: 'S·· awbimboroooatuk eQt a1ia 4gn5r eBa.Ct.',
    replace: [
      'This is Sun Simiao. He was born in 581 A.D.',
      'What did he do?',
      'He found many herbs.',
    ],
    source: '小学五四-五年级上册.pdf p78（三栏人物卡交错）',
  },
  {
    book: 'LWXX_5_1',
    idx: 21,
    find: 'He was What did he do?',
    replace: [
      'He was born in about 145 B.C.',
      'What did he do?',
      'He wrote a great book.',
    ],
    source: '小学五四-五年级上册.pdf p78 y=285~369',
  },
  {
    book: 'LWCZ_8_2',
    idx: 2,
    find: "Yine st,h tish astc'hs oroigl hfto.r / tNwoo, yI'evaer sb.een The first sentence of each paragraph is usually the topic sentence.",
    replace: [
      'The first sentence of each paragraph is usually the topic sentence.',
      "You just started yesterday, didn't you?",
    ],
    source: '初中五四-八年级下册.pdf —— Notes 注释框被插进正文首行',
  },
]

function main() {
  const dry = process.argv.includes('--dry-run')
  let hit = 0
  for (const fx of FIXES) {
    const file = path.join(DIR, fx.book + '.json')
    if (!fs.existsSync(file)) {
      console.log(`✗ 缺文件 ${fx.book}.json`)
      continue
    }
    const arr = JSON.parse(fs.readFileSync(file, 'utf8'))
    const a = arr[fx.idx]
    if (!a) {
      console.log(`✗ ${fx.book} 没有 #${fx.idx}`)
      continue
    }
    const paras = (a.text || '').split('\n\n')
    let found = false
    for (let pi = 0; pi < paras.length; pi++) {
      const lines = paras[pi].split('\n')
      for (let li = 0; li < lines.length; li++) {
        if (lines[li].trim() === fx.find) {
          lines.splice(li, 1, ...fx.replace)
          paras[pi] = lines.join('\n')
          found = true
          break
        }
      }
      if (found) break
    }
    if (!found) {
      console.log(`✗ ${fx.book} #${fx.idx} 没找到目标行（可能已修过）`)
      continue
    }
    a.text = paras.join('\n\n')
    if (!dry) fs.writeFileSync(file, JSON.stringify(arr, null, 2) + '\n', 'utf8')
    hit++
    console.log(`✓ ${fx.book} #${fx.idx}  已修（${fx.replace.length} 行）  来源: ${fx.source}`)
  }
  console.log(dry ? `\nDRY-RUN：命中 ${hit} 处，未写盘` : `\n完成：修了 ${hit} 处`)
}

main()
