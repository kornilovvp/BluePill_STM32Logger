"""Запись потока в CSV (Docs/40_Host/03): полный темп, отдельный поток.

Формат файла:

    # SLogger CSV v1
    # device: F103C6 | fw: 0.1.0 | proto: 1.0
    # started_local: 2026-08-02T21:15:00
    # rate_hz: 10000
    # vref_v: 3.300
    tick,t_s,A1_V,A2_V,D1,D2

Очередь записи не сбрасывается (FR-06); обрыв связи закрывает файл корректно.
"""

from __future__ import annotations

import queue
import threading
import time
from datetime import datetime
from pathlib import Path

from ..core import settings
from ..core.slp_protocol import BLOCK_TICKS, Block


class CsvRecorder:

    def __init__(self):
        self._q: queue.Queue[Block | None] = queue.Queue()
        self._thread: threading.Thread | None = None

        self._file = None
        self._path: Path | None = None

        self.rows      = 0
        self.bytes     = 0
        self.recording = False
        self.error: str | None = None

        self._vref      = settings.VREF_DEFAULT
        self._base_tick: int | None = None

    # ── управление (из GUI-потока) ──────────────────────────────────────────

    def start(self, directory: str, device_info: dict) -> Path | None:
        """Открыть файл и начать запись; None при ошибке (без исключений)."""

        self.error = None
        self._vref = device_info.get("vref_mv", 3300) / 1000.0

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path  = Path(directory) / f"slog_{stamp}.csv"

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(path, "w", encoding="utf-8", newline="\n")
            self._write_header(device_info)
        except OSError as exc:
            self.error = f"cannot open file: {exc}"
            self._file = None
            return None

        self._path      = path
        self.rows       = 0
        self.bytes      = 0
        self._base_tick = None
        self.recording  = True

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return path

    def push(self, block: Block) -> None:
        if self.recording:
            self._q.put(block)

    def stop(self) -> tuple[Path | None, int]:
        """Дописать очередь, закрыть файл; вернуть (путь, строк)."""

        if not self.recording:
            return self._path, self.rows

        self.recording = False
        self._q.put(None)                      # сигнал завершения

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        return self._path, self.rows

    # ── фоновый поток ───────────────────────────────────────────────────────

    def _run(self) -> None:
        last_flush = time.monotonic()

        while True:
            try:
                block = self._q.get(timeout=0.5)
            except queue.Empty:
                block = ...                    # тишина — повод для flush

            if block is None:
                break

            if block is not ...:
                try:
                    self._write_block(block)
                except OSError as exc:
                    self.error = f"write error: {exc}"
                    break

            if time.monotonic() - last_flush >= 1.0:
                last_flush = time.monotonic()
                try:
                    self._file.flush()
                except OSError:
                    pass

        try:
            self._file.flush()
            self._file.close()
        except OSError:
            pass

    # ── внутреннее ──────────────────────────────────────────────────────────

    def _write_header(self, info: dict) -> None:
        f = self._file
        f.write("# SLogger CSV v1\n")
        f.write(f"# device: {info.get('mcu', '?')} | fw: {info.get('fw', '?')}"
                f" | proto: {info.get('proto', '?')}\n")
        f.write(f"# started_local: {datetime.now().isoformat(timespec='seconds')}\n")
        f.write(f"# rate_hz: {settings.RATE_HZ}\n")
        f.write(f"# vref_v: {self._vref:.3f}\n")
        f.write("tick,t_s,A1_V,A2_V,D1,D2\n")

    def _write_block(self, b: Block) -> None:
        if self._base_tick is None:
            self._base_tick = b.first_tick

        lsb   = self._vref / 4095.0
        base  = self._base_tick
        lines = []

        for i in range(BLOCK_TICKS):
            tick = b.first_tick + i
            t_s  = (tick - base) / settings.RATE_HZ
            lines.append(
                f"{tick},{t_s:.4f},{b.a1[i] * lsb:.4f},{b.a2[i] * lsb:.4f},"
                f"{b.d1[i]},{b.d2[i]}\n"
            )

        text = "".join(lines)
        self._file.write(text)

        self.rows  += BLOCK_TICKS
        self.bytes += len(text)
