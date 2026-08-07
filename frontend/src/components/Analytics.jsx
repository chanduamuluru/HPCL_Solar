import { AnalyticsChart } from './Charts'
import {
  downloadCsv,
  fmtKw,
  fmtNum,
  fmtPct,
} from '../lib/format'

export default function Analytics({
  data,
  dailyRows,
  range,
  theme,
  onRange,
  onExport,
}) {
  if (!data) {
    return (
      <section className="tab-panel active">
        <p className="muted">Loading analytics…</p>
      </section>
    )
  }

  if (!data.available) {
    return (
      <section className="tab-panel active">
        <div className="panel-head row-between">
          <div>
            <h2>Analytics comparison</h2>
            <p className="muted">Yesterday has data · week / month need more history</p>
          </div>
          <div className="range-bar">
            {['yesterday', 'week', 'month'].map((r) => (
              <button
                key={r}
                type="button"
                className={`range-btn${range === r ? ' active' : ''}`}
                onClick={() => onRange(r)}
              >
                {r === 'yesterday' ? 'Yesterday' : r === 'week' ? 'Weekly' : 'Month'}
              </button>
            ))}
          </div>
        </div>
        <div className="empty-state">{data.message || 'No data for this range yet.'}</div>
      </section>
    )
  }

  const cmp = data.compare
  const tE = cmp?.today?.live_today_energy_kwh ?? cmp?.today?.today_energy_kwh
  const cards = [
    {
      title: 'Total plant',
      rows: [
        ['Today', `${fmtNum(tE, 2)} kWh`],
        ['Yesterday', `${fmtNum(cmp?.yesterday?.today_energy_kwh, 2)} kWh`],
        ['Energy Δ %', `${fmtPct(cmp?.delta?.energy_pct)}%`],
      ],
    },
    ...(cmp?.inverters || []).map((inv) => ({
      title: `Inverter ${inv.inverter_id}`,
      id: inv.inverter_id,
      rows: [
        ['Today', `${fmtNum(inv.today_energy_kwh, 2)} kWh`],
        ['Yesterday', `${fmtNum(inv.yesterday_energy_kwh, 2)} kWh`],
        ['Delta %', `${fmtPct(inv.delta_pct)}%`],
        ['Peak today', `${fmtKw(inv.today_peak_ac_w)} kW`],
      ],
    })),
  ]

  return (
    <section className="tab-panel active">
      <div className="panel-head row-between">
        <div>
          <h2>Analytics comparison</h2>
          <p className="muted">Yesterday has data · week / month need more history</p>
        </div>
        <div className="range-bar">
          {['yesterday', 'week', 'month'].map((r) => (
            <button
              key={r}
              type="button"
              className={`range-btn${range === r ? ' active' : ''}`}
              onClick={() => onRange(r)}
            >
              {r === 'yesterday' ? 'Yesterday' : r === 'week' ? 'Weekly' : 'Month'}
            </button>
          ))}
        </div>
      </div>

      <div className="analytics-kpis">
        {cards.map((c) => (
          <div className="cmp-card" data-id={c.id || ''} key={c.title}>
            <h3>
              {c.id ? <span className="dot" /> : '⚡ '}
              {c.title}
            </h3>
            {c.rows.map(([k, v]) => (
              <div className="cmp-row" key={k}>
                <span>{k}</span>
                <b>{v}</b>
              </div>
            ))}
          </div>
        ))}
      </div>

      <div className="panel chart-panel">
        <div className="panel-head">
          <h2>Today vs yesterday (kW)</h2>
          <p className="muted">
            Full day · 00:00–24:00 IST · solid = today, dashed = yesterday
          </p>
        </div>
        <AnalyticsChart
          seriesYday={data.series || []}
          seriesToday={data.series_today || []}
          stepMin={data.bucket_minutes || 15}
          theme={theme}
        />
      </div>

      <div className="panel">
        <div className="panel-head row-between">
          <h2>Detailed performance log</h2>
          <button type="button" className="link-btn" onClick={onExport}>
            Export CSV
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Inv</th>
                <th>Today kWh</th>
                <th>Peak AC</th>
                <th>Yield</th>
                <th>η min–max</th>
                <th>String</th>
                <th>OV count</th>
                <th>Samples</th>
              </tr>
            </thead>
            <tbody>
              {(dailyRows || []).map((r) => {
                const match = Number(r.string_voltage_match_pct || 0)
                const invId = r.inverter_id
                return (
                  <tr
                    key={`${r.reading_date}-${invId}`}
                    className={`inv-row inv-row-${invId}`}
                    data-inv={invId}
                  >
                    <td>{r.reading_date}</td>
                    <td>
                      <span className={`inv-badge inv-badge-${invId}`}>Inv {invId}</span>
                    </td>
                    <td>{fmtNum(r.max_today_energy_kwh, 2)}</td>
                    <td>{fmtKw(r.max_ac_power_w)} kW</td>
                    <td>{fmtNum(r.specific_yield_kwh_per_kw, 3)}</td>
                    <td>
                      {fmtNum(r.min_efficiency_pct, 1)}–{fmtNum(r.max_efficiency_pct, 1)}%
                    </td>
                    <td className={match > 50 ? 'alert' : 'ok'}>{fmtNum(match, 1)}%</td>
                    <td>{r.overvoltage_count ?? '—'}</td>
                    <td>{r.sample_count ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

export function exportAnalyticsCsv(rows) {
  if (!rows?.length) return
  const cols = [
    'reading_date',
    'inverter_id',
    'max_today_energy_kwh',
    'max_ac_power_w',
    'specific_yield_kwh_per_kw',
    'string_voltage_match_pct',
    'overvoltage_count',
    'sample_count',
  ]
  const lines = [cols.join(',')].concat(
    rows.map((r) => cols.map((c) => r[c] ?? '').join(',')),
  )
  downloadCsv('HPCL Solar_daily.csv', lines)
}
