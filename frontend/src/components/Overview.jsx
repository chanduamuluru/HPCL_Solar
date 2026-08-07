import InverterCard from './InverterCard'
import { PowerChart } from './Charts'
import {
  deltaClass,
  fmtAge,
  fmtIst,
  fmtKw,
  fmtNum,
  fmtPct,
} from '../lib/format'

function KpiDetail({ label, rows, accent }) {
  return (
    <article className={`kpi-card kpi-detail${accent === 'green' ? ' accent-green' : ''}`}>
      <p className="kpi-label">{label}</p>
      <div className="kpi-detail-rows">
        {rows.map(({ key, value, delta, emphasize }) => (
          <div
            className={`kpi-detail-row${delta != null ? ' is-delta' : ''}${emphasize ? ' is-emphasize' : ''}`}
            key={key}
          >
            <span>{key}</span>
            <b className={delta != null ? deltaClass(delta) : undefined}>{value}</b>
          </div>
        ))}
      </div>
    </article>
  )
}

export default function Overview({
  latest,
  compare,
  weather,
  seriesPoints,
  chartMode,
  chartCaption,
  theme,
  onChartMode,
}) {
  const p = latest?.plant || {}
  const stale = !!p.is_stale
  const displayAc = stale ? (p.last_ac_power_w ?? p.ac_power_w) : p.ac_power_w
  const displayDc = stale ? (p.last_dc_power_w ?? p.dc_power_w) : p.dc_power_w
  const tE = compare?.today?.live_today_energy_kwh ?? compare?.today?.today_energy_kwh ?? p.today_energy_kwh
  const yE = compare?.yesterday?.today_energy_kwh
  const vs = compare?.delta?.energy_pct
  const cmap = Object.fromEntries(
    (compare?.inverters || []).map((c) => [c.inverter_id, c]),
  )

  const peakT = compare?.today?.max_ac_power_w
  const peakY = compare?.yesterday?.max_ac_power_w
  const peakPct =
    peakT != null && peakY ? (100 * (peakT - peakY)) / peakY : null

  const syT = compare?.today?.specific_yield_kwh_per_kw ?? p.specific_yield_kwh_per_kw
  const syY = compare?.yesterday?.specific_yield_kwh_per_kw
  const syPct = compare?.delta?.specific_yield_pct
  const yieldUp = vs != null && vs > 0.5

  return (
    <section className="tab-panel active">
      <div className="kpi-row">
        <article className={`kpi-hero${yieldUp ? ' accent-green' : ''}${stale ? ' is-stale' : ''}`}>
          <div className="kpi-hero-top">
            <p className="kpi-label">Today yield</p>
          </div>
          <p className="kpi-hero-val">
            <span>{fmtNum(tE, 2)}</span> <span className="u">kWh</span>
          </p>
          <div className="kpi-detail-rows kpi-hero-detail">
            <div className="kpi-detail-row">
              <span>Yesterday</span>
              <b>{fmtNum(yE, 2)} kWh</b>
            </div>
            <div className="kpi-detail-row is-delta">
              <span>Delta %</span>
              <b className={deltaClass(vs)}>
                {vs == null ? '—' : `${fmtPct(vs)}%`}
              </b>
            </div>
          </div>
          <div className="kpi-weather" aria-live="polite">
            <div className="wx-main">
              <p className="kpi-label">Site weather</p>
              <p className="wx-line">
                <span className="wx-temp">
                  <span>{weather?.ok ? fmtNum(weather.temperature_c, 1) : '—'}</span>
                  <span className="u">°C</span>
                </span>
                <span className="wx-cond">
                  {weather?.ok ? weather.condition || '—' : 'Weather unavailable'}
                </span>
              </p>
            </div>
            <div className="wx-grid">
              <div>
                <label>Humidity</label>
                <b>
                  {weather?.humidity_pct == null
                    ? '—'
                    : `${fmtNum(weather.humidity_pct, 0)}%`}
                </b>
              </div>
              <div>
                <label>Clouds</label>
                <b>
                  {weather?.cloud_cover_pct == null
                    ? '—'
                    : `${fmtNum(weather.cloud_cover_pct, 0)}%`}
                </b>
              </div>
              <div>
                <label>Wind</label>
                <b>
                  {weather?.wind_speed_kmh == null
                    ? '—'
                    : `${fmtNum(weather.wind_speed_kmh, 0)} km/h`}
                </b>
              </div>
              <div>
                <label>GHI</label>
                <b>
                  {weather?.ghi_wm2 == null
                    ? '—'
                    : `${fmtNum(weather.ghi_wm2, 0)} W/m²`}
                </b>
              </div>
            </div>
          </div>
        </article>

        <div className="kpi-side">
          <div className="kpi-side-row">
            <article className={`kpi-card kpi-ac${stale ? ' is-stale' : ''}`}>
              <div className="kpi-hero-top">
                <p className="kpi-label">Current AC</p>
                <span className="bolt">⚡</span>
              </div>
              <p className="kpi-val">
                <span>{fmtKw(displayAc)}</span> <span className="u">kW</span>
              </p>
              <p className="kpi-ac-ghi">
                GHI{' '}
                <b>
                  {weather?.ghi_wm2 != null
                    ? fmtNum(weather.ghi_wm2, 0)
                    : p.ghi_wm2 != null
                      ? fmtNum(p.ghi_wm2, 0)
                      : '—'}
                </b>{' '}
                <span className="u">W/m²</span>
              </p>
              <p className={`kpi-ac-meta${stale ? ' is-stale' : ''}`}>
                {stale ? 'Last sample' : 'Live'}
                {' · '}
                {fmtAge(p.data_age_sec) || fmtIst(p.as_of)}
              </p>
            </article>

            <KpiDetail
              label="Peak AC"
              rows={[
                { key: 'Today', value: `${fmtKw(peakT)} kW` },
                { key: 'Yesterday', value: `${fmtKw(peakY)} kW` },
                {
                  key: 'Delta %',
                  value: peakPct == null ? '—' : `${fmtPct(peakPct)}%`,
                  delta: peakPct,
                },
              ]}
            />

            <KpiDetail
              label="Specific yield"
              rows={[
                { key: 'Today', value: fmtNum(syT, 3) },
                { key: 'Yesterday', value: fmtNum(syY, 3) },
                {
                  key: 'Delta %',
                  value: syPct == null ? '—' : `${fmtPct(syPct)}%`,
                  delta: syPct,
                },
              ]}
            />
          </div>

          <div className="kpi-side-row">
            <article className="kpi-card">
              <p className="kpi-label">Total energy</p>
              <p className="kpi-val">
                <span>{fmtNum((p.total_energy_kwh || 0) / 1000, 1)}</span>{' '}
                <span className="u">MWh</span>
              </p>
            </article>

            <article className="kpi-card">
              <p className="kpi-label">Current DC</p>
              <p className="kpi-val">
                <span>{fmtKw(displayDc)}</span> <span className="u">kW</span>
              </p>
            </article>

            <article className="kpi-card">
              <p className="kpi-label">Inverters</p>
              <p className="kpi-val">
                <span>{p.inverter_count ?? '—'}</span> <span className="u">Units</span>
              </p>
            </article>
          </div>
        </div>
      </div>

      <div className="panel chart-panel">
        <div className="panel-head row-between">
          <div>
            <h2>Live power (kW)</h2>
            <p className="muted">{chartCaption || '—'}</p>
          </div>
          <label className="window-ctrl">
            Chart
            <select value={chartMode} onChange={(e) => onChartMode(e.target.value)}>
              <option value="6">6 h</option>
              <option value="12">12 h</option>
              <option value="24">24 h</option>
              <option value="day">Full day</option>
            </select>
          </label>
        </div>
        <PowerChart points={seriesPoints} theme={theme} />
      </div>

      <div className="inv-section">
        <div className="section-head">
          <h2>Inverter status</h2>
        </div>
        <div className="inv-grid">
          {(latest?.inverters || []).map((r) => (
            <InverterCard key={r.inverter_id} row={r} compare={cmap[r.inverter_id]} />
          ))}
        </div>
      </div>
    </section>
  )
}
