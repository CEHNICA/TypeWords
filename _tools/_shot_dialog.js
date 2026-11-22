const { chromium } = require('./_playwright');

const path = require('path')
const ROOT = path.join(__dirname, '..')
const OUT = path.join(ROOT, '_shots')

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto('http://localhost:5567/articles');
  await page.waitForTimeout(4000);

  // 切中文界面（新开的上下文默认英文）
  await page.evaluate(() => {
    const el = [...document.querySelectorAll('*')].find(
      (e) => e.children.length === 0 && e.textContent.trim() === '中文' && e.closest('footer, .footer, body')
    );
    if (el) el.click();
  });
  await page.waitForTimeout(1500);

  // 打开「导入文章」弹窗（中文或英文都试）
  const clicked = await page.evaluate(() => {
    const el = [...document.querySelectorAll('div')].find(
      (e) => e.children.length === 0 && ['导入文章', 'Import Article'].includes(e.textContent.trim())
    );
    if (el) el.click();
    return { found: !!el, body: document.body.innerText.slice(0, 200) };
  });
  if (!clicked.found) { console.log('NOT FOUND:', JSON.stringify(clicked)); await browser.close(); return; }
  await page.waitForTimeout(1200);

  // 填点内容，让界面有真实感
  const filled = await page.evaluate(() => {
    const dlg = document.querySelector('.import-article');
    if (!dlg) return false;
    const inputs = [...dlg.querySelectorAll('input')].filter((i) => i.type !== 'file');
    const areas = [...dlg.querySelectorAll('textarea')];
    const setVal = (el, v) => {
      const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    };
    setVal(inputs[0], '小学英语课文');
    setVal(inputs[1], 'Lesson 1 Good Morning');
    setVal(inputs[2], '第一课 早上好');
    setVal(areas[0], 'Good morning, everyone. It is a fine day today.\nWe are going to have an English class now.\nPlease listen carefully and read after me.');
    setVal(areas[1], '大家早上好，今天天气不错。\n我们马上要上英语课了。\n请仔细听，跟我读。');
    return true;
  });
  await page.waitForTimeout(800);

  // 选中一个真实文件，看看文件名胶囊
  try {
    const fileInput = await page.$('.import-article input[type=file]');
    if (fileInput) {
      await fileInput.setInputFiles(path.join(__dirname, 'samples', 'my_article_en.txt'));
      await page.waitForTimeout(800);
    }
  } catch (e) {
    console.log('setInputFiles failed:', e.message);
  }

  await page.screenshot({ path: OUT + '/_shot_import_after.png' });

  // 展开高级设置，再截一张
  await page.evaluate(() => {
    const d = document.querySelector('.ia-advanced');
    if (d) d.open = true;
  });
  await page.waitForTimeout(500);
  await page.screenshot({ path: OUT + '/_shot_import_after_open.png' });

  // 结构体检：两个「选择文件」按钮的纵向位置
  const geo = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.ia-texts .ia-btn')].map((b) => {
      const r = b.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) };
    });
    const dlg = document.querySelector('.import-article');
    const dr = dlg ? dlg.getBoundingClientRect() : null;
    return { btns, dlg: dr ? { w: Math.round(dr.width), h: Math.round(dr.height) } : null };
  });
  console.log('filled=', filled, JSON.stringify(geo));
  await browser.close();
})();
