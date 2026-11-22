"""词库最后一轮清洗：控制字符 / null 标记 / 重复释义合并 / 单点错位修复。
=============================================================

四类脏数据（都是上游 json 里带的，本轮逐类实测确认）：

  F1 控制字符   释义末尾混进 \\x08 等控制字符（如 '圆圈\\x08'），87 处
  F2 null 标记  释义里出现字面量 'null'（上游 null 值被字符串化），如
                'null （Stray）（挪、美、英、俄）斯特雷（人名）'、'…；null'
  F3 重复释义  同一词条 trans 里 cn 完全相同、其中一条 pos 丢了词性
                （如 [('','铝'), ('n.','铝')]），1297 条
  F4 单点错位  释义内容属于别的词（'bridging' → 'unit 衔接单元'）

用法：
  python _tools/fix_dict_clean.py            # dry-run
  python _tools/fix_dict_clean.py --apply    # 写盘（保持原 json 格式）
"""
import os, sys, json, re, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORD_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST = os.path.join(ROOT, "public", "list", "word.json")

sys.path.insert(0, os.path.join(ROOT, "scripts"))
from json_io import dump_like

CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
NULL_TOKEN_RE = re.compile(r"(^|[\s;；,，、])null($|[\s;；,，、])", re.I)

# F4：已人工确认的错位词条 -> 正确的 trans
KNOWN_FIX = {
    ("LWCZ-6-1.json", "bridging"): [
        {"pos": "n.", "cn": "架桥；搭桥"},
        {"pos": "v.", "cn": "架桥；搭桥；连接"},
    ],
}


def clean_cn(s):
    if not isinstance(s, str):
        return s
    s = CTRL_RE.sub("", s)
    prev = None
    while prev != s:
        prev = s
        s = NULL_TOKEN_RE.sub(lambda m: m.group(1), s)
    s = s.strip()
    # 清掉清理后残留的悬空分隔符
    s = re.sub(r"^[;；,，、\s]+", "", s)
    s = re.sub(r"[;；,，、\s]+$", "", s)
    return s


def clean_rows(rows):
    """清理一组 {pos,cn,...} 条目里的控制字符和 null 标记。"""
    changed = False
    for t in rows:
        for k in ("cn",):
            if isinstance(t.get(k), str):
                c = clean_cn(t[k])
                if c != t[k]:
                    t[k] = c
                    changed = True
        ws = t.get("ws")
        if isinstance(ws, list):
            for i, x in enumerate(ws):
                if isinstance(x, str):
                    c = clean_cn(x)
                    if c != x:
                        ws[i] = c
                        changed = True
    return changed


def merge_dup_trans(trans):
    """cn 完全相同的一组里，丢掉 pos 为空的那条（保留有词性的）。

    pos 全都非空且彼此不同时（如 n. 预测 / v. 预测）→ 正常，不动。
    pos 全为空 → 只留第一条。
    """
    groups = {}
    order = []
    for t in trans:
        cn = (t.get("cn") or "").strip()
        if not cn:
            continue
        if cn not in groups:
            groups[cn] = []
            order.append(cn)
        groups[cn].append(t)

    out = []
    removed = 0
    for cn in order:
        items = groups[cn]
        withpos = [t for t in items if (t.get("pos") or "").strip()]
        if len(items) > 1 and withpos:
            keep = []
            seen_pos = set()
            for t in withpos:
                p = (t.get("pos") or "").strip()
                if p in seen_pos:
                    removed += 1
                    continue
                seen_pos.add(p)
                keep.append(t)
            removed += len(items) - len(keep)
            out.extend(keep)
        elif len(items) > 1:
            out.append(items[0])
            removed += len(items) - 1
        else:
            out.append(items[0])
    # 保留原来没有 cn 的条目（罕见），免得丢数据
    for t in trans:
        if not (t.get("cn") or "").strip():
            out.append(t)
    return out, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    books = json.load(open(LIST, encoding="utf-8"))
    stat = {"ctrl": 0, "null": 0, "dup": 0, "known": 0}
    changed_files = 0

    for b in books:
        url = b.get("url") or ""
        f = os.path.join(WORD_DIR, url)
        if not os.path.exists(f):
            continue
        raw = open(f, "rb").read()
        arr = json.loads(raw.decode("utf-8-sig"))
        touched = False

        for it in arr:
            w = (it.get("word") or "").strip()

            # F1 + F2：控制字符 / null 标记
            for field in ("trans", "synos"):
                rows = it.get(field) or []
                for t in rows:
                    old = t.get("cn")
                    if isinstance(old, str) and (CTRL_RE.search(old) or NULL_TOKEN_RE.search(old)):
                        if CTRL_RE.search(old):
                            stat["ctrl"] += 1
                        if NULL_TOKEN_RE.search(old):
                            stat["null"] += 1
                if clean_rows(rows):
                    touched = True

            # F3：重复释义合并
            trans = it.get("trans") or []
            if trans:
                new_trans, removed = merge_dup_trans(trans)
                if removed:
                    stat["dup"] += removed
                    it["trans"] = new_trans
                    touched = True

            # F4：已确认的错位修复
            key = (os.path.basename(url), w)
            if key in KNOWN_FIX:
                before = json.dumps(it.get("trans"), ensure_ascii=False)
                it["trans"] = KNOWN_FIX[key]
                it["synos"] = []
                if json.dumps(it.get("trans"), ensure_ascii=False) != before:
                    stat["known"] += 1
                    touched = True

        if touched:
            changed_files += 1
            if args.apply:
                with open(f, "wb") as fh:
                    fh.write(dump_like(raw, arr))

    print(f"{'已写盘' if args.apply else 'DRY-RUN'}：改动 {changed_files} 册")
    print(f"  F1 控制字符清理 {stat['ctrl']} 处 / F2 null 标记 {stat['null']} 处")
    print(f"  F3 重复释义合并 {stat['dup']} 条 / F4 已知错位修复 {stat['known']} 条")


if __name__ == "__main__":
    main()
