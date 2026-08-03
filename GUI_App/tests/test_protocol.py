"""Кодек SLP против golden-векторов (Docs/20_Protocol §5) + свойства парсера."""

import numpy as np
import pytest

from logger_app.core.slp_protocol import (
    TYPE_DATA, Block, FrameBuilder, Parser, crc16, decode_data_payload,
)


GOLDEN_FRAME = bytes.fromhex("AA5501000C000000000023815604FF07FF8FBDAD")


# ── §5.1: CRC ────────────────────────────────────────────────────────────────


def test_crc16_reference_value():
    assert crc16(b"123456789") == 0x29B1


# ── §5.2: тестовый кадр ──────────────────────────────────────────────────────


def test_golden_frame_parses():
    frames = Parser().feed(GOLDEN_FRAME)

    assert len(frames) == 1
    ftype, seq, payload = frames[0]

    assert ftype == TYPE_DATA
    assert seq == 0
    assert int.from_bytes(payload[0:4], "little") == 0

    words = np.frombuffer(payload, dtype="<u2", offset=4)
    assert list(words) == [0x8123, 0x0456, 0x07FF, 0x8FFF]


def test_builder_reproduces_golden_frame():
    words   = np.array([0x8123, 0x0456, 0x07FF, 0x8FFF], dtype="<u2")
    payload = (0).to_bytes(4, "little") + words.tobytes()

    assert FrameBuilder().frame(TYPE_DATA, payload) == GOLDEN_FRAME


# ── круговой тест: собрали 32 тика — разобрали без потерь ────────────────────


def test_data_frame_roundtrip():
    rng = np.random.default_rng(7)

    a1 = rng.integers(0, 4096, 32).astype(np.uint16)
    a2 = rng.integers(0, 4096, 32).astype(np.uint16)
    d1 = rng.integers(0, 2, 32).astype(np.uint8)
    d2 = rng.integers(0, 2, 32).astype(np.uint8)

    raw = FrameBuilder().data_frame(12345, a1, a2, d1, d2)
    (ftype, _seq, payload), = Parser().feed(raw)
    block = decode_data_payload(payload)

    assert ftype == TYPE_DATA
    assert block.first_tick == 12345
    assert np.array_equal(block.a1, a1)
    assert np.array_equal(block.a2, a2)
    assert np.array_equal(block.d1, d1)
    assert np.array_equal(block.d2, d2)


# ── устойчивость: мусор, дробление, битый CRC, потери ────────────────────────


def test_resync_on_garbage():
    parser = Parser()
    noisy = b"\x00\xaaXX" + GOLDEN_FRAME + b"\xff\xff" + GOLDEN_FRAME

    frames = parser.feed(noisy)

    assert len(frames) == 2
    assert parser.crc_err == 0
    assert parser.resync_count >= 1


def test_byte_by_byte_feeding():
    parser = Parser()
    frames = []

    for i in range(len(GOLDEN_FRAME)):
        frames += parser.feed(GOLDEN_FRAME[i : i + 1])

    assert len(frames) == 1


def test_corrupted_crc_is_counted_and_skipped():
    bad = bytearray(GOLDEN_FRAME)
    bad[10] ^= 0xFF

    parser = Parser()
    frames = parser.feed(bytes(bad) + GOLDEN_FRAME)

    assert len(frames) == 1
    assert parser.crc_err == 1


def test_lost_blocks_detected_by_first_tick():
    b = FrameBuilder()
    zeros = np.zeros(32, np.uint16)
    zbits = np.zeros(32, np.uint8)

    stream = (b.data_frame(0,   zeros, zeros, zbits, zbits)
              + b.data_frame(32,  zeros, zeros, zbits, zbits)
              + b.data_frame(160, zeros, zeros, zbits, zbits))   # пропущено 3 блока

    parser = Parser()
    parser.feed(stream)

    assert parser.lost_blocks == 3
    assert parser.frames_ok == 3
