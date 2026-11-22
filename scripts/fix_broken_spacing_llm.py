#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用 LLM 修复课文里的「断词 / 空格错位」
=========================================

背景：
  课本 PDF 的文本层在某些位置少了一个字形，那个位置被写成空格，于是
  "They" 变成 "T ey"、"often" 变成 "of en"、"fireworks" 变成 "fi reworks"。
  规则探测会误报（"good night" 拼起来也是词），所以让 LLM 裁决改不改。

流程：
  1. 读 _tools/check_article_broken.py --wide 导出的候选行
  2. 分批送 LLM：「只修断词，其余原样」
  3. 逐条校验（只接受「去掉空格后字母序列几乎不变」的修改）
  4. 写盘

用法：
  py -3 scripts/fix_broken_spacing_llm.py --probe
  py -3 scripts/fix_broken_spacing_llm.py            # dry-run
  py -3 scripts/fix_broken_spacing_llm.py --apply
"""
import os, sys, json, re, time, argparse, difflib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLE_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")
CAND = os.path.join(ROOT, "data", "broken-candidates.json")
CACHE = os.path.join(ROOT, "data", "broken-spacing-fixes.json")
CONFIG = os.path.join(os.path.expanduser("~"), ".minimax", "config.yaml")

SYSTEM = (
    "你是英语教材文本校对员。下面每行是一条从教材 PDF 里提取出来的英文句子，"
    "其中可能存在「PDF 少了一个字形、那个位置被写成空格」造成的断词错误。"
    "请逐行处理，规则如下："
    "1) 只有当句子里明显存在断词/空格错位时才修正，例如 "
    "'Th ey might' -> 'They might'、'of en' -> 'often'、'fi reworks' -> 'fireworks'、"
    "'gift s' -> 'gifts'、'astro- nauts' -> 'astronauts'；"
    "2) 正常的多词短语必须保持原样，例如 'kung fu'、'at least'、'next to'、"
    "'Hong Kong-Zhuhai-Macao'、'Hou Yi' 都不许合并；"
    "3) 不要改标点、不要改大小写（除非是把单词首字母还原成正确写法）、"
    "不要加词删词、不要翻译；"
    "4) 严格保持行号前缀（如 3. ）不变，一条输入对一行输出；"
    "5) 只输出处理后的句子本身。"
)


def load_cfg():
    import yaml
    c = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    out = []
    for pid, p in (c.get("custom_provider") or {}).items():
        o = p.get("options") or {}
        if o.get("apiKey") and o.get("baseURL"):
            out.append((o["apiKey"], o["baseURL"]))
    if out:
        return out
    p = c["provider"]["minimax"]
    return [(p["options"]["apiKey"], p["options"]["baseURL"])]


def call_llm(api_key, base_url, model, prompt, timeout=300, retries=6):
    import urllib.request
    url = base_url.rstrip("/") + "/v1/messages"
    body = {"model": model, "max_tokens": 32000, "temperature": 0.0,
            "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]}
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=data,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
            return "\n".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        except Exception as e:
            last = e
            code = getattr(e, "code", None)
            if code and code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(min(60, 5 * (2 ** attempt)))
    raise last


def parse_numbered(text):
    res = {}
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"^(\d+)\s*[.、]\s*(.*)$", line)
        if m:
            res[int(m.group(1))] = m.group(2).strip()
    return res


def letters_only(s):
    return re.sub(r"[^A-Za-z0-9]", "", s).lower()


def acceptable(old, new):
    """只接受两类修改：
       1) 去掉空白/标点后字母序列完全不变（纯空格错位修复）
       2) 字母序列恰好多出一个字母（PDF 少了一个字形）
    其它一律拒绝 —— LLM 顺手改词（"is it"->"is"、"bicycle"->"bike"）不算修复。
    """
    if not new or new == old:
        return False
    if "\n" in new:
        return False
    a, b = letters_only(old), letters_only(new)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(b) == len(a) + 1:
        # 恰好插入一个字母
        i = 0
        while i < len(a) and a[i] == b[i]:
            i += 1
        return a[i:] == b[i + 1:]
    return False


def live_providers(model):
    """验活：只留能真正调通的 key（有些 custom_provider 的 key 打这个端点会 404）"""
    out = []
    for k, b in load_cfg():
        try:
            call_llm(k, b, model, "1. ok", timeout=60, retries=1)
            out.append((k, b))
        except Exception as e:
            print(f"  key 不可用({b}): {e}")
    return out or load_cfg()[:1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--model", default="MiniMax-M2.7-highspeed")
    args = ap.parse_args()

    providers = live_providers(args.model)
    cands = json.load(open(CAND, encoding="utf-8"))
    print("候选行", len(cands), "可用 key 数", len(providers))

    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}

    if args.probe:
        sample = [c["text"] for c in cands[:12]]
        prompt = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sample))
        txt = call_llm(providers[0][0], providers[0][1], args.model, prompt)
        m = parse_numbered(txt)
        for i, s in enumerate(sample):
            print(f"{i+1}. {s}\n   -> {m.get(i+1, '<未解析>')}")
        return

    # 分批
    todo = [c for c in cands if c["text"] not in cache]
    print("待处理", len(todo))
    t0 = time.time()
    ki = 0
    for i in range(0, len(todo), args.batch):
        chunk = todo[i:i + args.batch]
        prompt = "\n".join(f"{j+1}. {c['text']}" for j, c in enumerate(chunk))
        k, b = providers[ki % len(providers)]
        ki += 1
        try:
            m = parse_numbered(call_llm(k, b, args.model, prompt))
            for j, c in enumerate(chunk):
                v = m.get(j + 1)
                if v:
                    cache[c["text"]] = v
        except Exception as e:
            print("  批次失败:", e, flush=True)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        done = min(i + args.batch, len(todo))
        print(f"  {done}/{len(todo)}  {time.time()-t0:.0f}s", flush=True)

    # 校验 + 汇总
    fixes = []
    for c in cands:
        new = cache.get(c["text"])
        if new and acceptable(c["text"], new):
            fixes.append((c, new))
    print(f"\n候选 {len(cands)} 条，LLM 判定可改 {len(fixes)} 条")
    for c, new in fixes[:40]:
        print(f"  {c['book']} #{c['art']}: {c['text'][:80]!r}\n      -> {new[:80]!r}")

    if not args.apply:
        print("（加 --apply 真写盘）")
        return

    # 写盘：按 book -> art -> line 精确定位
    by_art = {}
    for c, new in fixes:
        by_art.setdefault((c["book"], c["art"]), []).append((c["line"], new))
    changed = 0
    for (book, art), items in by_art.items():
        f = os.path.join(ARTICLE_DIR, book + ".json")
        arr = json.load(open(f, encoding="utf-8"))
        a = arr[art - 1]
        lines = (a.get("text") or "").split("\n")
        for ln, new in items:
            if 1 <= ln <= len(lines):
                lines[ln - 1] = new
        a["text"] = "\n".join(lines)
        json.dump(arr, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        open(f, "a", encoding="utf-8").write("\n")
        changed += 1
    print(f"已写盘 {changed} 篇文章")


if __name__ == "__main__":
    main()
