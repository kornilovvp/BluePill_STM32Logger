"""Кольцевые буферы сигналов для отображения (окно до RING_SECONDS).

Аналоговые каналы хранятся в вольтах, цифровые — 0/1; всё float32.
Пропуски потока (потерянные блоки) заполняются NaN — ось времени честная,
разрыв виден на графике, а не склеивается.
"""

from __future__ import annotations

import numpy as np

from ..core import settings
from ..core.slp_protocol import BLOCK_TICKS, Block


class ChannelRings:

    def __init__(self,
                 seconds: int = settings.RING_SECONDS,
                 vref: float = settings.VREF_DEFAULT):

        self.n     = seconds * settings.RATE_HZ
        self.vref  = vref
        self._lsb  = np.float32(vref / 4095.0)

        self.ch = {
            "a1": np.full(self.n, np.nan, np.float32),
            "a2": np.full(self.n, np.nan, np.float32),
            "d1": np.full(self.n, np.nan, np.float32),
            "d2": np.full(self.n, np.nan, np.float32),
        }

        self.idx   = 0                      # позиция следующей записи
        self.count = 0                      # заполненность (для окна короче буфера)
        self.last_tick: int | None = None
        self.total_ticks = 0                # всего принято тиков (для фактической частоты)

    def set_vref(self, vref: float) -> None:
        """Опора из INFO? устройства (влияет на новые выборки)."""

        self.vref = vref
        self._lsb = np.float32(vref / 4095.0)

    # ── запись ──────────────────────────────────────────────────────────────

    def clear(self) -> None:
        for arr in self.ch.values():
            arr.fill(np.nan)

        self.idx = 0
        self.count = 0
        self.last_tick = None

    def append(self, b: Block) -> None:
        if self.last_tick is not None:
            gap = b.first_tick - (self.last_tick + BLOCK_TICKS)

            if gap < 0:
                self.clear()                        # новая эпоха (START/reconnect)
            elif gap > 0:
                self._write_nan(min(gap, self.n))   # потерянные блоки -> разрыв

        self.last_tick    = b.first_tick
        self.total_ticks += BLOCK_TICKS

        self._write("a1", b.a1.astype(np.float32) * self._lsb)
        self._write("a2", b.a2.astype(np.float32) * self._lsb)
        self._write("d1", b.d1.astype(np.float32))
        self._write("d2", b.d2.astype(np.float32))

        self._advance(BLOCK_TICKS)

    # ── чтение ──────────────────────────────────────────────────────────────

    def window(self, seconds: float) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """(x, {канал: y}) за последние `seconds`; x в секундах, 0 = «сейчас»."""

        k = min(self.count, int(seconds * settings.RATE_HZ))

        if k == 0:
            empty = np.empty(0, np.float32)
            return empty, {name: empty for name in self.ch}

        ind = np.arange(self.idx - k, self.idx) % self.n
        x   = (np.arange(-k, 0, dtype=np.float32) + 1.0) / settings.RATE_HZ

        return x, {name: arr[ind] for name, arr in self.ch.items()}

    # ── внутреннее ──────────────────────────────────────────────────────────

    def _write(self, name: str, values: np.ndarray) -> None:
        arr  = self.ch[name]
        i, j = self.idx, self.idx + len(values)

        if j <= self.n:
            arr[i:j] = values
        else:
            k = self.n - i
            arr[i:]           = values[:k]
            arr[: j - self.n] = values[k:]

    def _write_nan(self, gap: int) -> None:
        nan_block = np.full(gap, np.nan, np.float32)

        for name in self.ch:
            self._write(name, nan_block)

        self._advance(gap)

    def _advance(self, n: int) -> None:
        self.idx   = (self.idx + n) % self.n
        self.count = min(self.count + n, self.n)
