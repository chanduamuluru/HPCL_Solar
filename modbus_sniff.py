r"""
Passive Modbus RTU sniffer v2 (listen-only) for the EVVO / Wattmon bus.

Captures the raw byte stream, then splits it into frames using the Modbus
length/byte-count field validated by CRC (NOT fragile inter-frame timing).
This keeps long responses intact even when the USB adapter delivers them in
chunks. No transmit -> safe on the live bus.

Run:  python D:\firmwareApp\Genfirmware\modbus_sniff.py
"""

import serial
import time

PORT = "COM23"
BAUD = 9600
DURATION = 20            # seconds to listen


def crc(frame):
    c = 0xFFFF
    for b in frame:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return c


def crc_ok(frame):
    return len(frame) >= 4 and (frame[-2] | (frame[-1] << 8)) == crc(frame[:-2])


def candidate_lengths(buf, i):
    """Possible total frame lengths for the frame starting at i."""
    if i + 2 >= len(buf):
        return []
    fn = buf[i + 1]
    lens = []
    if fn in (3, 4):
        bc = buf[i + 2]
        if bc % 2 == 0:
            lens.append(3 + bc + 2)   # response
        lens.append(8)                # request
    elif fn in (5, 6):
        lens.append(8)                # write single (req and resp are 8)
    elif fn == 16:
        lens.append(8)                # write-multi response
        if i + 6 < len(buf):
            lens.append(7 + buf[i + 6] + 2)  # write-multi request
    else:
        lens.append(8)
    return lens


def parse(buf):
    frames = []
    i = 0
    while i < len(buf) - 3:
        matched = False
        for L in candidate_lengths(buf, i):
            if 4 <= L <= len(buf) - i and crc_ok(buf[i:i + L]):
                frames.append(buf[i:i + L])
                i += L
                matched = True
                break
        if not matched:
            i += 1
    return frames


def describe(f):
    sid, fn = f[0], f[1]
    if fn in (3, 4):
        if f[2] == len(f) - 5:          # response
            regs = [(f[3 + 2 * k] << 8) | f[4 + 2 * k] for k in range(f[2] // 2)]
            return f"id {sid:>2} RESP fn{fn} {len(regs)} regs -> {regs}"
        addr = (f[2] << 8) | f[3]; cnt = (f[4] << 8) | f[5]
        return f"id {sid:>2} REQ  fn{fn} addr {addr} x{cnt}"
    if fn in (5, 6):
        return f"id {sid:>2} WRITE reg {(f[2] << 8) | f[3]} = {(f[4] << 8) | f[5]}"
    return f"id {sid:>2} fn{fn} {f.hex(' ')}"


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0, parity="N", stopbits=1, bytesize=8)
    print(f"Listening on {PORT} @ {BAUD} for {DURATION}s...\n")
    buf = bytearray()
    end = time.time() + DURATION
    while time.time() < end:
        chunk = ser.read(4096)
        if chunk:
            buf += chunk
        else:
            time.sleep(0.002)
    ser.close()

    frames = parse(buf)
    responses = 0
    for f in frames:
        line = describe(f)
        print(line)
        if "RESP" in line:
            responses += 1
    print(f"\n{len(frames)} frames parsed, {responses} responses decoded "
          f"({len(buf)} raw bytes).")


if __name__ == "__main__":
    main()
