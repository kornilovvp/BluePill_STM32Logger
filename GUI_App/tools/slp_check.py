"""Quick SLP v1 link check: PING -> INFO? -> START -> receive DATA -> STOP -> STAT?.

Usage:
    pip install pyserial
    python slp_check.py COM5 [seconds]

Validates against Docs/20_Protocol/01_Protocol_SLP_v1.md: frame sync/CRC16,
first_tick continuity (loss detection), effective sample rate, decoded values.
"""
import sys
import time

import serial


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC16/CCITT-FALSE (protocol section 1)."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


class Parser:
    """Streaming SLP frame parser with resync (protocol section 4)."""

    def __init__(self):
        self.buf = bytearray()
        self.frames_ok = 0
        self.crc_err = 0

    def feed(self, data: bytes):
        self.buf += data
        frames = []
        while True:
            i = self.buf.find(b"\xAA\x55")
            if i < 0:
                del self.buf[:-1]
                break
            if len(self.buf) < i + 8:
                del self.buf[:i]
                break
            length = self.buf[i + 4] | (self.buf[i + 5] << 8)
            if length > 256:
                del self.buf[: i + 1]
                continue
            end = i + 6 + length + 2
            if len(self.buf) < end:
                del self.buf[:i]
                break
            body = bytes(self.buf[i + 2 : i + 6 + length])  # TYPE..PAYLOAD
            rx_crc = self.buf[i + 6 + length] | (self.buf[i + 7 + length] << 8)
            if crc16(body) != rx_crc:
                self.crc_err += 1
                del self.buf[: i + 1]
                continue
            self.frames_ok += 1
            frames.append((body[0], body[1], body[4:]))  # type, seq, payload
            del self.buf[:end]
        return frames


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    port = sys.argv[1]
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0

    link = serial.Serial(port, timeout=0.2)
    parser = Parser()

    def cmd(text: bytes, wait: float = 0.15) -> list:
        link.write(text + b"\n")
        time.sleep(wait)
        return parser.feed(link.read(8192))

    for t, _seq, payload in cmd(b"PING"):
        if t == 0x02:
            print("PING  ->", payload.decode(errors="replace"))
    for t, _seq, payload in cmd(b"INFO?"):
        if t == 0x02:
            print("INFO? ->", payload.decode(errors="replace"))

    print(f"START -> приём потока {seconds:g} с...")
    cmd(b"START", wait=0.0)

    t0 = time.time()
    first_tick = last_tick = None
    lost_blocks = frames = 0
    a1_min, a1_max = 4095, 0
    sample_line = ""
    while time.time() - t0 < seconds:
        for t, _seq, payload in parser.feed(link.read(8192)):
            if t != 0x01:
                continue
            ft = int.from_bytes(payload[0:4], "little")
            if last_tick is not None and ft != last_tick + 32:
                lost_blocks += max(0, (ft - last_tick - 32) // 32)
            if first_tick is None:
                first_tick = ft
            last_tick = ft
            frames += 1
            w0 = int.from_bytes(payload[4:6], "little")
            w1 = int.from_bytes(payload[6:8], "little")
            a1, a2 = w0 & 0xFFF, w1 & 0xFFF
            d1, d2 = (w0 >> 15) & 1, (w1 >> 15) & 1
            a1_min, a1_max = min(a1_min, a1), max(a1_max, a1)
            sample_line = f"tick={ft} A1={a1} A2={a2} D1={d1} D2={d2}"
    duration = time.time() - t0

    cmd(b"STOP")
    for t, _seq, payload in cmd(b"STAT?"):
        if t == 0x03:
            print("STAT? ->", payload.decode(errors="replace"))

    ticks = (last_tick - first_tick + 32) if last_tick is not None else 0
    rate = ticks / duration if duration > 0 else 0.0
    print(
        f"\nИтог: DATA-кадров {frames}, тиков {ticks} за {duration:.2f} с "
        f"(~{rate:.0f} тик/с, ожидание 10000)"
    )
    print(
        f"Потеряно блоков: {lost_blocks} | ошибок CRC: {parser.crc_err} | "
        f"кадров всего: {parser.frames_ok}"
    )
    print(f"A1 min/max за прогон: {a1_min}/{a1_max} | последний тик: {sample_line}")

    ok = frames > 0 and parser.crc_err == 0 and 9500 <= rate <= 10500
    print("РЕЗУЛЬТАТ:", "OK" if ok else "ПРОВЕРИТЬ (см. цифры выше)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
