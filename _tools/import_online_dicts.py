#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从线上拉词库并落地到本地（不新增 schema、清单只做按条目合并）

线上资源在 files.typewords.cc（不在 typewords.cc 同域，那儿只是 SPA fallback）：
    清单    https://files.typewords.cc/list/word.json      （默认展示列表，194 条，不全）
    完整    https://typewords.cc/list/word.json            （241 条，schema 不同：id 是英文短名）
    词库文件 https://files.typewords.cc/dicts/en/word/<url>

为什么清单只做「按条目合并、绝不整份覆盖」：
  - 本地 public/list/word.json 有 217 条（含莱芜 13 册 + 2026-11-22 补入的 10 册线上词书，线上没有莱芜），
    整份覆盖会把这 13 册连同所有本地字段（categoryId / tags / createdAt…）一起冲掉；
  - 两边的 id 空间不同（本地 1..265，线上主站是英文短名），覆盖后 id 会全乱。

清洗口径与本仓库既有尺子一致（_tools/check_dict_data.py）：
  D2 同 (词性,中文) 完全相同的条目 → 去重
  D3 同一中文出现多次且其中一条没有词性 → 删掉那条没词性的
  D1/D5 释义为空 → 用本地离线索引 data/word-index.json 补；
                   补不上的条目**删除**（本地既有 207 册的 D1 就是 0，宁缺毋滥，不编造释义）

注意：data/cedict.txt.gz **不是**中英词典（它是「中文词条 → 英文释义」的混合词典），
本脚本没用它 —— 释义一律以本地离线索引（教辅口径 + CC-CEDICT 扩充）为准。

用法：
    python _tools/import_online_dicts.py            # 下载 + 清洗 + 落地 + 合并清单
    python _tools/import_online_dicts.py --dry-run  # 只报告，不写盘
"""
import argparse
import collections
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fix_dict_relwords import is_mismatch  # noqa: E402  线上原始数据的 relWords 会整组错位
DICT_DIR = os.path.join(ROOT, "public", "dicts", "en", "word")
LIST_FILE = os.path.join(ROOT, "public", "list", "word.json")
INDEX_FILE = os.path.join(ROOT, "data", "word-index.json")
CEDICT_FILE = os.path.join(ROOT, "data", "cedict.txt.gz")

RESOURCE = "https://files.typewords.cc"
MAIN_LIST = "https://typewords.cc/list/word.json"

# 本次要拉的册：(url 文件名, enName, 显示名, category, tags, categoryId)
SPEC = [
    ("IELTS_WANG_3.json", "ieltsWang3", "雅思wang C3", "国际考试", ["IELTS"], 2),
    ("IELTS_WANG_4.json", "ieltsWang4", "雅思wang C4", "国际考试", ["IELTS"], 2),
    ("IELTS_WANG_5.json", "ieltsWang5", "雅思wang C5", "国际考试", ["IELTS"], 2),
    ("IELTS_WANG_11.json", "ieltsWang11", "雅思wang C11", "国际考试", ["IELTS"], 2),
    ("ielts-real-1.json", "ielts-real-1", "雅思 real 词汇 1", "国际考试", ["IELTS"], 2),
    ("ielts-real-2.json", "ielts-real-2", "雅思 real 词汇 2", "国际考试", ["IELTS"], 2),
    ("ielts-real-3.json", "ielts-real-3", "雅思 real 词汇 3", "国际考试", ["IELTS"], 2),
    ("ielts-real-4.json", "ielts-real-4", "雅思 real 词汇 4", "国际考试", ["IELTS"], 2),
    ("ielts-real-5.json", "ielts-real-5", "雅思 real 词汇 5", "国际考试", ["IELTS"], 2),
    (
        "frequently_used_word03.json",
        "frequently_used_words03_level3",
        "超高频单词level 3",
        "中国考试",
        ["其他"],
        1,
    ),
]

CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]|\bnull\b")


def log(*a):
    print(*a)


def fetch(url, timeout=90, retries=3):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError("下载失败 %s: %s" % (url, last))


def load_index():
    with io.open(INDEX_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_cedict():
    """CC-CEDICT：词 -> [(pos, cn)]"""
    out = {}
    with gzip.open(CEDICT_FILE, "rt", encoding="utf-8") as f:
        for line in f:
            if not line.startswith("#"):
                break
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            trad = parts[0].strip()
            simp = parts[1].strip()
            key = trad.lower()
            if key not in out:
                out[key] = []
            out[key].append((parts[4].strip() if len(parts) > 4 else "", simp))
    return out


def dedup_trans(trans, stats):
    """D2：同 (词性,中文) 完全相同 → 只留第一条"""
    seen = set()
    out = []
    for t in trans:
        cn = (t.get("cn") or "").strip()
        pos = (t.get("pos") or "").strip()
        if cn and (pos, cn) in seen:
            stats["D2"] += 1
            continue
        seen.add((pos, cn))
        out.append(t)
    return out


def drop_posless_dup(trans, stats):
    """D3：同一中文出现多次且其中一条没有词性 → 删掉没词性的那条"""
    bycn = collections.defaultdict(list)
    for t in trans:
        cn = (t.get("cn") or "").strip()
        if cn:
            bycn[cn].append(t)
    drop = set()
    for cn, items in bycn.items():
        if len(items) > 1 and any(not (t.get("pos") or "").strip() for t in items):
            for t in items:
                if not (t.get("pos") or "").strip():
                    drop.add(id(t))
    if drop:
        stats["D3"] += len(drop)
        return [t for t in trans if id(t) not in drop]
    return trans


def strip_ctrl(trans, stats):
    out = []
    for t in trans:
        cn = t.get("cn") or ""
        if CTRL_RE.search(cn):
            stats["D4"] += 1
            cn = CTRL_RE.sub("", cn).strip()
            if not cn:
                continue
            t = dict(t)
            t["cn"] = cn
        out.append(t)
    return out


def has_cn(trans):
    return any((t.get("cn") or "").strip() for t in (trans or []))


def fill_missing(w, index, stats):
    """D1/D5：释义为空 → 离线索引补；补不上 → 删掉该词条（不编造释义）"""
    word = w.get("word") or ""
    hit = index.get(word.lower())
    if hit and has_cn(hit.get("trans")):
        w["trans"] = dedup_trans(hit.get("trans") or [], stats)
        stats["fill_index"] += 1
        return w, True
    stats["drop_no_trans"] += 1
    return w, False


def clean(data, index):
    stats = collections.Counter()
    dropped = []
    out = []
    for w in data:
        w = dict(w)
        trans = strip_ctrl(dedup_trans(w.get("trans") or [], stats), stats)
        trans = drop_posless_dup(trans, stats)
        w["trans"] = trans
        if not has_cn(trans):
            w, keep = fill_missing(w, index, stats)
            if not keep:
                dropped.append(w.get("word") or "")
                continue
        # 词头控制字符
        head = w.get("word") or ""
        if CTRL_RE.search(head):
            stats["D4"] += 1
            w["word"] = CTRL_RE.sub("", head).strip()
        # D6：relWords 整组挂错词头（线上原始数据自带，判据同 fix_dict_relwords.py）
        rw = w.get("relWords") or {}
        if (rw.get("root") or "").strip() and is_mismatch(w):
            stats["D6_relwords"] += 1
            w["relWords"] = {"root": "", "rels": []}
        out.append(w)
    return out, stats, dropped


def dump_compact(arr):
    """本地主流格式：compact 单行 / LF / 无 BOM / 无末尾换行"""
    text = json.dumps(arr, ensure_ascii=False, separators=(",", ":"))
    return text.encode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    log("加载本地离线索引 ...")
    index = load_index()
    log("  索引 %d 词" % len(index))

    with io.open(LIST_FILE, encoding="utf-8") as f:
        lst = json.load(f)
    used_ids = {int(x["id"]) for x in lst}
    used_en = {x.get("enName") for x in lst}
    next_id = max(used_ids) + 1

    new_entries = []
    total_stats = collections.Counter()
    all_dropped = []

    for url, en_name, disp, category, tags, category_id in SPEC:
        if en_name in used_en:
            log("[SKIP] enName 已被占用：%s" % en_name)
            continue
        local_path = os.path.join(DICT_DIR, url)
        raw = None
        if os.path.exists(local_path):
            with open(local_path, "rb") as f:
                raw = f.read()
            log("[本地] %s 已存在，跳过下载" % url)
        else:
            log("[下载] %s ..." % url)
            raw = fetch("%s/dicts/en/word/%s" % (RESOURCE, url))
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except Exception as e:  # noqa: BLE001
            log("  !! 解析失败：%s" % e)
            continue

        cleaned, stats, dropped = clean(data, index)
        total_stats.update(stats)
        all_dropped.extend(dropped)
        log(
            "  词条 %d → %d（D2 %d / D3 %d / D4 %d / D6错位rel %d / 索引补 %d / 无释义删除 %d）"
            % (
                len(data),
                len(cleaned),
                stats["D2"],
                stats["D3"],
                stats["D4"],
                stats["D6_relwords"],
                stats["fill_index"],
                len(dropped),
            )
        )
        if not args.dry_run:
            with open(local_path, "wb") as f:
                f.write(dump_compact(cleaned))
            log("  已写入 %s" % local_path)

        new_entries.append(
            {
                "id": next_id,
                "enName": en_name,
                "name": disp,
                "description": disp,
                "categoryId": category_id,
                "url": url,
                "length": len(cleaned),
                "language": "en",
                "translateLanguage": "zh_CN",
                "version": 1,
                "type": "word",
                "isDefault": False,
                "recommended": False,
                "userId": "00000000-0000-0000-0000-000000000001",
                "createdAt": "2026-05-10 03:11:48.274096",
                "updatedAt": "2026-06-03 15:27:15.113708",
                "cover": None,
                "hidden": False,
                "category": category,
                "tags": list(tags),
            }
        )
        next_id += 1

    log("")
    log("合计清洗：%s" % {k: v for k, v in total_stats.items() if k != "dropped_words"})
    if all_dropped:
        log("因无中文释义被删除的词头：%s" % "、".join(all_dropped))

    if args.dry_run:
        log("dry-run：未写清单")
        return

    if not new_entries:
        log("没有新条目，清单不动")
        return

    # 备份清单到 repo 外
    bak = os.path.join(os.environ.get("TEMP", "/tmp"), "tw_bak_list_word_%s.json" % int(time.time()))
    with open(LIST_FILE, "rb") as f:
        bak_raw = f.read()
    with open(bak, "wb") as f:
        f.write(bak_raw)
    log("清单已备份：%s" % bak)

    # 按条目合并（绝不整份覆盖）
    merged = list(lst) + new_entries
    with io.open(LIST_FILE, "w", encoding="utf-8", newline="") as f:
        # 清单格式铁律：2 空格缩进 + 末尾换行（check_dict_list.py 逐字节校验，别改）
        f.write(json.dumps(merged, ensure_ascii=False, indent=2) + "\n")
    log("清单已合并：%d → %d 条" % (len(lst), len(merged)))
    for e in new_entries:
        log("  + id=%d %-34s %s (%d 词)" % (e["id"], e["enName"], e["name"], e["length"]))


if __name__ == "__main__":
    main()
