"""本机路径配置解析（路径不进版本库）

背景：课本 PDF、词库备份这些资源体积大 / 涉及本机私有目录，
不能进 git；但脚本又需要知道它们在哪。于是分三层找：

    1. 环境变量（一次性设置，CI / 临时覆盖最方便）
       TW_TEXTBOOK_PDF_DIR   课本 PDF 所在目录
       TW_DICT_BACKUP        词库备份目录
    2. 本机配置文件 data/local_paths.json（.gitignore 已排除）
       {"textbookPdfDir": "D:\\教材\\课本", "dictBackup": "D:\\备份"}
    3. 仓库内相对路径兜底（公开仓库里 clone 下来时的默认位置）

用法：
    from local_paths import resolve_pdf_dir, resolve_dict_backup
    PDF_DIR = resolve_pdf_dir()
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(ROOT, "data", "local_paths.json")


def _config():
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001  文件不存在/坏了都不该让脚本崩
        return {}


def _resolve(env_key, cfg_key, fallback_rel):
    v = os.environ.get(env_key)
    if v and os.path.isdir(v):
        return v
    v = _config().get(cfg_key)
    if v and os.path.isdir(v):
        return v
    return os.path.join(ROOT, fallback_rel)


def resolve_pdf_dir():
    """课本 PDF 目录：env → data/local_paths.json → <repo>/课本PDF"""
    return _resolve("TW_TEXTBOOK_PDF_DIR", "textbookPdfDir", "课本PDF")


def resolve_dict_backup(default_name="_dict_backup"):
    """词库备份目录：env → data/local_paths.json → <repo>/../<default_name>"""
    v = os.environ.get("TW_DICT_BACKUP")
    if v:
        return v
    v = _config().get("dictBackup")
    if v:
        return v
    return os.path.join(os.path.dirname(ROOT), default_name)
