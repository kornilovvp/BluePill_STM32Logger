"""Главное окно: тулбар, четыре графика, статус-бар, горячие клавиши.

Логики здесь нет — только виджеты и колбэки, которые передаёт app.py.
"""

from __future__ import annotations

import os

import dearpygui.dearpygui as dpg

from ..core import settings
from .charts import Charts


_STATE_BADGE = {
    "DISCONNECTED": ("NO LINK",    (235, 100, 100)),
    "CONNECTED":    ("CONNECTED",  (170, 170, 170)),
    "STREAMING":    ("STREAMING",  (120, 220, 120)),
    "NO_DATA":      ("NO DATA",    (255, 200,  60)),
}

_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]


class MainWindow:
    """Строит интерфейс; callbacks — словарь обработчиков из app.py."""

    def __init__(self, callbacks: dict):
        self.cb = callbacks
        self.charts = Charts()

    # ── построение ──────────────────────────────────────────────────────────

    def build(self, ports: list[str], cfg: dict) -> None:
        dpg.create_context()
        _load_cyrillic_font()

        dpg.create_viewport(title="SLogger - 4-channel logger",
                            width=1150, height=760)

        with dpg.window(tag="primary"):
            self._build_toolbar(ports, cfg)
            with dpg.child_window(height=-34, border=False):
                self.charts.build()
            self._build_statusbar()

        self._build_hotkeys()

        dpg.set_primary_window("primary", True)
        dpg.setup_dearpygui()
        dpg.show_viewport()

    def _build_toolbar(self, ports: list[str], cfg: dict) -> None:
        with dpg.group(horizontal=True):
            dpg.add_combo(ports, tag="port", width=110,
                          default_value=cfg.get("port", ""))
            dpg.add_button(label="Refresh", callback=self.cb["refresh_ports"])
            dpg.add_button(label="Connect", tag="btn_connect", width=110,
                           callback=self.cb["connect"])

            dpg.add_spacer(width=14)
            dpg.add_button(label="Start", tag="btn_stream", width=90,
                           callback=self.cb["start_stop"], enabled=False)
            dpg.add_button(label="Record", tag="btn_record", width=90,
                           callback=self.cb["record"], enabled=False)

            dpg.add_spacer(width=14)
            dpg.add_text("Window:")
            dpg.add_radio_button([f"{s} s" for s in settings.WINDOW_CHOICES],
                                 tag="window", horizontal=True,
                                 default_value=f"{cfg.get('window_s', 5)} s",
                                 callback=self.cb["window_changed"])

            dpg.add_spacer(width=14)
            dpg.add_checkbox(label="Simulator", tag="sim",
                             callback=self.cb["sim_toggled"])

    def _build_statusbar(self) -> None:
        with dpg.group(horizontal=True):
            dpg.add_text("NO LINK", tag="st_state",
                         color=_STATE_BADGE["DISCONNECTED"][1])
            dpg.add_text(" | ")
            dpg.add_text("- sps", tag="st_rate")
            dpg.add_text(" | ")
            dpg.add_text("lost: 0", tag="st_lost")
            dpg.add_text(" | ")
            dpg.add_text("CRC: 0", tag="st_crc")
            dpg.add_text(" | ")
            dpg.add_text("", tag="st_rec")

    def _build_hotkeys(self) -> None:
        with dpg.handler_registry():
            dpg.add_key_press_handler(dpg.mvKey_Spacebar,
                                      callback=self.cb["start_stop"])
            dpg.add_key_press_handler(dpg.mvKey_R, callback=self.cb["record"])

    # ── обновление из app.py ────────────────────────────────────────────────

    def set_link_state(self, state: str) -> None:
        text, color = _STATE_BADGE.get(state, (state, (200, 200, 200)))
        dpg.set_value("st_state", text)
        dpg.configure_item("st_state", color=color)

    def set_streaming(self, streaming: bool) -> None:
        dpg.configure_item("btn_stream",
                           label=("Stop" if streaming else "Start"))

    def set_connected(self, connected: bool) -> None:
        dpg.configure_item("btn_connect",
                           label=("Disconnect" if connected else "Connect"))
        dpg.configure_item("btn_stream", enabled=connected)
        dpg.configure_item("btn_record", enabled=connected)

    def set_recording(self, recording: bool) -> None:
        dpg.configure_item("btn_record",
                           label=("Stop rec" if recording else "Record"))

    def set_counters(self, rate: float | None, lost: int, crc: int) -> None:
        dpg.set_value("st_rate",
                      f"{rate:.0f} sps" if rate is not None else "- sps")
        dpg.set_value("st_lost", f"lost: {lost}")
        dpg.set_value("st_crc",  f"CRC: {crc}")

    def set_record_status(self, text: str) -> None:
        dpg.set_value("st_rec", text)

    # ── чтение виджетов ─────────────────────────────────────────────────────

    def selected_port(self) -> str:
        return dpg.get_value("port")

    def sim_mode(self) -> bool:
        return dpg.get_value("sim")

    def window_seconds(self) -> int:
        return int(dpg.get_value("window").split()[0])

    def set_ports(self, ports: list[str]) -> None:
        dpg.configure_item("port", items=ports)


# ── внутреннее ──────────────────────────────────────────────────────────────


def _load_cyrillic_font() -> None:
    """Штатный шрифт DPG без кириллицы — берём системный, какой найдётся."""

    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            with dpg.font_registry():
                font = dpg.add_font(path, 16)   # диапазоны в DPG 2.x автоматические
            dpg.bind_font(font)
            return
