"""
logging_utils.py
One shared logger configuration for the whole package: console output
plus a rotating file under workspace/.lcycode/logs/lcycode.log, so a
long unattended run leaves a trail you can go back and read.
"""
import logging
from logging.handlers import RotatingFileHandler

from lcycode.config.settings import WORKSPACE_ROOT

LOG_DIR = WORKSPACE_ROOT / ".lcycode" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "lcycode.log"

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_configured = False


def _configure_root():
    global _configured
    if _configured:
        return
    root = logging.getLogger("lcycode")
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3)
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(f"lcycode.{name.replace('lcycode.', '')}")
