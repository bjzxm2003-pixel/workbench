"""路径与环境配置（server 包根）"""
from pathlib import Path
import os
import json

# 项目根 = server/ 的上一级
BASE = Path(__file__).resolve().parent.parent
DATA_DIR = BASE / "data"
BID_DIR = DATA_DIR / "bidding"
EXPORT_DIR = BID_DIR / "exports"
SAMPLES_DIR = DATA_DIR / "samples"
CONFIG_DIR = BASE / "config"
MASTER_FILE = BID_DIR / "master_bids.json"

DEFAULT_BID_KEYWORDS = ["EPC", "PC", "施工", "风电", "煤电", "光伏", "电缆"]

STATUS_VALUES = ["已投", "在投", "放弃", ""]


def ensure_dirs():
    for d in (DATA_DIR, BID_DIR, EXPORT_DIR, SAMPLES_DIR, CONFIG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_keywords() -> list:
    """投标关键词：优先 config/bidding_keywords.json，否则内置默认。"""
    ensure_dirs()
    f = CONFIG_DIR / "bidding_keywords.json"
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("keywords"):
                return [str(k).strip() for k in data["keywords"] if str(k).strip()]
        except Exception:
            pass
    return list(DEFAULT_BID_KEYWORDS)


def load_env_file(path: Path):
    """极简 .env 解析（不引入 dotenv 依赖），已存在的环境变量不覆盖。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_secret(name: str) -> str:
    """依次从 项目根/.env、server/.env、环境变量读取密钥。"""
    load_env_file(BASE / ".env")
    load_env_file(BASE / "server" / ".env")
    return os.environ.get(name, "")


ensure_dirs()
