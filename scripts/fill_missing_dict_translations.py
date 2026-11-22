"""
给六~九年级词库里「无释义」的词条补中文释义（MiniMax API 版）
==============================================================

为什么改成 Python + MiniMax：
  原来的 scripts/fill-missing-dict-translations.js 走 Google 免费接口，
  实测已被按 IP 限流（429），googleapis/google/google.co.jp 全灭。
  MiniMax 走国内直连，稳定且释义质量比机翻好。

分两步：
  1. 复用：从全库其它词书的同名词条搬释义（零成本、无误、461 条）
  2. 翻译：剩下的走 MiniMax（带批号回填），约 1160 条

用法：
  py -3 scripts/fill_missing_dict_translations.py --probe
  py -3 scripts/fill_missing_dict_translations.py            # dry-run
  py -3 scripts/fill_missing_dict_translations.py --apply    # 真写盘
"""
import os, sys, json, re, time, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST = os.path.join(ROOT, "public", "list", "word.json")
CACHE = os.path.join(ROOT, "data", "dict-translations-llm.json")
CONFIG = os.path.join(os.path.expanduser("~"), ".minimax", "config.yaml")

SYSTEM = (
    "你是中国中小学英语教材的词汇释义编写员。"
    "用户会给出一批英文词条（可能有短语或带点的专名缩写），"
    "请为每一个给出简洁准确的中文释义。"
    "要求：1) 严格保持行号前缀（如 3. ）不变，一个词条一行释义；"
    "2) 释义用「词性缩写+空格+中文」形式，如 'n. 苹果'、'v. 奔跑'、'adj. 困难的'、'adv. 快速地'；"
    "3) 短语按整体意思释义，不要逐词硬译；"
    "4) 人名地名给出常用中文译名；"
    "5) 释义末尾不要加句号；"
    "6) 只输出释义本身。"
)


def load_cfg():
    import yaml
    c = yaml.safe_load(open(CONFIG, encoding="utf-8"))
    for pid, p in (c.get("custom_provider") or {}).items():
        o = p.get("options") or {}
        if o.get("apiKey") and o.get("baseURL"):
            return o["apiKey"], o["baseURL"]
    p = c["provider"]["minimax"]
    return p["options"]["apiKey"], p["options"]["baseURL"]


def call_llm(api_key, base_url, model, prompt, timeout=300):
    import urllib.request
    url = base_url.rstrip("/") + "/v1/messages"
    body = {
        "model": model,
        "max_tokens": 32000,
        "temperature": 0.1,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    return "\n".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def parse_numbered(text):
    res = {}
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"^(\d+)\s*[.、]\s*(.*)$", line)
        if m:
            v = m.group(2).strip()
            if v:
                res[int(m.group(1))] = v
    return res


def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().strip())


def cn_of(w):
    """取词条中文释义。

    注意：词条的主释义字段是 trans[]（带 pos），synos[] 只是同义词补充。
    只看 synos 会把 9905 条正常词误判成「无释义」。
    """
    parts = []
    for s in (w.get("trans") or []):
        cn = (s.get("cn") or "").strip()
        if not cn:
            continue
        pos = (s.get("pos") or "").strip()
        parts.append(f"{pos} {cn}" if pos else cn)
    if not parts:
        for s in (w.get("synos") or []):
            cn = (s.get("cn") or "").strip()
            if cn:
                parts.append(cn)
    return "；".join(parts)


POS_RE = re.compile(r"^((?:adj|adv|v|n|vt|vi|prep|conj|pron|num|art|aux|modal|int|interj|phr|abbr)\.?)\s+(.*)$", re.I)


def split_pos(cn):
    """把 'n. 苹果' 拆成 ('n.', '苹果')；拆不出就原样当 cn"""
    m = POS_RE.match(cn.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", cn.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=50)
    ap.add_argument("--model", default="MiniMax-M2.7-highspeed")
    ap.add_argument("--all", action="store_true",
                    help="处理全部词书（默认只处理 tags 含「六」「九」的课本册）")
    args = ap.parse_args()

    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from json_io import dump_like

    api_key, base_url = load_cfg()
    print("baseURL", base_url, "model", args.model)

    lst = json.load(open(LIST, encoding="utf-8"))
    if args.all:
        targets = lst
    else:
        targets = [d for d in lst if any("六" in t and "九" in t for t in (d.get("tags") or []))]
    print("目标册数", len(targets))

    # 1) 复用索引：优先用离线大词典（65655 词，释义更全更准），再退回其它词书
    reuse = {}
    index_path = os.path.join(ROOT, "data", "word-index.json")
    if os.path.exists(index_path):
        idx = json.load(open(index_path, encoding="utf-8"))
        for k, v in idx.items():
            if not isinstance(v, dict):
                continue
            cn = ""
            for s in (v.get("trans") or []):
                c = (s.get("cn") or "").strip()
                if c:
                    p = (s.get("pos") or "").strip()
                    cn = f"{p} {c}" if p else c
                    break
            if cn:
                reuse[norm(k)] = cn
    print("离线词典复用索引词数", len(reuse))
    for d in lst:
        f = os.path.join(WORD_DIR, d.get("url", ""))
        if not os.path.exists(f):
            continue
        try:
            arr = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        for w in arr:
            cn = cn_of(w)
            k = norm(w.get("word"))
            if cn and k and k not in reuse:
                reuse[k] = cn
    print("复用索引词数", len(reuse))

    # 2) 找缺释义的
    need_fill = []   # 所有缺释义的词条（都要回填）
    need_translate = []  # 其中复用也救不回来的，才要送翻译
    for d in targets:
        f = os.path.join(WORD_DIR, d.get("url", ""))
        if not os.path.exists(f):
            continue
        arr = json.load(open(f, encoding="utf-8"))
        for i, w in enumerate(arr):
            if cn_of(w):
                continue
            k = norm(w.get("word"))
            if not k:
                continue
            rec = {"dict": d.get("name"), "file": f, "idx": i, "word": w.get("word") or "", "key": k}
            need_fill.append(rec)
            if k not in reuse:
                need_translate.append(rec)
    print("缺释义词条合计", len(need_fill), "（其中需翻译", len(need_translate), "）")
    missing = need_translate
    uniq_words, seen = [], set()
    for m in missing:
        if m["key"] in seen:
            continue
        seen.add(m["key"])
        uniq_words.append(m["word"])
    print("待翻译唯一词", len(uniq_words))

    if args.probe:
        sample = uniq_words[:10]
        prompt = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sample))
        t0 = time.time()
        txt = call_llm(api_key, base_url, args.model, prompt)
        print("耗时 %.1fs" % (time.time() - t0))
        for i, s in enumerate(sample):
            print(f"{i+1}. {s}  ->  {parse_numbered(txt).get(i+1, '<未解析>')}")
        return

    # 3) 翻译
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    todo = [w for w in uniq_words if norm(w) not in cache]
    print("缓存命中后待翻", len(todo))
    t0 = time.time()
    failed = 0
    B = args.batch
    for i in range(0, len(todo), B):
        chunk = todo[i:i + B]
        prompt = "\n".join(f"{j+1}. {s}" for j, s in enumerate(chunk))
        try:
            m = parse_numbered(call_llm(api_key, base_url, args.model, prompt))
            for j, s in enumerate(chunk):
                v = m.get(j + 1)
                if v:
                    cache[norm(s)] = v
                else:
                    failed += 1
        except Exception as e:
            print("  批次失败:", e)
            failed += len(chunk)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        done = min(i + B, len(todo))
        el = time.time() - t0
        rate = done / el if el else 0
        print(f"  {done}/{len(todo)} 失败{failed} {el/60:.1f}分 速率{done/el:.1f}词/s "
              f"ETA {(len(todo)-done)/rate/60 if rate else 0:.1f}分", flush=True)

    # 4) 回填（need_fill 全部，包括复用救回来的）
    changed = {}
    for m in need_fill:
        cn = reuse.get(m["key"]) or cache.get(m["key"])
        if not cn:
            continue
        changed.setdefault(m["file"], []).append({"idx": m["idx"], "cn": cn})
    for f, items in changed.items():
        raw = open(f, "rb").read()
        arr = json.loads(raw.decode("utf-8-sig"))
        for it in items:
            if cn_of(arr[it["idx"]]):
                continue
            pos, cn = split_pos(it["cn"])
            # 主释义写进 trans[]（前端渲染的就是它），synos[] 保持空
            arr[it["idx"]]["trans"] = [{"pos": pos, "cn": cn}]
        if args.apply:
            # 保持原文件格式（compact / indent / BOM / CRLF）
            with open(f, "wb") as fh:
                fh.write(dump_like(raw, arr))
    print(f"{'已写盘' if args.apply else 'DRY-RUN'}：会改 {len(changed)} 个词书，失败 {failed} 词")


if __name__ == "__main__":
    main()
