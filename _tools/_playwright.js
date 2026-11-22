/**
 * Playwright 解析（不写死本机全局安装路径）
 * ======================================================
 * 之前每个尺子都硬编码 `require('C:/Users/<本机用户名>/AppData/Roaming/npm/node_modules/playwright')`，
 * 推到公开仓库等于泄露本机用户名，而且换机器 / 换安装方式就崩。
 *
 * 现在按顺序找：
 *   1. 环境变量 PLAYWRIGHT_MODULE（指定模块目录或模块名）
 *   2. 本地 node_modules（仓库装了依赖的情况）
 *   3. 全局 npm root（`npm root -g`）
 *   4. 直接 require('playwright')
 *
 * 用法：const { chromium } = require('./_playwright')  （_tools/ 下）
 *       或 const { chromium } = require('../_tools/_playwright')
 */
const { execSync } = require('child_process')
const fs = require('fs')
const path = require('path')

function tryRequire(spec) {
  try {
    return require(spec)
  } catch (e) {
    return null
  }
}

function globalNpmRoot() {
  try {
    const out = execSync('npm root -g', { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] })
    return out.trim()
  } catch (e) {
    return null
  }
}

function resolvePlaywright() {
  const env = process.env.PLAYWRIGHT_MODULE
  if (env) {
    const m = tryRequire(env) || tryRequire(path.join(env, 'playwright'))
    if (m) return m
    throw new Error(
      'PLAYWRIGHT_MODULE 指向的模块找不到：' + env +
      '\n  可设成 playwright 模块目录，或直接设模块名。'
    )
  }

  // 本地 node_modules
  let dir = __dirname
  for (let i = 0; i < 6; i++) {
    const local = path.join(dir, 'node_modules', 'playwright')
    if (fs.existsSync(local)) {
      const m = tryRequire(local)
      if (m) return m
    }
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }

  // 全局 npm root
  const g = globalNpmRoot()
  if (g) {
    const m = tryRequire(path.join(g, 'playwright'))
    if (m) return m
  }

  // 裸 require（NODE_PATH 里）
  const m = tryRequire('playwright')
  if (m) return m

  throw new Error(
    '找不到 playwright。请任选一种：\n' +
    '  1) npm i -D playwright && npx playwright install chromium\n' +
    '  2) npm i -g playwright && npx playwright install chromium\n' +
    '  3) 设环境变量 PLAYWRIGHT_MODULE=<playwright 模块目录>'
  )
}

module.exports = resolvePlaywright()
