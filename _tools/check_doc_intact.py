"""尺子：Markdown 里的代码路径/命令不能是「掉了首字母」的残缺形态

背景（2026-11-22 真踩）：
  用 PowerShell here-string 写 Python 补丁脚本时，脚本正文里出现了
  普通英文单词 `node` / `app` / `background` / `frequently` / `fix_dict`。
  Python 会把源码里的 `\\n` `\\a` `\\b` `\\f` 解释成
  **换行 / BEL / BS / FF** 控制字符 → 写进文件后，
  **紧跟其后的字符被控制字符吃掉行首**（终端渲染时表现为「行首少一个字母」）。

  后果：AGENTS.md 里出现 `ode scripts/build-word-index.mjs`、
  `requently_used_words03_level3` 这类残缺内容 ——
  **肉眼扫过去根本发现不了**（看着像正常单词的一部分）。

判据：
  1) Markdown 里出现的**反引号包裹的代码片段**、
     以及行首的 `node ` / `npx ` 等常见命令，
     不能以「掉了首字母」的形态出现。
  2) 具体做法：维护一个「已知完整形态」白名单前缀清单，
     检查文中是否出现「疑似掉首字母」的变体：
       node→ode / app→pp / background→ackground / frequently→requently ...
     判据用「全文出现该词根但从来没出现完整形态」→ 报可疑。

  更稳的通用做法（已实现的 check_ctrl_chars.py 兜底）：
     直接查控制字符。但**已经被吃掉首字母**的情况控制字符查不出来
     （字符是真没了，不是被控制字符替换）→ 所以要这份尺子补上。

用法: python _tools/check_doc_intact.py
退出码 0 = 全过。
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOCS = ["AGENTS.md", "README.md"]

# (完整形态, 掉首字母后的形态, 说明)
# 「掉首字母」只可能出现在**代码/命令/路径**上下文里，
# 普通散文与 CSS 单位（8px / 1439px）不算 —— 所以形态后面必须跟
# 命令词（install / run / build / .mjs / .py …）或路径分隔符。
TRIPLES = [
    # (完整形态, 掉首字母后的形态, 说明, 形态后必须跟的上下文)
    # broken 形态**不带尾空格**，follow 负责要求后跟命令词/路径分隔符。
    ("node", "ode", "node 命令", r"(?:\s|[/\\.])"),
    ("npx", "px", "npx 命令", r"(?:\s|[/\\.])"),
    ("app/", "pp/", "app/ 目录", r""),
    ("app/core", "pp/core", "app/core 路径", r""),
    ("background", "ackground", "英文单词 background", r"(?:的|词族|挂在)"),
    ("frequently", "requently", "英文单词 frequently", r"(?:_used)"),
    ("fix_dict", "ix_dict", "文件名 fix_dict", r"\.py"),
    ("ability", "bility", "英文单词 ability", r"(?:挂着)"),
    ("accountant", "ccountant", "英文单词 accountant", r"(?:挂着)"),
]


def main():
    bad = []
    for rel in DOCS:
        p = os.path.join(ROOT, rel)
        if not os.path.isfile(p):
            continue
        with io.open(p, encoding="utf-8") as fh:
            text = fh.read()
        for full, broken, desc, follow in TRIPLES:
            n_full = len(re.findall(re.escape(full), text))
            # 前置断言：broken 前面不能是字母或数字
            # （否则 CSS 单位 '8px' / '1439px' 会被当成掉首字母的 'px'）
            pat = r"(?<![A-Za-z0-9])" + re.escape(broken) + follow
            # 文档里举「反面教材」时会写成 '…ode…' 这种带省略号的形态 → 跳过
            hits = [m for m in re.finditer(pat, text)
                    if "…" not in text[max(0, m.start() - 2):m.end() + 2]]
            n_broken = len(hits)
            # **broken 形态在代码/命令上下文里出现就是错**，
            # 不管完整形态在别处出现过多少次 ——
            # 否则「别处有完整的」会把这里的坏漏掉（实测假阴性）。
            if n_broken:
                bad.append((rel, desc, full, broken, n_broken))

    if not bad:
        print("文档完整性: 0 处可疑（无「掉首字母」的残缺形态）")
        return 0
    print("文档完整性: %d 处可疑" % len(bad))
    for rel, desc, full, broken, n in bad:
        print("  %s: %s —— 只见「%s」(%d 次)，不见完整形态「%s」"
              % (rel, desc, broken, n, full))
    return 1


if __name__ == "__main__":
    sys.exit(main())
