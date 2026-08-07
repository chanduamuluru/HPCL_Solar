import {
  fmtActiveHours,
  fmtChartDate,
  fmtKw,
  fmtNum,
} from '../lib/format'

function HistCard({ r }) {
  return (
    <article className="hist-card" data-id={r.inverter_id}>
      <div className="hist-card-h">
        <h3 className="inv-title">
          <span className="dot" />
          Inverter {r.inverter_id}
        </h3>
        <span className="hist-energy">
          {fmtNum(r.max_today_energy_kwh, 2)} <span className="u">kWh</span>
        </span>
      </div>
      <div className="hist-metrics">
        {[
          ['Peak AC', `${fmtKw(r.max_ac_power_w)} kW`],
          ['Peak DC', `${fmtKw(r.max_dc_power_w)} kW`],
          ['Yield', fmtNum(r.specific_yield_kwh_per_kw, 3)],
          ['Active', fmtActiveHours(r.max_grid_minutes)],
          [
            'η min–max',
            `${fmtNum(r.min_efficiency_pct, 1)}–${fmtNum(r.max_efficiency_pct, 1)}%`,
          ],
          ['Samples', r.sample_count ?? '—'],
          ['OV count', r.overvoltage_count ?? '—'],
          ['Faults', r.fault_sample_count ?? '—'],
          [
            'Sink °C',
            `${fmtNum(r.min_heatsink_temp_c, 0)}–${fmtNum(r.max_heatsink_temp_c, 0)}`,
          ],
          ['Internal °C', fmtNum(r.max_internal_temp_c, 0)],
          [
            'Freq Hz',
            `${fmtNum(r.min_grid_frequency_hz, 2)}–${fmtNum(r.max_grid_frequency_hz, 2)}`,
          ],
          [
            'Phase V',
            `${fmtNum(r.min_phase_voltage_v, 1)}–${fmtNum(r.max_phase_voltage_v, 1)}`,
          ],
        ].map(([label, value]) => (
          <div key={label}>
            <label>{label}</label>
            <b>{value}</b>
          </div>
        ))}
      </div>
      <div className="inv-pv hist-pv">
        <div className="inv-pv-row">
          <span className="inv-pv-tag">PV1</span>
          <span>
            {fmtNum(r.min_pv1_voltage_v, 1)}–{fmtNum(r.max_pv1_voltage_v, 1)} V
          </span>
          <span>max {fmtNum(r.max_pv1_current_a, 2)} A</span>
          <span>{fmtKw(r.max_pv1_power_w)} kW</span>
        </div>
        <div className="inv-pv-row">
          <span className="inv-pv-tag">PV2</span>
          <span>
            {fmtNum(r.min_pv2_voltage_v, 1)}–{fmtNum(r.max_pv2_voltage_v, 1)} V
          </span>
          <span>max {fmtNum(r.max_pv2_current_a, 2)} A</span>
          <span>{fmtKw(r.max_pv2_power_w)} kW</span>
        </div>
      </div>
      <div className="hist-foot">
        <span>DC bus max {fmtNum(r.max_dc_bus_voltage_v, 1)} V</span>
        <span>Rated {fmtKw(r.rated_dc_w)} kW</span>
        <span>Match {fmtNum(r.string_voltage_match_pct, 1)}%</span>
      </div>
    </article>
  )
}

export default function History({ rows, days, onDays }) {
  const byDate = {}
  for (const r of rows || []) {
    const d = r.reading_date
    if (!byDate[d]) byDate[d] = []
    byDate[d].push(r)
  }
  const dates = Object.keys(byDate).sort((a, b) => String(b).localeCompare(String(a)))

  return (
    <section className="tab-panel active">
      <div className="panel-head row-between">
        <div>
          <h2>History</h2>
          <p className="muted">Date-wise inverter performance from daily stats</p>
        </div>
        <label className="window-ctrl">
          Days
          <select value={String(days)} onChange={(e) => onDays(Number(e.target.value))}>
            <option value="7">7</option>
            <option value="14">14</option>
            <option value="30">30</option>
          </select>
        </label>
      </div>
      <div className="history-days">
        {!dates.length ? (
          <div className="empty-state">No daily history yet. Run aggregate if needed.</div>
        ) : (
          dates.map((d) => {
            const invs = byDate[d].sort((a, b) => a.inverter_id - b.inverter_id)
            const total = invs.reduce(
              (s, r) => s + Number(r.max_today_energy_kwh || 0),
              0,
            )
            return (
              <section className="hist-day" key={d}>
                <div className="hist-day-h">
                  <h3>{fmtChartDate(d)}</h3>
                  <p className="muted">
                    {d} · plant {fmtNum(total, 2)} kWh · {invs.length} inverters
                  </p>
                </div>
                <div className="hist-grid">
                  {invs.map((r) => (
                    <HistCard key={r.inverter_id} r={r} />
                  ))}
                </div>
              </section>
            )
          })
        )}
      </div>
    </section>
  )
}
