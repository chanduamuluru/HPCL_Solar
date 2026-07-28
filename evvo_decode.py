r"""
EVVO inverter register decoder (36-register block, HR 0..35).

All fields below were CONFIRMED on 2026-07-27 by cross-checking captured
registers against the inverter's front LCD (Today/Total/Power/AC/DC).
"""


def s16(v):
    return v - 0x10000 if v >= 0x8000 else v


STATUS = {0: "Standby", 1: "Starting", 2: "Normal", 3: "Fault"}


def decode_inverter(r):
    if len(r) < 33:
        return {"error": f"need 36 regs, got {len(r)}"}
    # R12 = native AC active power (x10 W -> /100 = kW). Confirmed vs LCD.
    # apparent kVA computed from V*I for reference (kVA >= kW by power factor).
    apparent_kVA = (r[15] / 10.0 * r[16] / 100.0
                    + r[17] / 10.0 * r[18] / 100.0
                    + r[19] / 10.0 * r[20] / 100.0) / 1000.0
    return {
        "status":        STATUS.get(r[0], f"code {r[0]}"),
        "power_kW":       round(r[12] / 100.0, 2),
        "apparent_kVA":   round(apparent_kVA, 2),
        "today_kWh":      r[25] / 100.0,
        "total_kWh":     (r[21] << 16) | r[22],
        "grid_freq_Hz":   r[14] / 100.0,
        # AC output (R / Y / B phases)
        "ac_R_V":         r[15] / 10.0,
        "ac_R_A":         r[16] / 100.0,
        "ac_Y_V":         r[17] / 10.0,
        "ac_Y_A":         r[18] / 100.0,
        "ac_B_V":         r[19] / 10.0,
        "ac_B_A":         r[20] / 100.0,
        # DC input (two MPPT strings)
        "pv1_V":          r[6] / 10.0,
        "pv1_A":          r[7] / 100.0,
        "pv2_V":          r[8] / 10.0,
        "pv2_A":          r[9] / 100.0,
        "temperature_C":  r[32],
    }


if __name__ == "__main__":
    sample = [2, 0, 0, 0, 0, 0, 6024, 781, 6693, 327, 471, 220, 677, 65529,
              4993, 2359, 969, 2335, 972, 2353, 977, 1, 8860, 0, 13290, 8153,
              605, 42, 53, 6893, 6012, 6678, 60, 0, 1, 0]
    for k, v in decode_inverter(sample).items():
        print(f"  {k:14} = {v}")
