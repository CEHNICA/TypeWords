/**
 * 水平摸底测试（Placement Test）——难度阶梯数据
 * =================================================
 *
 * 干什么用的：给孩子/自己测「现在到底什么水平」，测完给出
 *   ① 年级水平定位（如「约五年级水平」）
 *   ② 词汇量估计（估算认识多少个词）
 *   ③ 已掌握 / 待加强词表（可导出 CSV 给老师）
 *   ④ 建议从哪本教材接着学
 *
 * 阶梯怎么来的：本地词库里躺着全套小学教材词表（人教 PEP、人教版新起点、
 * 外研版、冀教版、剑桥 JOIN IN、KET…）。每一级 = 某个年级的词表，
 * 年级越高词越难，于是「年级」天然就是难度轴。
 *
 * ids 对应 public/list/word.json 里的词库 id。改这里之前先跑
 * `_tools/check_placement.py`，它会校验每个 id 真实存在。
 */

export interface PlacementStep {
  /** 显示名，如「五年级上」 */
  label: string
  /** 该年级的词库 id（可多个，运行时合并去重） */
  ids: number[]
}

export interface PlacementLadder {
  key: string
  /** 教材名，如「人教版 PEP」 */
  name: string
  /** 一句话说明 */
  desc: string
  /** 这条阶梯摸到顶之后往哪走（小学阶梯要指路去初中，初中阶梯才谈高中） */
  afterTop: string
  /** 从易到难的阶梯 */
  steps: PlacementStep[]
}

/** 词库 id → 名字，运行时从 /list/word.json 取 */
export type DictResourceMap = Map<number, { name: string, url: string, length: number }>

export const PLACEMENT_LADDERS: PlacementLadder[] = [
  {
    key: 'lw',
    name: '莱芜五四制（山东版）',
    desc: '山东莱芜五四制英语（常被叫「鲁教版」）。小学三上到五下，六年级起接初中五四，一路排到九年级。',
    afterTop: '这一套是初中五四制，初中都过了，可以上高中词汇表了。',
    steps: [
      { label: '三年级上', ids: [253] },
      { label: '三年级下', ids: [254] },
      { label: '四年级上', ids: [255] },
      { label: '四年级下', ids: [256] },
      { label: '五年级上', ids: [257] },
      { label: '五年级下', ids: [258] },
      { label: '六年级上', ids: [259] },
      { label: '六年级下', ids: [260] },
      { label: '七年级上', ids: [261] },
      { label: '七年级下', ids: [262] },
      { label: '八年级上', ids: [263] },
      { label: '八年级下', ids: [264] },
      { label: '九年级', ids: [265] },
    ],
  },
  {
    key: 'pep',
    name: '人教版 PEP',
    desc: '小学三年级起，衔初中，一路到九年级。最通用的版本。',
    afterTop: '初中都过了，可以上高中词汇表了。',
    steps: [
      { label: '三年级上', ids: [141] },
      { label: '三年级下', ids: [142] },
      { label: '四年级上', ids: [143] },
      { label: '四年级下', ids: [144] },
      { label: '五年级上', ids: [145] },
      { label: '五年级下', ids: [146] },
      { label: '六年级上', ids: [147] },
      { label: '六年级下', ids: [148] },
      { label: '初中七年级上', ids: [161] },
      { label: '初中七年级下', ids: [162] },
      { label: '初中八年级上', ids: [163] },
      { label: '初中八年级下', ids: [164] },
      { label: '初中九年级', ids: [165] },
    ],
  },
  {
    key: 'pep_new',
    name: '人教版新起点（小学）',
    desc: '一二年级就有词，适合从零起步摸底。新起点初中另见「人教版 PEP」。',
    afterTop: '人教新起点只有小学。转去「人教版 PEP」接着测初中，或者直接上高中词汇表。',
    steps: [
      { label: '一年级上', ids: [149] },
      { label: '一年级下', ids: [150] },
      { label: '二年级上', ids: [151] },
      { label: '二年级下', ids: [152] },
      { label: '三年级上', ids: [153, 141] },
      { label: '三年级下', ids: [154, 142] },
      { label: '四年级上', ids: [155, 143] },
      { label: '四年级下', ids: [156, 144] },
      { label: '五年级上', ids: [157, 145] },
      { label: '五年级下', ids: [158, 146] },
      { label: '六年级上', ids: [159, 147] },
      { label: '六年级下', ids: [160, 148] },
    ],
  },
  {
    key: 'wy',
    name: '外研版（小学）',
    desc: '外研社新版教材（小学部分）。初中另见「外研社（初中）」。',
    afterTop: '外研版这套是小学。转去「外研社（初中）」接着测初中。',
    steps: [
      { label: '一年级上', ids: [187] },
      { label: '一年级下', ids: [188] },
      { label: '二年级上', ids: [189] },
      { label: '二年级下', ids: [190] },
      { label: '三年级上', ids: [191, 199] },
      { label: '三年级下', ids: [192, 200] },
      { label: '四年级上', ids: [193, 201] },
      { label: '四年级下', ids: [194, 202] },
      { label: '五年级上', ids: [195, 203] },
      { label: '五年级下', ids: [196, 204] },
      { label: '六年级上', ids: [197, 205] },
      { label: '六年级下', ids: [198, 206] },
    ],
  },
  {
    key: 'wy_junior',
    name: '外研社（初中）',
    desc: '外研社初中教材，七年级上到九年级下。',
    afterTop: '外研初中都过了，可以上高中词汇表了。',
    steps: [
      { label: '七年级上', ids: [177] },
      { label: '七年级下', ids: [180] },
      { label: '八年级上', ids: [181] },
      { label: '八年级下', ids: [182] },
      { label: '九年级上', ids: [183] },
      { label: '九年级下', ids: [184] },
    ],
  },
  {
    key: 'jie',
    name: '冀教版',
    desc: '河北等地区用的冀教版本，小学三年级起，一路到九年级。',
    afterTop: '初中都过了，可以上高中词汇表了。',
    steps: [
      { label: '三年级上', ids: [222] },
      { label: '三年级下', ids: [223] },
      { label: '四年级上', ids: [224] },
      { label: '四年级下', ids: [225] },
      { label: '五年级上', ids: [226] },
      { label: '五年级下', ids: [227] },
      { label: '六年级上', ids: [228] },
      { label: '六年级下', ids: [229] },
      { label: '初中七年级上', ids: [230] },
      { label: '初中七年级下', ids: [231] },
      { label: '初中八年级上', ids: [232] },
      { label: '初中八年级下', ids: [233] },
      { label: '初中九年级', ids: [234] },
    ],
  },
  {
    key: 'joinin',
    name: '剑桥小学英语 JOIN IN',
    desc: '综合词表（不分年级），出报告时只给词汇量估计。',
    afterTop: '这套词表不分年级，按掌握比例估的词汇量。可以直接进 CET-4 或高考 3500 词库练。',
    steps: [
      { label: '剑桥小学综合', ids: [237] },
    ],
  },
  {
    key: 'ket',
    name: '剑桥少儿英语 KET',
    desc: 'KET 词汇表（约等于小学毕业水平），只给词汇量估计。',
    afterTop: 'KET 是小学毕业水平。转去「人教版 PEP」接着测初中，或者直接上高中词汇表。',
    steps: [
      { label: 'KET 综合', ids: [111] },
    ],
  },
]

/**
 * 每次升降几级。1 = 一级一级来（对小学生最自然：从最简单一级开始，
 * 答对升一级、答错退一级，慢慢逼近能力边界）；改成 2 会收敛更快但跳得生硬。
 */
export const PLACEMENT_STEP_JUMP = 1

/** 报告里的词汇量参考基线：小学阶段常见词汇量 */
export const PLACEMENT_REFERENCE = {
  primaryTotal: 700,
  juniorTotal: 1600,
}
