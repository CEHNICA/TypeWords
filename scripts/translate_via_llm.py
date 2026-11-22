"""
用 MiniMax Anthropic 协议批量翻译课文句子
=========================================

为什么不用 Google 免费接口：
  实测并发 12 会立刻触发 429，IP 被限流后所有域名（googleapis/google/com/.co.jp）
  全部返回 429，连 bing/sogou/youdao 在无头浏览器里也 CORS 全灭。
  MiniMax 走 api.minimax.cn，国内直连稳定，且译文质量比机翻好得多。

为什么按批（而不是逐句）：
  6641 句逐句请求太慢（每句一次 RTT）。按 40 句一批，
  模型一次性输出 40 行，用行号对齐回填，省 40 倍请求数。

用法：
  python scripts/translate_via_llm.py --probe
  python scripts/translate_via_llm.py --batch 40
  python scripts/translate_via_llm.py --apply
"""
import os, sys, json, re, time, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTICLE_DIR = os.path.join(ROOT, "public", "dicts", "en", "article")
CACHE = os.path.join(ROOT, "data", "article-translations-llm.json")
CONFIG = os.path.join(os.path.expanduser("~"), ".minimax", "config.yaml")

BOOKS = ["LWXX_3_1", "LWXX_3_2", "LWXX_4_1", "LWXX_4_2", "LWXX_5_1", "LWXX_5_2",
         "LWCZ_6_1", "LWCZ_6_2", "LWCZ_7_1", "LWCZ_7_2", "LWCZ_8_1", "LWCZ_8_2", "LWCZ_9_1"]

SYSTEM = (
    "你是中国中小学英语教材的专业英译中译者。"
    "把用户给出的每一行编号英文翻译成自然、准确、简洁的简体中文。"
    "要求：1) 严格保持行号前缀（如 3. ）不变，一条英文对一行中文；"
    "2) 教材口吻，不要口语化，不要加解释、不要加引号；"
    "3) 人名地名音译或意译均可，但同一称呼全文保持一致；"
    "4) 保留原文的数字、单位、专有名词含义；"
    "5) 只输出译文本身。"
)


def load_cfg():
    """返回 [(api_key, baseURL), ...]，优先 custom_provider 里的真实 key。

    provider.minimax 走的是本地代理 baseURL，直连会 401，用不了。
    多个 custom_provider 就都带上 —— 限流时轮换 key 还能接着跑。
    """
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
    """带指数退避的调用。429 / 5xx 自动重试。"""
    import urllib.request
    import urllib.error
    url = base_url.rstrip("/") + "/v1/messages"
    body = {
        "model": model,
        "max_tokens": 32000,
        "temperature": 0.2,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=data,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.loads(r.read().decode("utf-8"))
            return "\n".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        except Exception as e:
            last = e
            code = getattr(e, "code", None)
            if code and code not in (429, 500, 502, 503, 504):
                raise
            sleep = min(60, 5 * (2 ** attempt))
            print(f"    [退避] {e} -> 等 {sleep}s 后重试({attempt+1}/{retries})", flush=True)
            time.sleep(sleep)
    raise last


def parse_numbered(text):
    """把模型的 '1. xxx\\n2. yyy' 解析成 {序号: 译文}"""
    res = {}
    for line in text.split("\n"):
        line = line.strip()
        m = re.match(r"^(\d+)\s*[.、]\s*(.*)$", line)
        if m:
            res[int(m.group(1))] = m.group(2).strip()
    return res


def split_text(text):
    out = []
    for para in (text or "").split("\n\n"):
        para = para.strip()
        if not para:
            continue
        for s in para.split("\n"):
            if s.strip():
                out.append(s.strip())
    return out


def live_providers(model):
    """验活：只留能真正调通的 key（有些 custom_provider 的 key 打这个端点会 404）"""
    out = []
    for k, b in load_cfg():
        try:
            call_llm(k, b, model, "1. ok", timeout=60, retries=1)
            out.append((k, b))
        except Exception as e:
            print(f"  key 不可用({b}): {e}", flush=True)
    return out or load_cfg()[:1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--batch", type=int, default=40)
    ap.add_argument("--conc", type=int, default=3)
    ap.add_argument("--model", default="MiniMax-M2.7-highspeed")
    args = ap.parse_args()

    providers = live_providers(args.model)
    api_key, base_url = providers[0]
    print("baseURL", base_url, "model", args.model, "可用 key 数", len(providers))

    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    print("缓存条目", len(cache))

    # 收集所有需要翻译的句（按册、按文章、按句）
    tasks = []   # (book, art_idx, sent_idx_in_article, text)
    books_data = {}
    for b in BOOKS:
        f = os.path.join(ARTICLE_DIR, b + ".json")
        if not os.path.exists(f):
            continue
        arr = json.load(open(f, encoding="utf-8"))
        books_data[b] = arr
        for ai, a in enumerate(arr):
            t = (a.get("title") or "").strip()
            if t and t not in cache:
                tasks.append((b, ai, t))
            for s in split_text(a.get("text", "")):
                if s not in cache:
                    tasks.append((b, ai, s))
    # 去重
    seen = set()
    uniq = []
    for b, ai, s in tasks:
        if s in seen:
            continue
        seen.add(s)
        uniq.append((b, ai, s))
    print("待翻唯一句", len(uniq))

    if args.probe:
        sample = [s for _, _, s in uniq[:8]]
        prompt = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sample))
        t0 = time.time()
        txt = call_llm(api_key, base_url, args.model, prompt)
        print("耗时 %.1fs" % (time.time() - t0))
        print("---原始---")
        for i, s in enumerate(sample):
            print(f"{i+1}. {s}")
        print("---译文---")
        print(txt)
        return

    # 分批（失败批次重排队，最后再兜底跑一轮；多 key 轮换绕限流）
    t0 = time.time()
    failed = 0
    B = args.batch
    queue = list(uniq)   # 每项是 (book, art_idx, text)
    rounds = 0
    while queue and rounds < 4:
        rounds += 1
        retry = []
        ki = 0
        for i in range(0, len(queue), B):
            chunk = queue[i:i + B]
            prompt = "\n".join(f"{j+1}. {s}" for j, (_, _, s) in enumerate(chunk))
            k, b = providers[ki % len(providers)]
            ki += 1
            try:
                txt = call_llm(k, b, args.model, prompt)
                m = parse_numbered(txt)
                hit = 0
                for j, (_, _, s) in enumerate(chunk):
                    v = m.get(j + 1)
                    if v:
                        cache[s] = v
                        hit += 1
                    else:
                        retry.append((_, _, s))
                failed += len(chunk) - hit
            except Exception as e:
                print("  批次失败:", e, flush=True)
                retry.extend(chunk)
                failed += len(chunk)
            os.makedirs(os.path.dirname(CACHE), exist_ok=True)
            json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            done = min(i + B, len(queue))
            el = time.time() - t0
            rate = done / el if el else 0
            print(f"  [轮{rounds}] {done}/{len(queue)} 失败{failed} {el/60:.1f}分 "
                  f"速率{done/el:.1f}句/s", flush=True)
        queue = retry
        if queue:
            print(f"  [轮{rounds}] 剩 {len(queue)} 句重排队", flush=True)
            time.sleep(10)

    # 回填
    changed = 0
    for b, arr in books_data.items():
        f = os.path.join(ARTICLE_DIR, b + ".json")
        touched = False
        for a in arr:
            paras = []
            for para in (a.get("text", "") or "").split("\n\n"):
                if not para.strip():
                    continue
                sents = [s.strip() for s in para.split("\n") if s.strip()]
                paras.append([cache.get(s, "") for s in sents])
            new_t = "\n\n".join("\n".join(p) for p in paras)
            if new_t != (a.get("textTranslate") or ""):
                a["textTranslate"] = new_t
                touched = True
            t = (a.get("title") or "").strip()
            if t and cache.get(t) and a.get("titleTranslate") != cache[t]:
                a["titleTranslate"] = cache[t]
                touched = True
        if touched:
            changed += 1
            if args.apply:
                json.dump(arr, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                open(f, "a", encoding="utf-8").write("\n")
    print(f"\n{'已写盘' if args.apply else 'DRY-RUN'}：{changed} 册有更新，失败 {failed} 句")


if __name__ == "__main__":
    main()
