"""
修复「单词首字母被拆开」的粘连（PDF 空格丢失）
=================================================
现象： "T e name Lu Xun"  →  应为 "The name Lu Xun"
      "T ey might be asked" → "They might be asked"
      "H i, Lisa."         → "Hi, Lisa."

判据：大写单字母 + 空格 + 小写词，合并后必须是一个**真实英文词**
      （用离线词典 + 常见词表验证），且原文里该组合不是独立用法。

用法： python _tools/fix_split_words.py [--dry-run]
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "public", "dicts", "en", "article")
BOOKS = ["LWXX_3_1", "LWXX_3_2", "LWXX_4_1", "LWXX_4_2", "LWXX_5_1", "LWXX_5_2",
         "LWCZ_6_1", "LWCZ_6_2", "LWCZ_7_1", "LWCZ_7_2", "LWCZ_8_1", "LWCZ_8_2", "LWCZ_9_1"]

# 合并后可能出现的合法英文词（首字母大写时）
MERGE_OK = {
    "the", "they", "them", "their", "there", "these", "this", "that", "then", "those", "though",
    "things", "think", "time", "thanks", "thank", "third", "twenty", "ten", "two", "tall", "taste",
    "tiger", "table", "teacher", "team", "test", "text", "travel", "tree", "try", "turn", "take",
    "tell", "term", "test", "town", "type", "top", "true", "twice", "toward", "towards",
    "hi", "he", "her", "here", "his", "him", "how", "has", "had", "have", "hello", "help",
    "head", "hand", "half", "happy", "hard", "hello", "high", "home", "horse", "hot", "hope",
    "ice", "idea", "if", "in", "is", "it", "its",
    "our", "of", "on", "or", "one", "once", "over", "off", "open", "out", "often", "oh",
    "a", "an", "and", "as", "at", "are", "all", "also", "after", "again", "around", "ask",
    "am", "about", "above", "across", "ago",
    "you", "your", "yes", "yet", "yesterday", "why", "we", "was", "were", "will", "would",
    "us", "up", "use", "under", "until", "un", "understand",
    "no", "not", "now", "nice", "new", "night", "name", "next", "never", "need", "nine",
    "very", "video", "visit", "voice", "vote", "village",
    "go", "good", "great", "get", "give", "girl", "green", "group", "grow", "grand",
    "do", "does", "done", "doctor", "down", "dinner", "day", "dear",
    "so", "some", "story", "school", "she", "small", "sit", "see", "say", "come", "can",
    "for", "from", "find", "first", "five", "food", "friend", "four", "family",
    "want", "we", "what", "when", "where", "who", "why", "which", "with", "will", "work",
    "make", "man", "many", "may", "more", "mother", "my", "music", "must", "many",
    "look", "learn", "leave", "left", "let", "like", "live", "long", "little", "listen",
    "me", "mother", "morning", "moon", "more", "money",
    "man", "men", "meaning", "miss", "must", "moment", "move", "mother",
    "name", "near", "need", "never", "next", "nice", "night", "now", "number",
    "old", "open", "other", "our", "out", "over", "own",
    "play", "please", "put", "people", "picture", "place", "point", "problem", "part",
    "question", "quiet", "quite",
    "read", "ready", "real", "right", "room", "run", "red", "round", "ride",
    "say", "school", "see", "seat", "send", "set", "she", "short", "should", "sing", "sit",
    "six", "small", "some", "song", "soon", "sorry", "stand", "start", "stay", "still",
    "story", "study", "such", "sun", "swim", "student", "sit", "sell",
    "talk", "take", "tell", "ten", "than", "thank", "that", "the", "their", "them", "then",
    "there", "these", "they", "think", "this", "those", "three", "time", "to", "today",
    "together", "too", "two", "try",
    "under", "up", "use", "usually",
    "very", "voice",
    "walk", "want", "warm", "was", "watch", "water", "way", "we", "week", "well", "were",
    "what", "when", "where", "which", "while", "white", "who", "why", "will", "with",
    "woman", "women", "word", "work", "world", "would", "write",
    "year", "yes", "yesterday", "yet", "you", "young", "your",
}


def load_words():
    words = set()
    idx = os.path.join(ROOT, "data", "word-index.json")
    if os.path.exists(idx):
        d = json.load(open(idx, encoding="utf-8"))
        words |= set(w.lower() for w in (d.keys() if isinstance(d, dict) else d))
    words |= MERGE_OK
    return words


PAT = re.compile(r"\b([A-Z])\s+([a-z]{1,5})\b")
EXCLUDE_FIRST = {"I", "A"}   # I / A 是独立代词/冠词


def main():
    dry = "--dry-run" in sys.argv
    words = load_words()
    total = 0
    details = []
    for b in BOOKS:
        f = os.path.join(DIR, b + ".json")
        if not os.path.exists(f):
            continue
        arr = json.load(open(f, encoding="utf-8"))
        touched = False
        for a in arr:
            paras = []
            for para in (a.get("text") or "").split("\n\n"):
                lines = []
                for s in para.split("\n"):
                    if not s.strip():
                        lines.append(s)
                        continue
                    def rep(m, _b=b, _a=a):
                        nonlocal total
                        c = m.group(1)
                        w = m.group(2)
                        if c in EXCLUDE_FIRST:
                            return m.group(0)
                        merged = (c + w).lower()
                        if merged not in words:
                            return m.group(0)
                        total += 1
                        details.append((_b, _a.get("title", "")[:30], m.group(0), c + w))
                        return c + w
                    ns = PAT.sub(rep, s)
                    if ns != s:
                        touched = True
                    lines.append(ns)
                paras.append("\n".join(lines))
            a["text"] = "\n\n".join(paras)
        if touched:
            if not dry:
                json.dump(arr, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
                open(f, "a", encoding="utf-8").write("\n")
    print(f"修复 {total} 处")
    for b, t, old, new in details:
        print(f"  [{b}] {t}: {old!r} -> {new!r}")
    print("DRY-RUN，未写盘" if dry else "已写盘")


if __name__ == "__main__":
    main()
