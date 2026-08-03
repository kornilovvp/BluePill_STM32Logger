"""Источники данных: реальная плата (SerialSource) и симулятор (SimSource).

Оба реализуют один контракт (Docs/40_Host/01) и складывают события в очередь:

    ("state", str)    — смена состояния канала: DISCONNECTED / CONNECTED /
                        STREAMING / NO_DATA
    ("info",  dict)   — паспорт устройства (ответ INFO?)
    ("block", Block)  — разобранный блок данных

GUI ничего не знает про порт и потоки; все вызовы pyserial живут в фоновом
потоке под try/except — обрыв это штатная ситуация (NFR-08).
"""

from __future__ import annotations

import json
import queue
import threading
import time
from abc import ABC, abstractmethod

import numpy as np
import serial
from serial.tools import list_ports

from ..core import settings
from ..core.slp_protocol import (
    TYPE_DATA, TYPE_ERR, TYPE_RESP, TYPE_STAT,
    Block, FrameBuilder, Parser, decode_data_payload,
)


# ────────────────────────────── общий контракт ──────────────────────────────


class DataSource(ABC):
    """Источник блоков; владеет своим фоновым потоком."""

    def __init__(self, out_q: queue.Queue):
        self.out_q  = out_q
        self.parser = Parser()

        self._thread: threading.Thread | None = None
        self._stop_ev = threading.Event()

        self.state = "DISCONNECTED"
        self.info: dict = {}

    # управление
    @abstractmethod
    def start_stream(self) -> None: ...

    @abstractmethod
    def stop_stream(self) -> None: ...

    def open(self) -> None:
        self._stop_ev.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop_ev.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def stats(self) -> dict:
        p = self.parser
        return {
            "frames_ok":   p.frames_ok,
            "crc_err":     p.crc_err,
            "lost_blocks": p.lost_blocks,
            "resync":      p.resync_count,
        }

    # внутреннее
    @abstractmethod
    def _run(self) -> None: ...

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.out_q.put(("state", state))

    def _dispatch(self, frames) -> None:
        for ftype, _seq, payload in frames:

            if ftype == TYPE_DATA:
                self.out_q.put(("block", decode_data_payload(payload)))

            elif ftype in (TYPE_RESP, TYPE_STAT, TYPE_ERR):
                try:
                    obj = json.loads(payload.decode("ascii", "replace"))
                except ValueError:
                    obj = {"raw": payload.decode("ascii", "replace")}
                if "fw" in obj:
                    self.info = obj
                    self.out_q.put(("info", obj))


# ─────────────────────────────── реальная плата ─────────────────────────────


def available_ports() -> list[str]:
    return [p.device for p in sorted(list_ports.comports(), key=lambda p: p.device)]


class SerialSource(DataSource):
    """Плата по COM-порту: FSM живучести из Docs/40_Host/01 (NFR-08).

    Автопереподключение не чаще 1 р/с, сторожевой таймер потока 1 с,
    авто-START после реконнекта, никаких исключений наружу.
    """

    def __init__(self, out_q: queue.Queue, port: str):
        super().__init__(out_q)

        self.port = port
        self._want_stream = False
        self._cmd_q: queue.Queue[bytes] = queue.Queue()

    # управление (из GUI-потока: только флаги и очередь команд)

    def start_stream(self) -> None:
        self._want_stream = True
        self.parser.reset_stream()
        self._cmd_q.put(b"START")

    def stop_stream(self) -> None:
        self._want_stream = False
        self._cmd_q.put(b"STOP")

    def request_stat(self) -> None:
        self._cmd_q.put(b"STAT?")

    # фоновый поток: весь pyserial только здесь

    def _run(self) -> None:
        link: serial.Serial | None = None
        last_frame_ts = 0.0

        while not self._stop_ev.is_set():

            # ── подключение ────────────────────────────────────────────────
            if link is None:
                link = self._try_connect()
                if link is None:
                    self._set_state("DISCONNECTED")
                    self._sleep(settings.RECONNECT_PERIOD_S)
                    continue

                last_frame_ts = time.monotonic()
                self._set_state("CONNECTED")

                if self._want_stream:            # авто-START после реконнекта
                    self.parser.reset_stream()
                    self._cmd_q.put(b"START")

            # ── обмен ──────────────────────────────────────────────────────
            try:
                while not self._cmd_q.empty():
                    link.write(self._cmd_q.get_nowait() + b"\n")

                chunk = link.read(4096)

            except (serial.SerialException, OSError):
                link = self._drop(link)          # порт исчез — штатно
                continue

            if chunk:
                frames = self.parser.feed(chunk)
                if frames:
                    last_frame_ts = time.monotonic()
                self._dispatch(frames)

            # ── состояние ──────────────────────────────────────────────────
            if self._want_stream:
                silent = time.monotonic() - last_frame_ts
                self._set_state(
                    "NO_DATA" if silent > settings.NO_DATA_TIMEOUT_S else "STREAMING"
                )
            else:
                self._set_state("CONNECTED")

        # выход: вежливо остановить поток и закрыть порт
        if link is not None:
            try:
                link.write(b"STOP\n")
                link.close()
            except (serial.SerialException, OSError):
                pass

    # внутреннее ────────────────────────────────────────────────────────────

    def _try_connect(self) -> serial.Serial | None:
        try:
            link = serial.Serial(self.port, timeout=0.05)
            link.reset_input_buffer()
            link.write(b"INFO?\n")
            return link
        except (serial.SerialException, OSError, ValueError):
            return None

    def _drop(self, link: serial.Serial) -> None:
        try:
            link.close()
        except (serial.SerialException, OSError):
            pass
        self._set_state("DISCONNECTED")
        self._sleep(settings.RECONNECT_PERIOD_S)
        return None

    def _sleep(self, seconds: float) -> None:
        self._stop_ev.wait(seconds)


# ──────────────────────────────── симулятор ─────────────────────────────────


class SimSource(DataSource):
    """Симулятор устройства (Docs/40_Host/04, FR-09).

    Генерирует БАЙТОВЫЙ поток SLP через FrameBuilder и прогоняет его через тот
    же Parser, что и реальные данные, — эталонная реализация протокола.

    Сигналы детерминированы от тика:
        A1 — синус 50 Гц, 1.65 ± 1.00 В, шум 5 мВ (seed 42)
        A2 — треугольник 5 Гц, 0.20…3.10 В
        D1 — меандр 100 Гц, скважность 30 %
        D2 — пачка из 5 импульсов 1 кГц каждую секунду
    """

    def __init__(self, out_q: queue.Queue,
                 drop_every: int = 0,
                 corrupt_every: int = 0):
        super().__init__(out_q)

        self.drop_every    = drop_every      # каждый N-й блок не отправляется
        self.corrupt_every = corrupt_every   # у каждого N-го кадра портится байт

        self.builder  = FrameBuilder()
        self.rng      = np.random.default_rng(42)

        self._abs_tick    = 0                # абсолютное время симулятора
        self._epoch_base  = 0
        self._streaming   = False
        self._block_no    = 0

        self.info = {
            "fw": "sim", "proto": "1.0", "mcu": "SIM",
            "rate": settings.RATE_HZ, "ch": "A2D2",
            "vref_mv": int(settings.VREF_DEFAULT * 1000),
        }

    # управление

    def start_stream(self) -> None:
        self.parser.reset_stream()
        self.builder.reset()
        self._epoch_base = self._abs_tick
        self._streaming  = True

    def stop_stream(self) -> None:
        self._streaming = False

    # фоновый поток: реальное время

    def _run(self) -> None:
        self._set_state("CONNECTED")
        self.out_q.put(("info", self.info))

        period    = settings.BLOCK_TICKS / settings.RATE_HZ      # 3.2 мс на блок
        next_time = time.monotonic()

        while not self._stop_ev.is_set():
            now = time.monotonic()

            if now < next_time:
                self._stop_ev.wait(next_time - now)
                continue

            next_time += period
            self.produce_block()
            self._set_state("STREAMING" if self._streaming else "CONNECTED")

    # генерация (используется и в реальном времени, и в fast-тестах)

    def produce_block(self) -> None:
        ticks = np.arange(self._abs_tick, self._abs_tick + settings.BLOCK_TICKS)
        self._abs_tick += settings.BLOCK_TICKS

        if not self._streaming:
            return

        a1, a2, d1, d2 = self._signals(ticks)
        first_tick     = int(ticks[0] - self._epoch_base)

        raw = self.builder.data_frame(first_tick, a1, a2, d1, d2)
        self._block_no += 1

        if self.drop_every and self._block_no % self.drop_every == 0:
            return                                    # «потерянный» блок

        if self.corrupt_every and self._block_no % self.corrupt_every == 0:
            bad = bytearray(raw)
            bad[10] ^= 0xFF                           # ошибка CRC на приёме
            raw = bytes(bad)

        self._dispatch(self.parser.feed(raw))

    def _signals(self, ticks: np.ndarray):
        t = ticks / settings.RATE_HZ

        a1_v = 1.65 + 1.00 * np.sin(2 * np.pi * 50.0 * t) \
                    + self.rng.normal(0.0, 0.005, len(t))

        phase = (t * 5.0) % 1.0                       # треугольник 5 Гц
        a2_v  = 0.20 + 2.90 * (1.0 - np.abs(2.0 * phase - 1.0))

        d1 = ((t * 100.0) % 1.0) < 0.30               # меандр 100 Гц, 30 %

        t_in_s = t % 1.0                              # пачка 5 имп. 1 кГц каждые 1 с
        d2 = (t_in_s < 0.005) & ((t_in_s * 1000.0) % 1.0 < 0.5)

        to_counts = lambda v: np.clip(v / self.info_vref() * 4095.0, 0, 4095)

        return (
            to_counts(a1_v).astype(np.uint16),
            to_counts(a2_v).astype(np.uint16),
            d1.astype(np.uint8),
            d2.astype(np.uint8),
        )

    def info_vref(self) -> float:
        return self.info["vref_mv"] / 1000.0
