# HPCL Solar — EVVO Inverter Data Analysis
## Final report

**Corpus:** 10,648 unique samples, three inverters, 2026-08-01 09:46 IST →
2026-08-02 16:51 IST (31 hours, covering two sunrises' worth of daylight
including one sunset and one full 11-hour day).

| Source file | UTC window | IST window | Rows |
|---|---|---|---|
| `hpcl_solardata_01_08` | Aug 1, 04:16–13:30 | 09:46–19:00 | 1,305 |
| `hpcl_solardata` | Aug 2, 00:22–05:47 | 05:52–11:17 | 4,589 |
| `hpcl_solardata_02_08` | Aug 2, 05:47–11:21 | 11:17–16:51 | 4,754 |

Zero duplicate `reading_id` values across the three files; the Aug 2 pair joins
seamlessly at 05:47:15 → 05:47:26 UTC. Every row carried exactly 36 registers.

---

# 1. Executive summary

**The register map is fully validated.** All decode identities hold across
10,648 samples. The map in `REGISTER_MAP.md` and the decoder in
`register_map.py` can be treated as production-ready.

**Four things need attention, in priority order:**

| # | Finding | Severity | Action |
|---|---|---|---|
| 1 | **Plant-wide grid trip**, 13:14–13:26 IST Aug 2, all three units | **High** | Investigate grid side; ~3.1 kWh lost |
| 2 | **Inverter 1 string-voltage anomaly** — both MPPTs report identical voltage in 98.4% of samples | **High** | Physical inspection of DC input |
| 3 | **Sustained grid overvoltage** — 690 samples above 253 V during peak export, peaking at 258.2 V | **High** | Raise with utility / check transformer tap |
| 4 | **Inverter 3 running hot** — heatsink reached 70 °C | Medium | Check ventilation and filters |
| 5 | Capacity ratings were underestimated; revised upward | Low | Confirm from nameplates |

**Plant performance is otherwise good.** Aug 2 yield was 215.15 kWh across the
three units to 16:51 IST, with conversion efficiency of 95.6–97.4% and grid
frequency at 50.01 Hz median.

Findings 1 and 3 are probably related — see section 5.

---

# 2. Finding 1 — Plant-wide grid trip (High)

## What happened

At **13:13:58 IST on 2026-08-02**, all three inverters dropped to zero output
within one second of each other while still reporting status = Normal.

```
13:05:00  inv1 3.07 kW   inv2 5.53 kW   inv3 8.87 kW   50.05 Hz   normal
13:13:58  inv1 0.00 kW   inv2 0.00 kW   inv3 0.00 kW   50.44 Hz   <- all three, same second
   ...    frequency elevated 50.3-50.55 Hz for ~10 minutes, zero output
13:23:02  inv1/2/3 status=3 FAULT, flag r1 = 2 (bit 1), same second
13:24:45  inv1 additionally flag r1 = 8 (bit 3)
13:24:06  inv2 recovers
13:25:52  inv3 recovers -> 21.3 kW, climbing to 24.5 kW
```

## Why this is a grid event, not an inverter fault

Four independent lines of evidence:

1. **Simultaneity.** Three separately-polled Modbus slaves dropped to zero
   within the same second and faulted within the same second. No plausible
   independent-failure mechanism does that.
2. **Frequency signature.** All 12 out-of-band frequency samples in the entire
   corpus fall inside this window, on all three units: 50.51–50.55 Hz. Rising
   frequency with generation curtailment is the classic signature of an
   over-frequency condition or an upstream trip.
3. **DC side stayed healthy.** String voltages rose to open-circuit (inv1 342 V
   → 684 V, inv2 554 V → 756 V) exactly as expected when an inverter stops
   drawing from the array. The panels were fine; the inverters stopped
   exporting.
4. **Recovery was strong.** Inverter 3 returned to 21.3 kW immediately and
   climbed to 24.5 kW — no derating, no repeat fault.

## Fault flags observed

| Flag | Register | Units affected | Context |
|---|---|---|---|
| `r1 = 2` (bit 1) | fault word 1 | **all three, simultaneously** | 13:23:02, during grid event |
| `r1 = 8` (bit 3) | fault word 1 | inverter 1 only | 13:24:45, 100 s later |
| `r4 = 128` (bit 7) | fault word 4 | inverter 1 only | 06:08 IST startup, 5 samples |

**Interpretation:** `r1` appears to be the grid-related fault word and `r4` a
startup/DC-related one. The exact bit meanings are not in EVVO's published
manual — **request the fault code table from EVVO support**, quoting these
three observed values. That table would let the dashboard show real fault text
instead of a bit index.

## Energy impact

| | Downtime | Power before | Estimated loss |
|---|---|---|---|
| inv 1 | 1.1 min | 8.69 kW | ~0.2 kWh |
| inv 2 | 10.1 min | 5.72 kW | ~1.0 kWh |
| inv 3 | 11.9 min | 9.35 kW | ~1.9 kWh |
| **Total** | | | **~3.1 kWh** |

Small in absolute terms. It matters as a **signal**, not as a loss: if this
recurs, it points to a grid stability or protection-coordination problem on the
HPCL side of the meter that will eventually cause longer outages.

**Recommended action:** correlate 13:14–13:26 IST on 2026-08-02 against site
electrical logs and any utility notifications. If nothing is found, add
frequency-excursion alerting so the next occurrence is caught live.

---

# 3. Finding 2 — Inverter 1 string anomaly (High)

## The evidence

Rows where the two MPPT string voltages agree to within 2 V:

| | Aug 1 | Aug 2 AM | Full corpus | Verdict |
|---|---|---|---|---|
| **inv 1** | 99.6% | 99.7% | **98.4%** (3315/3370) | **anomalous** |
| inv 2 | 2.5% | 2.8% | 2.1% (75/3579) | normal |
| inv 3 | 0.5% | 0.3% | 1.1% (41/3699) | normal |

Two independent MPPT trackers, on independently-oriented sub-arrays, holding
within 2 V of each other across 3,315 samples spanning two days is not
physically plausible. Independent trackers diverge as irradiance differs
between strings — which is exactly what inverters 2 and 3 show.

## Corroborating signals

**Per-string power identity is broken.** The ratio of computed V×I to the
inverter's own reported string power:

| | median | p5 | p95 | spread |
|---|---|---|---|---|
| **inv 1** | 1.0015 | **0.705** | **1.497** | **±50%** |
| inv 2 | 1.0004 | 0.992 | 1.011 | ±1% |
| inv 3 | 1.0002 | 0.988 | 1.015 | ±1.5% |

The median is correct, so the *total* is right — but individual string
readings scatter by up to 50%. That is consistent with one voltage channel
mirroring the other while the current channels stay independent.

**Lowest conversion efficiency of the three:** 95.6% median, p5 92.7%, versus
97.4% and 96.8%.

**Most fault events:** 7 of the 9 faults in the entire corpus, including the
only startup fault (`r4 = 128`, 06:08 IST) which no other unit exhibited.

Note that during that startup fault, `pv1 = pv2 = 438 V` exactly — the two
strings reading identically even at the moment of a fault.

## Two candidate explanations

1. **Both DC inputs paralleled onto one array.** If someone wired a single
   string across both MPPT inputs, both would read the same voltage by
   definition. This is a commissioning error, not a failure — but it means the
   unit is running one MPPT instead of two, losing yield whenever the array is
   partially shaded.
2. **One voltage-sense channel has failed** and is reporting its neighbour's
   value.

Either way the *total* power figures remain trustworthy (the median identity
holds), but **per-string diagnostics from inverter 1 are meaningless** and
should be suppressed or flagged in the dashboard.

**Recommended action:** open the DC compartment and verify that MPPT 1 and
MPPT 2 are fed by separate strings. This is a 10-minute check that resolves the
question definitively.

---

# 4. Finding 3 — Sustained grid overvoltage (High)

## The measurement

Phase voltages exceeded the 253 V limit (230 V nominal +10%) in **690 samples**
between 11:29 and 15:43 IST on 2026-08-02, peaking at **258.2 V**.

| | Range while Normal | Median | Samples > 253 V |
|---|---|---|---|
| inv 1 | 228.9–257.6 V | 243.1 V | 715 / 9,969 (7.2%) |
| inv 2 | 228.2–**258.2 V** | 243.0 V | 780 / 10,623 (7.3%) |
| inv 3 | 225.5–253.9 V | 240.8 V | 19 / 11,025 (0.2%) |

*Counts are per phase-reading; 690 is the count of distinct samples where at
least one phase exceeded the limit.*

## Distribution by hour (IST)

| 11:00 | 12:00 | 13:00 | 14:00 | 15:00 |
|---|---|---|---|---|
| 7 | 123 | 184 | **338** | 38 |

Tightly concentrated in the peak-generation window, with median plant output of
9.54 kW during the excursions.

## Why this matters

This is the classic signature of **voltage rise from PV export**. When a
distributed generator pushes current back through the distribution impedance,
the local voltage rises above the utility's nominal. The correlation with
midday peak output is textbook.

Consequences if left unaddressed:

- **Inverters will eventually trip on overvoltage protection**, losing yield at
  exactly the most productive time of day
- Sustained overvoltage stresses site equipment beyond the inverters
- It may breach the connection agreement with the utility

Note the striking asymmetry: inverters 1 and 2 see it in ~7% of samples,
inverter 3 in 0.2%. Since all three share a grid connection, this points to
**inverters 1 and 2 being electrically further from the point of common
coupling** — longer cable runs, higher impedance, so greater voltage rise for
the same export.

## Likely relationship to the grid trip (Finding 1)

The 13:14 event occurred inside this overvoltage window, and combined elevated
frequency (50.55 Hz) with a plant already running near the voltage ceiling. A
weak or lightly-loaded grid exhibits both symptoms together: exported power has
nowhere to go, so both voltage and frequency rise until protection operates.

Frequency was 50.44–50.55 Hz at the trip while phase voltage happened to be
235–245 V in that specific second, so overvoltage was not the direct trigger.
But both are symptoms of the same underlying condition, and **treating them as
one problem is more likely to be correct than treating them as two.**

## Recommended action

1. Measure the voltage at the point of common coupling and compare with the
   inverter terminals — that difference is the voltage rise across your cabling
2. Check the distribution transformer tap setting with the utility; a tap
   change is often the cheapest fix
3. Verify AC cable sizing to inverters 1 and 2 specifically
4. If those don't resolve it, the inverters support volt-watt or volt-var
   response — but that curtails generation, so it is the last resort, not the
   first

---

# 5. Finding 4 — Inverter 3 thermal (Medium)

Inverter 3's heatsink reached **70 °C**, and spent **336 samples at or above
65 °C** between 11:27 and 14:46 IST on Aug 2.

| | Max heatsink (r27) | Max internal (r28) | r27 > r28 |
|---|---|---|---|
| inv 1 | 50 °C | 58 °C | 0% |
| inv 2 | 52 °C | 55 °C | 0% |
| inv 3 | **70 °C** | 57 °C | **25%** |

The last column is the interesting one. On inverters 1 and 2 the internal
sensor is essentially always the hotter of the two. On inverter 3 the heatsink
overtakes it a quarter of the time — the signature of a heatsink not shedding
heat as fast as it should.

Inverter 3 is the largest unit (27 kW) so higher absolute temperature is
expected. But the *crossover* is not a sizing artefact; it suggests restricted
airflow.

70 °C is below the derating threshold for most inverters and no derating was
observed in the data — output continued climbing to 24.5 kW after the grid
event. So this is not currently costing yield.

**Recommended action:** check inverter 3's ventilation path, cooling fans, and
any air filters at the next site visit. Add a dashboard alert at 75 °C.

---

# 6. Finding 5 — Revised capacity estimates (Low)

The additional afternoon data raised all three peaks substantially. Earlier
estimates were based on partial-day coverage.

| | Earlier estimate | Peak AC observed | Peak DC observed | p99.9 AC |
|---|---|---|---|---|
| inv 1 | 10.3 kW | **13.09 kW** | 13.75 kW | 12.96 kW |
| inv 2 | 15.5 kW | **17.51 kW** | 18.10 kW | 17.32 kW |
| inv 3 | 26.4 kW | **27.14 kW** | 27.99 kW | 26.70 kW |

Inverter 3 barely moved (26.44 → 27.14 kW), which suggests it was already
reaching its ceiling in the earlier data. Inverters 1 and 2 gained 27% and 13%
respectively — they had simply not been observed at peak.

**These are still lower bounds, not nameplate values.** Use them to configure
`RATED_DC_KW` provisionally, but read the three nameplates and correct them.
Several derived metrics depend on this figure: the efficiency validity
threshold, load factor, and specific yield.

---

# 7. Performance summary

## Daily yield

| | Aug 1 (to 19:00) | Aug 2 (to 16:51) |
|---|---|---|
| inv 1 | 36.33 kWh | 40.19 kWh |
| inv 2 | 60.31 kWh | 65.97 kWh |
| inv 3 | 93.32 kWh | 108.99 kWh |
| **Plant** | **189.96 kWh** | **215.15 kWh** |

Aug 2 is a partial figure — collection stopped at 16:51 IST, and the Aug 1 data
shows meaningful generation continuing until about 18:30.

## Specific yield, Aug 2 (partial day)

| | Yield | Rating | kWh/kW |
|---|---|---|---|
| inv 1 | 40.19 kWh | 13.1 kW | **3.07** |
| inv 2 | 65.97 kWh | 17.5 kW | **3.77** |
| inv 3 | 108.99 kWh | 27.1 kW | **4.02** |

Inverter 1 is delivering **24% less energy per kW installed** than inverter 3.
Some of that is the grid-trip downtime and some may be array orientation or
shading — but combined with its string anomaly and lowest efficiency, it
reinforces that inverter 1 is the unit to investigate.

## Conversion efficiency (samples above 20% rated load)

| | n | median | p5 | p95 |
|---|---|---|---|---|
| inv 1 | 2,044 | **95.6%** | 92.7% | 97.8% |
| inv 2 | 2,435 | **97.4%** | 96.3% | 98.4% |
| inv 3 | 2,256 | **96.8%** | 96.1% | 97.8% |

All three are within normal range for string inverters. Inverter 1 trails by
~1.8 points.

## Grid quality

| | Range while Normal | Median | Out of 49.5–50.5 Hz |
|---|---|---|---|
| inv 1 | 49.81–50.53 Hz | 50.01 | 4 / 3,323 |
| inv 2 | 49.81–50.55 Hz | 50.01 | 4 / 3,541 |
| inv 3 | 49.81–50.54 Hz | 50.01 | 4 / 3,675 |

**All 12 out-of-band frequency samples occur inside the 13:14–13:22 grid event
window.** Outside that ten-minute period, frequency was inside tolerance for all
10,527 remaining grid-connected samples.

Phase voltage is a different story — see Finding 3. Imbalance is healthy
throughout at 0.5–1.0% median, but absolute voltage exceeded 253 V in 690
samples during peak export.

## Lifetime counters

| | Total energy | Total runtime |
|---|---|---|
| inv 1 | 59,310 kWh | 10,402 h |
| inv 2 | 81,341 kWh | 13,546 h |
| inv 3 | 74,954 kWh | 13,367 h |

Inverter 1 has 3,000 fewer operating hours than the other two — it is either a
later installation or has had significant downtime historically. Worth
establishing which, since it bears on the anomaly above.

---

# 8. Register map validation

Every identity in `REGISTER_MAP.md` was re-tested against the full 10,648-sample
corpus. All hold.

| Check | Result |
|---|---|
| Per-string power `r6×r7 = r10×10` | median ratio 1.0002–1.0015 on all units |
| Power factor via `√(P²+Q²)` | **0 impossible values** (PF > 1) in 6,724 samples |
| Power factor via `ΣV×I` | **677 impossible values (7.3–14.2%)**, max PF 1.77 |
| `r32 = 60` whenever status = Normal | 10,539 / 10,539 samples |
| `r32 < 60` whenever status ≠ Normal | confirmed, values 0–59 observed |
| Total energy steps | exactly +1 kWh |
| Frame length | 36 registers in 10,648 / 10,648 rows |

The apparent-power finding is worth restating because it is the easiest mistake
to make: **computing apparent power as the sum of per-phase V×I produces
physically impossible power factors above 1.0 in up to 14% of samples.** Use
`√(P² + Q²)` from registers 12 and 13 instead. It never fails.

## Data collection quality

| | Rows | Median interval | Gaps > 2 min |
|---|---|---|---|
| inv 1 | 3,370 | 12 s | 16 |
| inv 2 | 3,579 | 12 s | 22 |
| inv 3 | 3,699 | 13 s | 24 |

Collection is healthy. Remaining gaps are from collector work in progress
rather than bus problems — all retained frames decode cleanly, and there are no
CRC-level failures reaching the database.

Because `persist.py` downsamples on change, the series is unevenly spaced.
**Compute time-series charts by averaging within buckets, never by sampling one
row per bucket.** Daily totals should come from the inverter's own counters
(r25, r21:r22), which are immune to collector downtime.

---

# 9. Recommended actions

## Site

1. **Raise grid voltage rise with the utility.** Measure voltage at the point
   of common coupling versus the inverter terminals, and ask about the
   distribution transformer tap setting. This is the highest-value action: it
   likely underlies both the overvoltage and the 13:14 trip.
2. **Investigate the 13:14–13:26 IST grid event on 2026-08-02** against site
   electrical logs and utility notifications. Treat it as related to (1)
   unless evidence separates them.
3. **Check AC cable sizing to inverters 1 and 2** — they see 40× more
   overvoltage samples than inverter 3 on the same connection.
4. **Open inverter 1's DC compartment** and verify MPPT 1 and MPPT 2 are fed by
   separate strings. Ten-minute check, resolves the anomaly definitively.
5. **Check inverter 3's ventilation** — fans, filters, airflow clearance.
6. **Record all three nameplate ratings** and update `RATED_DC_KW`.
7. **Request the fault code table from EVVO support**, quoting the observed
   values `r1 = 2`, `r1 = 8`, `r4 = 128`.

## Dashboard

8. **Add overvoltage alerting** at 253 V and a daily count of excursions —
   this is the metric to watch while pursuing action (1).
9. **Add frequency-excursion alerting** — any sample outside 49.5–50.5 Hz while
   status = Normal. This would have caught the grid event live.
10. **Add a plant-wide simultaneity alert** — two or more inverters dropping to
    zero output within the same poll cycle is a categorically different event
    from one unit stopping, and should be surfaced differently.
11. **Add a heatsink alert at 75 °C.**
12. **Suppress per-string diagnostics for inverter 1** until the wiring question
    is resolved, or they will generate constant false warnings.
13. **Scale the conversion chart per-unit.** With 13 / 17.5 / 27 kW units on one
    shared axis, inverter 1 will look permanently underperforming.

## Analysis, once more data exists

14. **Capture a full sunrise-to-sunset day with no gaps** to establish a clean
    performance baseline.
15. **Consider a pyranometer.** Performance ratio — the standard metric for
    plant health — needs plane-of-array irradiance, which is not derivable from
    these registers. Without it, degradation over time cannot be separated from
    weather.

---

# 10. Confidence and limitations

**High confidence:** the register map, all decode scalings, the grid event
(four independent lines of evidence), inverter 1's string anomaly (98.4% across
two days and 3,370 samples), the overvoltage measurement itself (690 samples,
clear midday concentration).

**Moderate confidence:** capacity ratings (observed peaks are lower bounds, not
nameplate); inverter 3's thermal issue (real pattern, but 70 °C is not yet
dangerous and the cause is inferred, not observed).

**Low confidence / unresolved:**

- Fault bit meanings — `r1.1`, `r1.3` and `r4.7` are observed but not decoded;
  EVVO's fault table is not public
- `r35` — constant 64 on inverter 1, 0 on the others, purpose unknown
- The r26 EEPROM-commit hypothesis (776 → 768 across a power cycle) is
  inference from a single day boundary, not proven
- Root cause of the grid event — the data shows *what* happened, not *why*
- The link between the overvoltage and the 13:14 trip is a reasoned inference
  from timing and shared symptoms, not a proven causal chain
- Whether the overvoltage originates upstream (utility) or from site cabling
  impedance — distinguishing these requires a measurement at the point of
  common coupling

**Not derivable from this data at all:** performance ratio, degradation rate,
soiling losses, shading analysis. All require either irradiance measurement or
a much longer baseline.
