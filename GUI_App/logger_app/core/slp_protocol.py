"""Кодек протокола SLP v1: CRC16, потоковый парсер, сборщик кадров.

Единственный источник истины — Docs/20_Protocol/01_Protocol_SLP_v1.md.
Правильность закреплена тестами на golden-векторах (§5).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# ─────────────────────────────── константы кадра ────────────────────────────

SYNC0, SYNC1 = 0xAA, 0x55

TYPE_DATA = 0x01
TYPE_RESP = 0x02
TYPE_STAT = 0x03
TYPE_ERR  = 0x7F

BLOCK_TICKS      = 32
DATA_PAYLOAD_LEN = 4 + BLOCK_TICKS * 4     # first_tick + 32 тика × 4 байта
MAX_PAYLOAD      = 256


# ──────────────────────────────────── CRC16 ─────────────────────────────────
#  CRC16/CCITT-FALSE: poly 0x1021, init 0xFFFF; crc16(b"123456789") == 0x29B1

_CRC_TAB: list[int] = []

for _i in range(256):
    _c = _i << 8
    for _ in range(8):
        _c = ((_c << 1) ^ 0x1021) & 0xFFFF if _c & 0x8000 else (_c << 1) & 0xFFFF
    _CRC_TAB.append(_c)


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CRC_TAB[((crc >> 8) ^ b) & 0xFF]
    return crc


# ─────────────────────────────── блок данных ────────────────────────────────


@dataclass
class Block:
    """Один кадр DATA в разобранном виде: 32 тика, сырые отсчёты и биты."""

    first_tick: int
    a1: np.ndarray   # uint16[32], 0..4095
    a2: np.ndarray
    d1: np.ndarray   # uint8[32], 0/1
    d2: np.ndarray


def decode_data_payload(payload: bytes) -> Block:
    """Разобрать payload кадра DATA (формат тика — §2 протокола)."""

    first_tick = int.from_bytes(payload[0:4], "little")

    words = np.frombuffer(payload, dtype="<u2", offset=4)
    w = words.reshape(BLOCK_TICKS, 2)

    return Block(
        first_tick = first_tick,
        a1 = (w[:, 0] & 0x0FFF).astype(np.uint16),
        a2 = (w[:, 1] & 0x0FFF).astype(np.uint16),
        d1 = (w[:, 0] >> 15).astype(np.uint8),
        d2 = (w[:, 1] >> 15).astype(np.uint8),
    )


# ─────────────────────────────── потоковый парсер ───────────────────────────


class Parser:
    """Автомат разбора (§4): ресинхронизация с любого байта, счётчики ошибок."""

    def __init__(self):
        self.buf = bytearray()

        self.frames_ok    = 0
        self.crc_err      = 0
        self.resync_count = 0
        self.lost_blocks  = 0

        self._last_data_tick: int | None = None
        self._synced = True

    def reset_stream(self) -> None:
        """Новая эпоха тиков (после START) — забыть непрерывность."""

        self._last_data_tick = None

    def feed(self, data: bytes) -> list[tuple[int, int, bytes]]:
        """Скормить байты; вернуть готовые кадры как (type, seq, payload)."""

        out: list[tuple[int, int, bytes]] = []
        buf = self.buf
        buf += data

        while True:

            #  1. найти сигнатуру AA 55
            i = buf.find(b"\xaa\x55")
            if i < 0:
                if len(buf) > 1:
                    self._note_resync()
                    del buf[:-1]          # последний байт может быть 0xAA
                break
            if i > 0:
                self._note_resync()
                del buf[:i]

            #  2. дождаться заголовка и проверить длину
            if len(buf) < 8:
                break
            length = buf[4] | (buf[5] << 8)
            if length > MAX_PAYLOAD:
                del buf[:1]
                continue

            #  3. дождаться кадра целиком и проверить CRC
            end = 6 + length + 2
            if len(buf) < end:
                break
            body   = bytes(buf[2 : 6 + length])          # TYPE..PAYLOAD
            rx_crc = buf[6 + length] | (buf[7 + length] << 8)

            if crc16(body) != rx_crc:
                self.crc_err += 1
                self._synced = False
                del buf[:1]        # поиск со следующего байта после 0xAA (§4)
                continue

            #  4. кадр валиден
            self.frames_ok += 1
            self._synced = True

            ftype, seq = body[0], body[1]
            payload    = body[4:]

            if ftype == TYPE_DATA and len(payload) == DATA_PAYLOAD_LEN:
                self._track_losses(payload)

            out.append((ftype, seq, payload))
            del buf[:end]

        return out

    #  внутреннее ───────────────────────────────────────────────────────────

    def _track_losses(self, payload: bytes) -> None:
        ft = int.from_bytes(payload[0:4], "little")

        if self._last_data_tick is not None:
            gap = ft - (self._last_data_tick + BLOCK_TICKS)
            if gap > 0:
                self.lost_blocks += gap // BLOCK_TICKS

        self._last_data_tick = ft

    def _note_resync(self) -> None:
        if self._synced:
            self._synced = False
            self.resync_count += 1


# ─────────────────────────────── сборщик кадров ─────────────────────────────


class FrameBuilder:
    """Сборка кадров SLP — зеркало framer.c из CORE (нужен симулятору)."""

    def __init__(self):
        self.seq = 0

    def reset(self) -> None:
        self.seq = 0

    def frame(self, ftype: int, payload: bytes) -> bytes:
        length = len(payload)
        head   = bytes((SYNC0, SYNC1, ftype, self.seq, length & 0xFF, length >> 8))

        self.seq = (self.seq + 1) & 0xFF

        crc = crc16(head[2:] + payload)
        return head + payload + bytes((crc & 0xFF, crc >> 8))

    def data_frame(self, first_tick: int,
                   a1: np.ndarray, a2: np.ndarray,
                   d1: np.ndarray, d2: np.ndarray) -> bytes:

        w = np.empty((BLOCK_TICKS, 2), dtype="<u2")
        w[:, 0] = (a1.astype(np.uint16) & 0x0FFF) | (d1.astype(np.uint16) << 15)
        w[:, 1] = (a2.astype(np.uint16) & 0x0FFF) | (d2.astype(np.uint16) << 15)

        payload = int(first_tick).to_bytes(4, "little") + w.tobytes()
        return self.frame(TYPE_DATA, payload)
