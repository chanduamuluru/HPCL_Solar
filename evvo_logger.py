r"""
EVVO passive logger (listen-only) — captures EVERY Modbus response on the bus
so no register is ever missed, and writes it to disk.

Outputs (created under .\logs\):
  * evvo_raw.jsonl  - one line per response: timestamp, unit id, start addr,
                      count, and the FULL raw register list. Complete record.
  * inverter.csv    - decoded rows for inverters (ids 1,2,3) for easy viewing.

Responses don't carry the start address, so we tag each response with the
address from the matching preceding request (per unit id).

No transmit -> safe on the live bus. Stop with Ctrl+C.
Run:  python D:\firmwareApp\Genfirmware\evvo_logger.py
"""

import serial
import time
import json
import os
import csv
from datetime import datetime, timezone
from evvo_decode import decode_inverter

PORT = "COM23"
BAUD = 9600
INVERTERS = {1, 2, 3}
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

last_req = {}          # id -> (addr, count) from the most recent request
counts = {}            # id -> responses logged


def crc(fr):
    c = 0xFFFF
    for b in fr:
        c ^= b
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
    return c


def crc_ok(fr):
    return len(fr) >= 4 and (fr[-2] | (fr[-1] << 8)) == crc(fr[:-2])


def cand_lens(buf, i):
    if i + 2 >= len(buf):
        return []
    fn = buf[i + 1]
    if fn in (3, 4):
        lens = []
        if buf[i + 2] % 2 == 0:
            lens.append(3 + buf[i + 2] + 2)     # response
        lens.append(8)                          # request
        return lens
    return [8]                                  # write / others


def consume(buf):
    """Return (frames, leftover). Keeps incomplete trailing bytes for next read."""
    frames, i = [], 0
    while i <= len(buf) - 4:
        matched = False
        for L in cand_lens(buf, i):
            if 4 <= L <= len(buf) - i and crc_ok(buf[i:i + L]):
                frames.append(buf[i:i + L]); i += L; matched = True; break
        if not matched:
            if len(buf) - i < 300:              # maybe a partial frame; wait
                break
            i += 1
    return frames, buf[i:]


def main():
    os.makedirs(LOG_DIR, exist_ok=True)
    raw_path = os.path.join(LOG_DIR, "evvo_raw.jsonl")
    csv_path = os.path.join(LOG_DIR, "inverter.csv")

    raw_f = open(raw_path, "a", encoding="utf-8")
    new_csv = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
    csv_f = open(csv_path, "a", newline="", encoding="utf-8")
    csv_w = csv.writer(csv_f)
    csv_cols = ["ts", "id", "status", "power_kW", "apparent_kVA", "today_kWh",
                "total_kWh", "grid_freq_Hz", "ac_R_V", "ac_R_A", "ac_Y_V",
                "ac_Y_A", "ac_B_V", "ac_B_A", "pv1_V", "pv1_A", "pv2_V",
                "pv2_A", "temperature_C"]
    if new_csv:
        csv_w.writerow(csv_cols)
        csv_f.flush()

    ser = serial.Serial(PORT, BAUD, timeout=0, parity="N", stopbits=1, bytesize=8)
    print(f"Logging {PORT} @ {BAUD}")
    print(f"  raw -> {raw_path}")
    print(f"  csv -> {csv_path}")
    print("Ctrl+C to stop.\n")

    buf = bytearray()
    last_status = 0
    try:
        while True:
            chunk = ser.read(4096)
            if chunk:
                buf += chunk
                frames, leftover = consume(buf)
                buf = bytearray(leftover)
                for f in frames:
                    sid, fn = f[0], f[1]
                    if fn not in (3, 4):
                        continue
                    if len(f) == 8:                       # request
                        last_req[sid] = ((f[2] << 8) | f[3], (f[4] << 8) | f[5])
                        continue
                    if f[2] != len(f) - 5:                # not a clean response
                        continue
                    regs = [(f[3 + 2 * k] << 8) | f[4 + 2 * k]
                            for k in range(f[2] // 2)]
                    addr, _ = last_req.get(sid, (None, None))
                    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
                    rec = {"ts": ts, "id": sid, "fn": fn,
                           "addr": addr, "count": len(regs), "regs": regs}
                    raw_f.write(json.dumps(rec) + "\n")
                    raw_f.flush()                          # never lose a record
                    counts[sid] = counts.get(sid, 0) + 1

                    if sid in INVERTERS and len(regs) >= 33:
                        d = decode_inverter(regs)
                        csv_w.writerow([ts, sid] + [d[c] for c in csv_cols[2:]])
                        csv_f.flush()

            if time.time() - last_status >= 5:
                summary = "  ".join(f"id{k}:{v}" for k, v in sorted(counts.items()))
                print(f"\r{datetime.now().strftime('%H:%M:%S')}  responses -> "
                      f"{summary or 'none yet'}    ", end="", flush=True)
                last_status = time.time()
            time.sleep(0.005)
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        ser.close()
        raw_f.close()
        csv_f.close()


if __name__ == "__main__":
    main()
