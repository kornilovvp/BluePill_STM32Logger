"""Кольцевые буферы: заворот, разрывы NaN, новая эпоха."""

import numpy as np

from logger_app.core import settings
from logger_app.data.buffers import ChannelRings
from logger_app.data.downsampling import minmax
from logger_app.core.slp_protocol import BLOCK_TICKS, Block


def _block(first_tick: int, value: int = 1000) -> Block:
    full  = np.full(BLOCK_TICKS, value, np.uint16)
    bits  = np.zeros(BLOCK_TICKS, np.uint8)
    return Block(first_tick, full, full, bits, bits)


def test_window_shorter_than_data():
    rings = ChannelRings(seconds=1)

    for i in range(10):
        rings.append(_block(i * BLOCK_TICKS))

    x, ch = rings.window(1.0)
    assert len(x) == 10 * BLOCK_TICKS
    assert x[-1] <= 0.0


def test_wraparound_keeps_only_capacity():
    rings = ChannelRings(seconds=1)                      # ёмкость 10 000
    blocks = settings.RATE_HZ // BLOCK_TICKS + 50        # больше ёмкости

    for i in range(blocks):
        rings.append(_block(i * BLOCK_TICKS))

    x, _ = rings.window(10.0)
    assert len(x) == rings.n


def test_gap_becomes_nan():
    rings = ChannelRings(seconds=1)

    rings.append(_block(0))
    rings.append(_block(BLOCK_TICKS * 4))                # пропали 3 блока

    _, ch = rings.window(1.0)
    assert np.isnan(ch["a1"]).sum() == 3 * BLOCK_TICKS


def test_epoch_reset_clears():
    rings = ChannelRings(seconds=1)

    rings.append(_block(BLOCK_TICKS * 100))
    rings.append(_block(0))                              # тик назад -> новая эпоха

    x, _ = rings.window(1.0)
    assert len(x) == BLOCK_TICKS                         # остался только новый блок


def test_minmax_preserves_spike():
    n = 40_000
    y = np.zeros(n, np.float32)
    y[12_345] = 3.3                                      # одиночный выброс
    x = np.arange(n, dtype=np.float32)

    _, yd = minmax(x, y, max_points=2000)

    assert len(yd) <= 2000
    assert yd.max() == np.float32(3.3)
