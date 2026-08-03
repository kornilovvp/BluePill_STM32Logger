"""Свойства сигналов симулятора (Docs/40_Host/04) и инъекции отказов."""

import queue

import numpy as np

from logger_app.core import settings
from logger_app.data.sources import SimSource


def _collect(seconds: float, **kwargs):
    """Прогнать симулятор в fast-режиме и склеить блоки в сплошные массивы."""

    q: queue.Queue = queue.Queue()
    sim = SimSource(q, **kwargs)
    sim.start_stream()

    n_blocks = int(seconds * settings.RATE_HZ / settings.BLOCK_TICKS)
    for _ in range(n_blocks):
        sim.produce_block()

    blocks = []
    while not q.empty():
        kind, value = q.get()
        if kind == "block":
            blocks.append(value)

    join = lambda field: np.concatenate([getattr(b, field) for b in blocks])
    return sim, blocks, join("a1"), join("a2"), join("d1"), join("d2")


# ── свойства сигналов ────────────────────────────────────────────────────────


def test_a1_sine_50hz():
    _, _, a1, _, _, _ = _collect(2.0)
    volts = a1 * settings.VREF_DEFAULT / 4095.0

    assert abs(volts.mean() - 1.65) < 0.02          # смещение

    crossings = np.sum((volts[:-1] < 1.65) & (volts[1:] >= 1.65))
    assert abs(crossings - 100) <= 2                # 50 Гц -> 100 восх. пересечений за 2 с


def test_a2_triangle_range():
    _, _, _, a2, _, _ = _collect(1.0)
    volts = a2 * settings.VREF_DEFAULT / 4095.0

    assert abs(volts.min() - 0.20) < 0.05
    assert abs(volts.max() - 3.10) < 0.05


def test_d1_pwm_duty():
    _, _, _, _, d1, _ = _collect(1.0)

    assert abs(d1.mean() - 0.30) < 0.01             # скважность 30 %

    edges = np.sum((d1[:-1] == 0) & (d1[1:] == 1))
    assert abs(edges - 100) <= 1                    # 100 фронтов в секунду


def test_d2_burst_five_pulses_per_second():
    _, _, _, _, _, d2 = _collect(2.0)

    second = d2[settings.RATE_HZ - 1 : 2 * settings.RATE_HZ]   # полная 2-я секунда
    edges  = np.sum((second[:-1] == 0) & (second[1:] == 1))

    assert edges == 5


# ── непрерывность и инъекции ─────────────────────────────────────────────────


def test_ticks_are_continuous():
    sim, blocks, *_ = _collect(1.0)

    ticks = [b.first_tick for b in blocks]
    assert ticks[0] == 0
    assert all(b - a == settings.BLOCK_TICKS for a, b in zip(ticks, ticks[1:]))
    assert sim.parser.lost_blocks == 0


def test_drop_injection_visible_in_parser():
    sim, *_ = _collect(1.0, drop_every=50)

    assert sim.parser.lost_blocks > 0


def test_corrupt_injection_counted_as_crc_error():
    sim, *_ = _collect(1.0, corrupt_every=50)

    assert sim.parser.crc_err > 0
    assert sim.parser.lost_blocks > 0               # битые кадры выпали из потока
