"""Настройки: константы приложения и пользовательский config.json."""

from __future__ import annotations

import json
from pathlib import Path


# ─────────────────────────── протокол и устройство ───────────────────────────
#  Контракт: Docs/20_Protocol/01_Protocol_SLP_v1.md

RATE_HZ      = 10_000     # частота выборки, тиков в секунду
BLOCK_TICKS  = 32         # тиков в одном кадре DATA
VREF_DEFAULT = 3.300      # опора АЦП, вольты (уточняется полем vref_mv из INFO?)
PROTO_MAJOR  = 1          # поддерживаемый мажор протокола


# ─────────────────────────────── отображение ────────────────────────────────

RING_SECONDS      = 10           # ёмкость буферов = максимальное окно, секунд
WINDOW_CHOICES    = (1, 5, 10)   # варианты окна на экране
GUI_UPDATE_HZ     = 30           # частота обновления графиков
MAX_PLOT_POINTS   = 2_000        # точек на кривую после децимации


# ─────────────────────────────── живучесть (NFR-08) ─────────────────────────

NO_DATA_TIMEOUT_S  = 1.0   # нет кадров дольше — состояние «нет данных»
RECONNECT_PERIOD_S = 1.0   # период попыток переподключения


# ─────────────────────────────── пути и config.json ─────────────────────────

APP_DIR        = Path(__file__).resolve().parents[2]         # GUI_App/
CONFIG_PATH    = APP_DIR / "config.json"
RECORDINGS_DIR = APP_DIR / "recordings"

_DEFAULTS = {
    "port":           "COM11",
    "window_s":       5,
    "recordings_dir": str(RECORDINGS_DIR),
}


def load() -> dict:
    """Настройки пользователя; битый или отсутствующий файл — дефолты."""

    cfg = dict(_DEFAULTS)

    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass

    return cfg


def save(cfg: dict) -> None:
    """Сохранить молча: настройки не стоят падения приложения (NFR-08)."""

    try:
        text = json.dumps(cfg, ensure_ascii=False, indent=2)
        CONFIG_PATH.write_text(text, encoding="utf-8")
    except OSError:
        pass
