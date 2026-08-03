"""Сборка приложения: источники → буферы → графики → запись.

Главный поток владеет GUI и render-циклом; источники и запись живут в своих
потоках и общаются через очереди. Обрыв связи — штатная ситуация (NFR-08).
"""

from __future__ import annotations

import queue
import time

import dearpygui.dearpygui as dpg

from .core import settings
from .data.buffers import ChannelRings
from .data.csv_recorder import CsvRecorder
from .data.sources import DataSource, SerialSource, SimSource, available_ports
from .gui.main_window import MainWindow


class App:

    def __init__(self, args):
        self.args = args
        self.cfg  = settings.load()

        self.events: queue.Queue = queue.Queue(maxsize=2000)
        self.rings    = ChannelRings()
        self.recorder = CsvRecorder()

        self.source: DataSource | None = None
        self.streaming = False

        self.ui = MainWindow({
            "connect":        lambda *_: self._toggle_connect(),
            "start_stop":     lambda *_: self._toggle_stream(),
            "record":         lambda *_: self._toggle_record(),
            "refresh_ports":  lambda *_: self.ui.set_ports(available_ports()),
            "window_changed": lambda *_: None,
            "sim_toggled":    lambda *_: None,
        })

        #  фактическая частота: считаем принятые тики раз в секунду
        self._rate = None
        self._rate_ts = time.monotonic()
        self._rate_ticks = 0

    # ────────────────────────────── запуск ──────────────────────────────────

    def run(self) -> None:
        self.ui.build(available_ports(), self.cfg)

        if self.args.sim:
            dpg.set_value("sim", True)
        if self.args.port:
            dpg.set_value("port", self.args.port)

        next_redraw = 0.0

        try:
            while dpg.is_dearpygui_running():
                self._drain_events()

                now = time.monotonic()
                if now >= next_redraw:
                    next_redraw = now + 1.0 / settings.GUI_UPDATE_HZ
                    self._redraw()

                dpg.render_dearpygui_frame()
        finally:
            self._shutdown()

    # ─────────────────────────── обработчики UI ─────────────────────────────

    def _toggle_connect(self) -> None:
        if self.source is None:
            self._connect()
        else:
            self._disconnect()

    def _connect(self) -> None:
        if self.ui.sim_mode():
            self.source = SimSource(self.events)
        else:
            port = self.ui.selected_port()
            if not port:
                return
            self.cfg["port"] = port
            self.source = SerialSource(self.events, port)

        self.rings.clear()
        self.ui.charts.clear()
        self.source.open()
        self.ui.set_connected(True)

    def _disconnect(self) -> None:
        if self.streaming:
            self._toggle_stream()
        if self.recorder.recording:
            self._toggle_record()

        self.source.close()
        self.source = None

        self.ui.set_connected(False)
        self.ui.set_link_state("DISCONNECTED")

    def _toggle_stream(self) -> None:
        if self.source is None:
            return

        self.streaming = not self.streaming

        if self.streaming:
            self.rings.clear()
            self.ui.charts.clear()
            self.source.start_stream()
        else:
            self.source.stop_stream()
            if self.recorder.recording:
                self._toggle_record()

        self.ui.set_streaming(self.streaming)

    def _toggle_record(self) -> None:
        if self.source is None:
            return

        if not self.recorder.recording:
            path = self.recorder.start(self.cfg["recordings_dir"], self.source.info)
            if path is None:
                self.ui.set_record_status(f"ERROR: {self.recorder.error}")
                return
            self.ui.set_recording(True)
        else:
            path, rows = self.recorder.stop()
            self.ui.set_recording(False)
            name = path.name if path else "?"
            self.ui.set_record_status(f"saved {rows} rows -> {name}")

    # ────────────────────────── конвейер данных ─────────────────────────────

    def _drain_events(self) -> None:
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "block":
                self.rings.append(value)
                self.recorder.push(value)
                self._rate_ticks += len(value.a1)

            elif kind == "state":
                self.ui.set_link_state(value)

            elif kind == "info":
                self.rings.set_vref(value.get("vref_mv", 3300) / 1000.0)

    def _redraw(self) -> None:
        window_s = self.ui.window_seconds()
        self.cfg["window_s"] = window_s

        x, channels = self.rings.window(window_s)
        if len(x):
            self.ui.charts.update(x, channels, window_s)

        self._update_statusbar()

    def _update_statusbar(self) -> None:
        now = time.monotonic()
        if now - self._rate_ts >= 1.0:
            self._rate = self._rate_ticks / (now - self._rate_ts)
            self._rate_ticks = 0
            self._rate_ts = now
            if not self.streaming:
                self._rate = None

        stats = self.source.stats() if self.source else {}
        self.ui.set_counters(self._rate,
                             stats.get("lost_blocks", 0),
                             stats.get("crc_err", 0))

        if self.recorder.recording:
            self.ui.set_record_status(
                f"REC: {self.recorder.rows} rows, "
                f"{self.recorder.bytes / 1e6:.1f} MB"
            )

    # ────────────────────────────── выход ───────────────────────────────────

    def _shutdown(self) -> None:
        """Порядок важен (Docs/40_Host/01): стоп → порт → CSV → GUI."""

        if self.source is not None:
            try:
                self.source.stop_stream()
                self.source.close()
            except Exception:
                pass

        self.recorder.stop()
        settings.save(self.cfg)
        dpg.destroy_context()
