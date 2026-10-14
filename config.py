"""ApexTorrent configuration: paths + persisted settings."""
import json
from pathlib import Path

APP_DIR = Path.home() / ".apextorrent"
CONFIG_FILE = APP_DIR / "config.json"
RESUME_DIR = APP_DIR / "resume"

DEFAULTS = {
    "download_dir": str(Path.home() / "Downloads" / "ApexTorrent"),
    "seed_after_finish": False,
    "listen_port": 6881,
    "preset": "balanced",        # balanced | max | quiet
    "adaptive": True,            # adaptive connection tuning
    "interface": "",             # "" = any interface; otherwise adapter name (kill switch active)
    "require_encryption": False, # True = refuse peers that don't speak MSE/PE
    "vt_api_key": "",            # VirusTotal v3 key (free tier: 4 req/min, 500/day)
    "vt_max_lookups": 10,        # max hash lookups per torrent (protects the free quota)
    "vt_delay": 16.0,            # seconds between lookups (free tier = 4/min)
}


def load():
    APP_DIR.mkdir(parents=True, exist_ok=True)
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text()))
        except Exception:
            pass
    return cfg


def save(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
