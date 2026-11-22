"""尺子：仓库文本文件里不能有控制字符（PDF 抽取噪声 / 转义序列事故）

判据：
  1) 任何被 git 跟踪的文本文件里不能出现 C0 控制字符
     （除 \\t \\n \\r 三个合法空白）
  2) 特别检查 AGENTS.md / README.md —— 这里的噪声会**肉眼吃掉行首字符**
     （'\\x07' BEL 会让终端把上一个字符顶掉，看起来像 'requently_used_words03'）

踩过的坑（2026-11-22）：
  用 PowerShell here-string 写 Python 补丁脚本时，脚本里如果有
  'app' / 'background' / 'fix_dict' 这类**普通英文单词**，
  Python 会把 '\\a' '\\b' '\\f' 解释成 BEL / BS / FF 控制字符！
  → 写进文件后行首字符被吃掉，肉眼完全看不出来，
    只有 grep/打印时才暴露。

  防法：补丁脚本里**不要用带反斜杠的转义序列拼普通单词**；
  要么用双反斜杠，要么用 raw string，要么分两次写。

用法: python _tools/check_ctrl_chars.py
退出码 0 = 全过。
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 允许的：制表符、换行、回车。其余 C0 全禁。
CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

TEXT_EXT = {
    ".md", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".json",
    ".txt", ".yml", ".yaml", ".ps1", ".sh", ".css", ".scss", ".html",
    ".mjs", ".cjs", ".env.example", ".gitignore", ".gitattributes",
}

# 第三方压缩库：里面本来就有控制字符（xlsx/jszip 的 codepage 表），
# 不是我们写的代码，排除掉。
VENDOR_PREFIXES = ("public/libs/",)


def is_vendor(rel):
    return any(rel.startswith(p) for p in VENDOR_PREFIXES)


def tracked_files():
    out = subprocess.run(
        ["git", "-C", ROOT, "ls-files", "-z"],
        capture_output=True,
    )
    return [f for f in out.stdout.decode("utf-8", "replace").split("\0") if f]


def main():
    files = tracked_files()
    bad = []
    for rel in files:
        if is_vendor(rel):
            continue
        ext = os.path.splitext(rel)[1].lower()
        base = os.path.basename(rel)
        if ext not in TEXT_EXT and not base.startswith("."):
            continue
        p = os.path.join(ROOT, rel)
        if not os.path.isfile(p):
            continue
        try:
            with open(p, "rb") as f:
                raw = f.read()
        except OSError:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.split("\n"), 1):
            m = CTRL.search(line)
            if m:
                bad.append((rel, i, m.group(0), line.strip()[:90]))

    print("扫描 %d 个被跟踪文件" % len(files))
    if not bad:
        print("控制字符: 0 处")
    else:
        print("控制字符: %d 处" % len(bad))
        for rel, ln, ch, text in bad[:30]:
            print("  %s:%d  [%r]  %s" % (rel, ln, ch, text))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
