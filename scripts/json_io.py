"""保持原文件格式写回 JSON。

词库 json 有两种形态：
  - 197 册 compact 单行（无 BOM / 无末尾换行）
  - 10 册 indent=2 + CRLF + 末尾换行
写回时必须照原样还原，否则 diff 会炸、文件会撑大。
"""
import json


def dump_like(original_bytes, arr):
    """按原文件格式序列化 arr，返回 bytes。"""
    bom = original_bytes[:3] == b"\xef\xbb\xbf"
    crlf = b"\r\n" in original_bytes[:4000]
    body = original_bytes[3:] if bom else original_bytes
    compact = not body[:1] == b"\n"
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


def load_preserve(path):
    """读文件，同时返回原始字节（供 dump_like 用）。"""
    raw = open(path, "rb").read()
    return json.loads(raw.decode("utf-8-sig")), raw
