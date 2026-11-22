/**
 * 等 Nuxt 应用「可以交互」
 * ======================================
 * 为什么需要：dev server 首屏要现编译页面 + 现执行客户端 bundle，
 * 在这之前页面虽然已有 SSR 出来的按钮（能点、能读文字），但
 *  - Vue 还没 hydrate → 点击事件没绑上 → 点了没反应；
 *  - onMounted 还没跑 → 它会把 `ladderKey` 强制拉回默认阶梯，
 *    于是「点前 primary」在不同用例里五花八门（实测出现过 人教版PEP/莱芜 两种）。
 *
 * 典型假红：`_check_placement_ladders.js` 点「人教版 PEP」后加载的仍是
 * 默认阶梯（莱芜），报「没看到请求：PEPChuZhong7_1_T…」。
 * 实测固定 sleep 900ms 必假红、1200ms 也偶发假红、1500ms 才稳。
 *
 * 判定信号：**`useNuxtApp().isHydrating === false`**
 *   - `isHydrating` 是 Nuxt 官方的「还在 hydrate 吗」标志；
 *     它变 false = hydrate 全部完成 + onMounted 已执行完。
 *   - 实测时间线：t=973ms isHydrating=true（SSR 态，primary 还是初始值）
 *     → t=1228ms isHydrating=false（primary 已被 onMounted 改成默认值）。
 *   - **`#__nuxt.__vue_app__` 存在 ≠ hydrate 完** —— 它在 mount 过程中就有了，
 *     比 onMounted 早，用它会踩到「onMounted 还没跑」的坑。
 *   - `window.useNuxtApp` 只在 **Nuxt dev 模式**暴露（生产构建没有），
 *     所以生产环境要退回「点一次 + 等选中态变化」的兜底（见尺子里的重试逻辑）。
 *
 * 用法：await waitForInteractive(page)
 */
const { chromium } = require('./_playwright')

/**
 * 等页面可交互
 * @param {import('playwright').Page} page
 * @param {number} timeout 毫秒
 * @returns {Promise<boolean>} 是否在超时前就绪
 */
async function waitForInteractive(page, timeout = 30000) {
  try {
    await page.waitForFunction(
      () => {
        const fn = window.useNuxtApp
        if (typeof fn !== 'function') return false
        try {
          return fn().isHydrating === false
        } catch (e) {
          return false
        }
      },
      null,
      { timeout, polling: 200 }
    )
    return true
  } catch (e) {
    return false
  }
}

/** 等指定元素出现且可见 */
async function waitVisible(page, selector, timeout = 20000) {
  try {
    await page.waitForSelector(selector, { state: 'visible', timeout })
    return true
  } catch (e) {
    return false
  }
}

module.exports = { waitForInteractive, waitVisible, chromium }
