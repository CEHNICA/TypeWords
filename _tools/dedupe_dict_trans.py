"""清理词库里「完全重复」的释义条目。

判据：trans / synos 里 (pos, cn) 完全相同的条目只保留第一条。
（pos 不同但中文相同是正常的——不同词性同义，不能去。）
默认 dry-run，--apply 写盘。
"""
import os
import sys
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST = os.path.join(ROOT, "public", "list", "word.json")


def dedupe_trans(items):
    """trans 没有 ws 字段，(pos, cn) 相同即完全重复。"""
    return _dedupe(items, lambda it: ((it.get("pos") or "").strip(), (it.get("cn") or "").strip()))


def dedupe_synos(items):
    """synos 带 ws（近义词组）：必须 (pos, cn, ws) 全同才算重复。

    同中文但 ws 不同 = 不同的近义词组，去掉会丢信息，不能动。
    """
    return _dedupe(items, lambda it: (
        (it.get("pos") or "").strip(),
        (it.get("cn") or "").strip(),
        tuple(sorted(it.get("ws") or [])),
    ))


def _dedupe(items, keyfn):
    if not isinstance(items, list):
        return items, 0
    seen = set()
    out = []
    dropped = 0
    for it in items:
        if not isinstance(it, dict):
            out.append(it)
            continue
        k = keyfn(it)
        if k in seen:
            dropped += 1
            continue
        seen.add(k)
        out.append(it)
    return out, dropped


def dump_like(original_bytes, arr):
    """按原文件的格式写回：compact 单行 或 indent=2；保留 BOM / CRLF / 末尾换行。"""
    bom = original_bytes[:3] == b"\xef\xbb\xbf"
    crlf = b"\r\n" in original_bytes[:4000]
    compact = not original_bytes.lstrip(b"\xef\xbb\xbf")[:1] == b"\n"
    if compact:
        text = json.dumps(arr, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(arr, ensure_ascii=False, indent=2)
        if original_bytes.endswith(b"\n") and not text.endswith("\n"):
            text += "\n"
    if crlf:
        text = text.replace("\r\n", "\n").replace("\n", "\r\n")
    data = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + data) if bom else data


def main():
    apply = "--apply" in sys.argv
    books = json.load(open(LIST, encoding="utf-8"))
    total = 0
    touched = 0
    for b in books:
        path = os.path.join(WORD_DIR, b.get("url", ""))
        if not os.path.exists(path):
            continue
        raw = open(path, "rb").read()
        arr = json.loads(raw.decode("utf-8-sig"))
        dirty = False
        for it in arr:
            t, dt = dedupe_trans(it.get("trans"))
            s, ds = dedupe_synos(it.get("synos"))
            if dt or ds:
                total += dt + ds
                dirty = True
                if apply:
                    if dt:
                        it["trans"] = t
                    if ds:
                        it["synos"] = s
        if apply and dirty:
            with open(path, "wb") as f:
                f.write(dump_like(raw, arr))
            touched += 1
    print(f"去掉完全重复的释义条目 {total} 条，涉及词书 {touched} 册（apply={apply}）")
    sys.exit(0)


if __name__ == "__main__":
    main()
