/**
 * 本地词表导入 —— 浏览器端到端实测尺子
 * ==================================================
 *
 * 覆盖静态尺子（check_custom_import.py）盖不到的运行时行为：
 *   1. 词典列表页有「导入词表」入口，点开是对话框
 *   2. 选 CSV 文件 → 预览表出现、列识别提示正确、坏行/重复行有提示
 *   3. 词书名自动填成文件名（回归守护：isMergeMode 在 script 里漏写 .value 的坑）
 *   4. 点「导入」→ Toast 成功 → 落地到 /dict
 *   5. 新词书真的进了 store（bookList 里多了一本 custom 词典）
 *   6. 真的落盘了（IndexedDB 的 typing-word-dict 里能读回来，且词条在）
 *   7. 刷新后仍在（/words 页能看到新词书）
 *   8. 合并模式：传 targetId → 按钮文案变「合并到当前词典」，同名单词被跳过并计数
 *   9. 导入全程**不请求任何云端接口**（本地导入 = 纯本地）
 *
 * 踩过的坑（尺子自身写歪过的记录）：
 *   - file input 是 hidden 的（.hidden），用 setInputFiles 而不是点 label。
 *   - BaseButton 渲染成 div.base-button，不是 <button>。
 *   - 用**干净 profile**（newContext 无 storageState）→ IndexedDB 是空的，导入结果不会被历史数据污染。
 *   - **pinia 拿不到**：#__nuxt.__vue_app__._instance.provides 在 Nuxt4 里拿不到 base store。
 *     正解是拿任意 DOM 元素的 __vueParentComponent → appContext.provides[Symbol.for('pinia')]
 *     → pinia.state.value.base。
 *   - **IndexedDB 读法**：上游存的是 JSON 字符串 {val, version, updated_at}，
 *     词书在 `data.val.word.bookList`，不是 `data.word.bookList`。
 *   - **合并用例**：合并前词典里已有 apple/banana，如果再喂同一份 CSV 就是「两个都重复」，
 *     期望值必须按实际语义写（1 重复 + 1 新增 → 跳过 1、新增 1、总数 3）。
 */
const { chromium } = require('C:/Users/17321/AppData/Roaming/npm/node_modules/playwright')
const fs = require('fs')
const os = require('os')
const path = require('path')

const BASE = process.env.TW_BASE_URL || 'http://localhost:5567'
let failed = 0
function check(name, ok, detail = '') {
  if (!ok) failed++
  console.log((ok ? '[PASS] ' : '[FAIL] ') + name + (ok ? '' : '  —— ' + detail))
}
function info(name, detail = '') {
  console.log('[INFO] ' + name + (detail ? '  —— ' + detail : ''))
}

/** 临时文件目录（用完删） */
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'tw-import-'))

/** 文件名用中文，词书名默认取它 —— 顺带验证「词书名自动填成文件名」 */
const BOOK_FILE = '导入测试词表.csv'

/** 造一份 CSV：带表头、含重复行、含坏行（纯数字） */
const CSV_DUP = [
  '单词,音标①,翻译,笔记',
  'apple,/ˈæpəl/,苹果,水果',
  'banana,/bəˈnɑːnə/,香蕉,水果',
  'apple,/ˈæpəl/,苹果重复,重复行',
  '123,/n/,数字,坏行',
].join('\n')

/** 一份干净 CSV（无重复无坏行） */
const CSV_CLEAN = ['单词,翻译', 'orange,橙子', 'grape,葡萄'].join('\n')

/** 合并专用：1 个已存在（apple）+ 1 个新的（grape）→ 跳过 1、新增 1 */
const CSV_MERGE = ['单词,翻译', 'apple,苹果重复', 'grape,葡萄'].join('\n')

function writeTmp(name, content) {
  const p = path.join(TMP, name)
  // 用 Buffer 写 UTF-8，不带 BOM（另有一份带 BOM 的专门测 BOM）
  fs.writeFileSync(p, Buffer.from(content, 'utf8'))
  return p
}

/** 从页面里翻出 base store 的 word.bookList 快照 */
async function readStore(page) {
  return await page.evaluate(() => {
    const sym = Symbol.for('pinia')
    let pinia = null
    // 正解：pinia 用的是**本地** Symbol（Symbol('pinia')），不是 Symbol.for('pinia')，
    // 所以按 provides[Symbol.for('pinia')] 永远拿不到。走 app.config.globalProperties.$pinia。
    const rootEl = document.querySelector('#__nuxt')
    const app = rootEl && rootEl.__vue_app__
    if (app && app.config && app.config.globalProperties) {
      const p = app.config.globalProperties.$pinia
      if (p && p.state && p.state.value && p.state.value.base) pinia = p
    }
    // 兜底：provides 里翻（symbol 键要用 ownKeys 才能看到）
    if (!pinia && app && app._instance && app._instance.provides) {
      for (const k of Reflect.ownKeys(app._instance.provides)) {
        const v = app._instance.provides[k]
        if (v && v.state && v.state.value && v.state.value.base) {
          pinia = v
          break
        }
      }
    }
    if (!pinia) {
      const els = document.querySelectorAll('*')
      for (const el of els) {
        const c = el.__vueParentComponent
        if (!c) continue
        const p = c.appContext && c.appContext.provides
        if (!p) continue
        for (const k of Reflect.ownKeys(p)) {
          const v = p[k]
          if (v && v.state && v.state.value && v.state.value.base) {
            pinia = v
            break
          }
        }
        if (pinia) break
      }
    }
    if (!pinia) return { ok: false, reason: '拿不到 pinia state' }
    const base = pinia.state.value.base
    const custom = (base.word.bookList || []).filter(d => d.custom)
    return {
      ok: true,
      customCount: custom.length,
      customs: custom.map(d => ({
        id: d.id,
        name: d.name,
        category: d.category,
        length: d.length,
        words: (d.words || []).map(w => w.word),
      })),
    }
  })
}

/** 直接读 IndexedDB 里的落盘数据（上游存的是 {val, version, updated_at} 包装） */
async function readPersisted(page) {
  return await page.evaluate(async () => {
    const db = await new Promise((resolve, reject) => {
      const req = indexedDB.open('keyval-store')
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    })
    const raw = await new Promise((resolve, reject) => {
      const tx = db.transaction('keyval', 'readonly')
      const req = tx.objectStore('keyval').get('typing-word-dict')
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    })
    if (!raw) return { ok: false, reason: 'IndexedDB 里没有 typing-word-dict' }
    let data = raw
    if (typeof raw === 'string') {
      try {
        data = JSON.parse(raw)
      } catch (e) {
        return { ok: false, reason: '存盘内容不是合法 JSON' }
      }
    }
    // 上游存的是 {val: BaseState, version, updated_at}
    const state = data && data.val ? data.val : data
    const custom = (state && state.word && state.word.bookList ? state.word.bookList : []).filter(d => d.custom)
    return {
      ok: true,
      count: custom.length,
      customs: custom.map(d => ({
        id: d.id,
        name: d.name,
        length: d.length,
        words: (d.words || []).map(w => w.word),
      })),
    }
  })
}

async function main() {
  const csvDup = writeTmp(BOOK_FILE, CSV_DUP)
  const csvClean = writeTmp('clean.csv', CSV_CLEAN)
  const csvBom = writeTmp('bom.csv', '\uFEFF' + CSV_CLEAN)
  const csvMerge = writeTmp('merge.csv', CSV_MERGE)

  const browser = await chromium.launch({ headless: true })
  // 干净 profile：IndexedDB / localStorage 都是空的
  const ctx = await browser.newContext()
  // 上游 dict-list 首次访问会弹 Shepherd 新手引导，遮罩会挡住所有点击。
  // 上游自己认 localStorage['tour-guide']，提前打上（不污染真实浏览器，这是独立 profile）。
  await ctx.addInitScript(() => {
    try {
      localStorage.setItem('tour-guide', '1')
    } catch (e) {}
  })
  const page = await ctx.newPage()

  const pageErrors = []
  const cloudRequests = []
  page.on('pageerror', e => pageErrors.push('PAGEERROR ' + e.message))
  page.on('console', m => {
    if (m.type() === 'error') pageErrors.push('CONSOLE ' + m.text())
  })
  page.on('request', r => {
    const u = r.url()
    // 云端：supabase / 上游 API / 外网
    if (/supabase|typewords\.cc|api\./i.test(u) && !u.startsWith(BASE)) cloudRequests.push(u)
  })

  try {
    // ---------- 1. 词典列表页入口 ----------
    await page.goto(BASE + '/dict-list', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)

    const importBtn = page.locator('.base-button:has-text("导入词表")')
    check('词典列表页有「导入词表」按钮', (await importBtn.count()) > 0)
    if ((await importBtn.count()) === 0) throw new Error('入口按钮都没找到，后面没法测')
    await importBtn.first().click()
    await page.waitForTimeout(800)

    const dialog = page.locator('.import-word-list')
    check('点开出现导入对话框', (await dialog.count()) > 0)
    check('对话框有标题「导入词表」', ((await page.locator('.iw-title').first().textContent()) || '').includes('导入词表'))

    // ---------- 2. 选文件 → 预览 ----------
    const fileInput = page.locator('.import-word-list input[type=file]')
    check('有文件选择 input', (await fileInput.count()) > 0)
    await fileInput.first().setInputFiles(csvDup)
    await page.waitForTimeout(1500)

    check('预览区出现', (await page.locator('.iw-preview').count()) > 0)
    const previewText = (await page.locator('.iw-preview').first().innerText().catch(() => '')) || ''
    info('预览文本', previewText.replace(/\n/g, ' | ').slice(0, 200))

    check('预览里有 apple', previewText.includes('apple'))
    check('预览里有 banana', previewText.includes('banana'))
    check('列识别提示含「单词」', previewText.includes('单词'))
    check('列识别提示含「翻译」', previewText.includes('翻译'))
    // 重复 + 坏行 → 2 行有问题
    check('提示有问题的行（重复+坏行）', /\d+\s*行有问题/.test(previewText), previewText.slice(0, 120))
    check('提示里含「重复」', previewText.includes('重复'))
    // 有效单词 2 个（apple、banana；重复的 apple 和坏行 123 被跳过）
    check('有效单词数是 2', /共\s*2\s*个单词/.test(previewText), previewText.slice(0, 120))

    // 文件名标签
    const tagText = (await page.locator('.iw-tag').first().textContent().catch(() => '')) || ''
    check('显示已选文件名', tagText.includes(BOOK_FILE), tagText)

    // ---------- 2b. 词书名自动填成文件名（回归守护） ----------
    // 上游组件把 isMergeMode（computed）当裸 ref 用 → 恒 truthy → 这段永远不执行
    // → 词书名空着 → 提交被「给这本词书起个名字」拦下。
    const nameInput = page.locator('.import-word-list input[type=text]').first()
    const nameVal = (await nameInput.inputValue().catch(() => '')) || ''
    check('词书名自动填成文件名（去扩展名）', nameVal === '导入测试词表', '实际="' + nameVal + '"')

    // ---------- 3. 导入按钮可点 ----------
    const submitBtn = page.locator('.iw-foot .base-button:has-text("导入")')
    check('导入按钮存在', (await submitBtn.count()) > 0)
    check('导入按钮未被禁用', !(await submitBtn.first().getAttribute('class')).includes('disabled'))
    const disabledAttr = await submitBtn.first().getAttribute('disabled')
    check('导入按钮 disabled 属性为空', disabledAttr === null, String(disabledAttr))

    // ---------- 4. 点导入 → Toast + 落地 ----------
    await submitBtn.first().click()
    await page.waitForTimeout(2500)

    const toastText = (await page.locator('.toast-container').first().innerText().catch(() => '')) || ''
    info('Toast 文本', toastText.replace(/\n/g, ' ').slice(0, 160))
    check('有导入成功提示', toastText.includes('导入成功'), toastText)
    check('提示里的单词数是 2', /导入成功[:：]\s*2\s*个单词/.test(toastText), toastText)

    await page.waitForTimeout(1500)
    check('落地到 /dict 页面', page.url().includes('/dict'), page.url())

    // ---------- 5. 新词书进了 store ----------
    const storeInfo = await readStore(page)
    info('store 自定义词典', JSON.stringify(storeInfo).slice(0, 300))
    check('store 里多了一本自定义词典', storeInfo.ok && storeInfo.customCount >= 1, JSON.stringify(storeInfo).slice(0, 200))
    if (storeInfo.ok && storeInfo.customs.length) {
      const d = storeInfo.customs[storeInfo.customs.length - 1]
      check('新词典 id 带 custom- 前缀', String(d.id).startsWith('custom-dict-'), String(d.id))
      check('新词典归到「我的词表」分类', d.category === '我的词表', String(d.category))
      check('新词典名是自动填的词书名', d.name === '导入测试词表', String(d.name))
      check('新词典有 2 个词', d.words.length === 2, JSON.stringify(d.words))
      check('新词典词条正确（apple/banana）', d.words.includes('apple') && d.words.includes('banana'), JSON.stringify(d.words))
    }

    // ---------- 6. 真的落盘了（IndexedDB） ----------
    const persisted = await readPersisted(page)
    info('IndexedDB 落盘', JSON.stringify(persisted).slice(0, 250))
    check('IndexedDB 里能读到落盘的词典', persisted.ok, persisted.reason || '')
    check('落盘里有 1 本自定义词典', persisted.ok && persisted.count >= 1, JSON.stringify(persisted).slice(0, 200))
    if (persisted.ok && persisted.customs.length) {
      const d = persisted.customs[persisted.customs.length - 1]
      check('落盘词典名正确', d.name === '导入测试词表', String(d.name))
      check('落盘词典词数是 2', (d.words || []).length === 2, JSON.stringify(d.words))
      check('落盘词典 length 字段是 2', d.length === 2, String(d.length))
    }

    // ---------- 7. 刷新后仍在（/words 页能看到新词书） ----------
    await page.goto(BASE + '/words', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const wordsPageText = (await page.locator('body').innerText().catch(() => '')) || ''
    check('刷新后「我的词典」里出现了新词书', wordsPageText.includes('导入测试词表'), wordsPageText.slice(0, 200))
    const persistedAfterReload = await readPersisted(page)
    check(
      '刷新后落盘数据还在',
      persistedAfterReload.ok && persistedAfterReload.customs.some(d => d.name === '导入测试词表'),
      JSON.stringify(persistedAfterReload).slice(0, 200)
    )

    // ---------- 8. 合并模式 ----------
    // 先拿到新词典的 id
    const newDictId = storeInfo.ok && storeInfo.customs.length ? storeInfo.customs[storeInfo.customs.length - 1].id : ''
    if (newDictId) {
      await page.goto(BASE + '/import?type=word&targetId=' + encodeURIComponent(newDictId), {
        waitUntil: 'domcontentloaded',
      })
      await page.waitForTimeout(2000)
      const mergeBtn = page.locator('.iw-foot .base-button')
      const mergeText = (await mergeBtn.allTextContents().catch(() => [])) || []
      info('合并模式底部按钮', mergeText.join(' | '))
      check('合并模式按钮文案是「合并到当前词典」', mergeText.some(t => t.includes('合并到当前词典')), mergeText.join(' | '))

      // 合并模式不该有词书名输入框
      check('合并模式没有词书名输入框', (await page.locator('.iw-field .iw-label:has-text("词书名")').count()) === 0)

      // 选一份「1 重复 + 1 新增」的文件 → apple 已存在被跳过，grape 新增
      await page.locator('.import-word-list input[type=file]').first().setInputFiles(csvMerge)
      await page.waitForTimeout(1500)
      const mergeSubmit = page.locator('.iw-foot .base-button:has-text("合并到当前词典")')
      check('合并按钮可点', (await mergeSubmit.count()) > 0)
      await mergeSubmit.first().click()
      await page.waitForTimeout(2500)
      const mergeToast = (await page.locator('.toast-container').first().innerText().catch(() => '')) || ''
      info('合并 Toast', mergeToast.replace(/\n/g, ' ').slice(0, 160))
      check('合并成功提示里有「跳过」', mergeToast.includes('跳过'), mergeToast)
      check('跳过 1 个重复', /跳过\s*1\s*个重复/.test(mergeToast), mergeToast)
      check('新增 1 个单词', /导入成功[:：]\s*1\s*个单词/.test(mergeToast), mergeToast)

      // 合并后词数应该是 3（apple、banana 原有 + grape 新增）
      const afterMerge = await readPersisted(page)
      info('合并后词典', JSON.stringify(afterMerge).slice(0, 250))
      const merged = afterMerge.ok && afterMerge.customs.length ? afterMerge.customs[afterMerge.customs.length - 1] : null
      check('合并后词数是 3（1 重复被跳过 + 1 新增）', merged && merged.words.length === 3, JSON.stringify(merged && merged.words))
      check(
        '合并后词条是 apple/banana/grape',
        merged && merged.words.includes('apple') && merged.words.includes('banana') && merged.words.includes('grape'),
        JSON.stringify(merged && merged.words)
      )
      check('合并后 length 字段同步为 3', merged && merged.length === 3, String(merged && merged.length))
    } else {
      info('合并模式', '跳过：没拿到新词典 id')
      failed++
    }

    // ---------- 8b. 目标词典不存在时，文案不能说成「内置词典」 ----------
    await page.goto(BASE + '/import?type=word&targetId=custom-dict-not-exist', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2500)
    const missingText = (await page.locator('.iw-note').first().innerText().catch(() => '')) || ''
    info('目标不存在的提示', missingText.replace(/\n/g, ' ').slice(0, 120))
    check('目标不存在时提示「找不到这本词典」', missingText.includes('找不到这本词典'), missingText)
    check('目标不存在时不误报成「内置词典」', !missingText.includes('内置词典'), missingText)
    check(
      '目标不存在时降级成新建（有词书名输入框）',
      (await page.locator('.iw-field .iw-label:has-text("词书名")').count()) === 1
    )

    // ---------- 9. BOM 文件也能解析 ----------
    await page.goto(BASE + '/dict-list', { waitUntil: 'domcontentloaded' })
    await page.waitForTimeout(2000)
    await page.locator('.base-button:has-text("导入词表")').first().click()
    await page.waitForTimeout(600)
    await page.locator('.import-word-list input[type=file]').first().setInputFiles(csvBom)
    await page.waitForTimeout(1500)
    const bomText = (await page.locator('.iw-preview').first().innerText().catch(() => '')) || ''
    check('带 BOM 的 CSV 能识别表头', bomText.includes('单词'), bomText.slice(0, 120))
    check('带 BOM 的 CSV 解析出 2 个词', /共\s*2\s*个单词/.test(bomText), bomText.slice(0, 120))
    // 表头第一格不应残留 BOM 字符
    check('表头没有残留 BOM 字符', !bomText.includes('\uFEFF'))

    // ---------- 10. 全程无云端请求 ----------
    check('导入全程没有云端请求', cloudRequests.length === 0, cloudRequests.slice(0, 3).join(' | '))

    // ---------- 11. 无页面级报错 ----------
    const realErrors = pageErrors.filter(e => !/favicon|ERR_/.test(e))
    check('无页面级 JS 报错', realErrors.length === 0, realErrors.slice(0, 3).join(' | '))
  } finally {
    await ctx.close()
    await browser.close()
    try {
      fs.rmSync(TMP, { recursive: true, force: true })
    } catch (e) {}
  }

  console.log('')
  console.log('-'.repeat(60))
  console.log('失败项合计: ' + failed)
  // Windows 上 close 之后立刻 exit 会撞 libuv 断言（UV_HANDLE_CLOSING）→ 假红。
  // 判据优先级：尺子自己打印的失败计数 > 退出码。
  await new Promise(r => setTimeout(r, 500))
  process.exit(failed ? 1 : 0)
}

main().catch(e => {
  console.error('尺子自身崩溃：', e)
  process.exit(2)
})
