import {
  STATUS_PILL,
  deltaClass,
  fmtActiveHours,
  fmtAge,
  fmtKw,
  fmtNum,
  fmtPct,
} from '../lib/format'

function StatusPill({ code, text, tip }) {
  const [label, cls] = STATUS_PILL[code] || [text || 'Unknown', 'pill-muted']
  return (
    <span className={`pill ${cls}`} data-tip={tip} title={tip}>
      {label}
    </span>
  )
}

function Metric({ label, tip, children }) {
  return (
    <div className="metric-tip" data-tip={tip} title={tip}>
      <label>{label}</label>
      <b>{children}</b>
    </div>
  )
}

function Tip({ tip, children, className = '' }) {
  return (
    <span className={`metric-tip ${className}`.trim()} data-tip={tip} title={tip}>
      {children}
    </span>
  )
}

export default function InverterCard({ row, compare }) {
  const stale = row.is_stale
  const dPct = compare?.delta_pct
  const dCls = deltaClass(dPct)
  const peakW = compare?.today_peak_ac_w
  const acW = stale ? (row.last_ac_power_w ?? row.ac_power_w) : row.ac_power_w
  const dcW = stale ? (row.last_dc_power_w ?? row.dc_power_w) : row.dc_power_w
  const ageSec = row.data_age_sec
  const ageLive = !stale && ageSec != null && ageSec < 120
  const ageLabel = ageLive ? 'live' : fmtAge(ageSec) || '—'

  return (
    <article className={`inv-card${stale ? ' is-stale' : ''}`} data-id={row.inverter_id}>
      <div className="inv-h">
        <h3
          className="inv-title metric-tip"
          data-tip={`EVVO inverter unit #${row.inverter_id} at Plant #402`}
          title={`EVVO inverter unit #${row.inverter_id} at Plant #402`}
        >
          <span className="dot" />
          Inverter {row.inverter_id}
        </h3>
        <div className="inv-status">
          <div className="inv-status-row">
            <span
              className="inv-status-label metric-tip"
              data-tip="Operating state from the last sample (Standby / Starting / Normal / Fault)"
              title="Operating state from the last sample (Standby / Starting / Normal / Fault)"
            >
              Last status
            </span>
            <StatusPill
              code={row.status_code}
              text={row.status_text}
              tip="Inverter status code from Modbus register map"
            />
          </div>
          <p
            className={`inv-age metric-tip${ageLive ? ' is-live' : ''}`}
            data-tip={
              ageLive
                ? 'Fresh data received within the last 2 minutes'
                : 'Time since the last sample was received from this inverter'
            }
            title={
              ageLive
                ? 'Fresh data received within the last 2 minutes'
                : 'Time since the last sample was received from this inverter'
            }
          >
            {ageLabel}
          </p>
        </div>
      </div>

      <div className="inv-hero">
        <p
          className="inv-power metric-tip"
          data-tip="Instantaneous AC output power from the latest sample. Age is shown above when the feed is behind."
          title="Instantaneous AC output power from the latest sample. Age is shown above when the feed is behind."
        >
          {fmtKw(acW)}
          <span className="u">kW AC</span>
        </p>
        <p
          className="inv-dc metric-tip"
          data-tip={
            stale
              ? 'DC input from the latest sample (feed not fresh). Age shown in the header.'
              : 'Instantaneous DC input power from the PV arrays into the inverter.'
          }
          title={
            stale
              ? 'DC input from the latest sample (feed not fresh). Age shown in the header.'
              : 'Instantaneous DC input power from the PV arrays into the inverter.'
          }
        >
          DC {fmtKw(dcW)} kW
          {stale ? ' · not fresh' : ''}
        </p>
      </div>

      <div className="inv-energy">
        <Metric
          label="Today"
          tip="Energy generated today (Asia/Kolkata calendar day), from the inverter today-energy register."
        >
          {fmtNum(row.today_energy_kwh, 2)} <span className="u">kWh</span>
        </Metric>
        <Metric
          label="Yday"
          tip="Energy generated yesterday for this inverter (from daily stats)."
        >
          {compare ? fmtNum(compare.yesterday_energy_kwh, 2) : '—'}{' '}
          <span className="u">kWh</span>
        </Metric>
        <Metric
          label="Δ energy"
          tip="Percent change in today’s energy vs yesterday: (today − yesterday) / yesterday × 100."
        >
          <span className={`trend ${dCls}`}>{fmtPct(dPct)}%</span>
        </Metric>
        <Metric
          label="Peak today"
          tip="Highest AC power recorded for this inverter today (daily peak)."
        >
          {peakW != null ? fmtKw(peakW) : '—'} <span className="u">kW</span>
        </Metric>
      </div>

      <div className="inv-metrics">
        <Metric
          label="Active"
          tip="Time the inverter has been grid-connected today (from today grid-minutes register)."
        >
          {fmtActiveHours(row.today_grid_minutes)}
        </Metric>
        <Metric
          label="Load"
          tip="Load factor: current AC output as a percentage of rated DC capacity."
        >
          {fmtNum(row.load_factor_pct, 1)}%
        </Metric>
        <Metric
          label="PF"
          tip="Power factor (AC active vs apparent power)."
        >
          {fmtNum(row.power_factor, 3)}
        </Metric>
        <Metric
          label="Yield"
          tip="Specific yield today: kWh produced per kW of rated DC capacity (fair comparison across inverter sizes)."
        >
          {fmtNum(row.specific_yield_kwh_per_kw, 3)}
        </Metric>
        <Metric
          label="Freq"
          tip="Grid frequency at the inverter AC terminals (Hz). Nominal is ~50 Hz in India."
        >
          {fmtNum(row.grid_frequency_hz, 2)} <span className="u">Hz</span>
        </Metric>
        <Metric
          label="Sink °C"
          tip="Heatsink temperature (°C). Rising values indicate thermal stress under load."
        >
          {fmtNum(row.heatsink_temp_c, 1)}
        </Metric>
      </div>

      <div className="inv-pv">
        <div className="inv-pv-row">
          <Tip tip="PV1 / MPPT 1 string measurements">
            <span className="inv-pv-tag">PV1</span>
          </Tip>
          <Tip tip="PV1 DC string voltage">{fmtNum(row.pv1_voltage_v, 1)} V</Tip>
          <Tip tip="PV1 DC string current">{fmtNum(row.pv1_current_a, 2)} A</Tip>
          <Tip tip="PV1 DC string power">{fmtKw(row.pv1_power_w)} kW</Tip>
        </div>
        <div className="inv-pv-row">
          <Tip tip="PV2 / MPPT 2 string measurements">
            <span className="inv-pv-tag">PV2</span>
          </Tip>
          <Tip tip="PV2 DC string voltage">{fmtNum(row.pv2_voltage_v, 1)} V</Tip>
          <Tip tip="PV2 DC string current">{fmtNum(row.pv2_current_a, 2)} A</Tip>
          <Tip tip="PV2 DC string power">{fmtKw(row.pv2_power_w)} kW</Tip>
        </div>
      </div>

      <div className="inv-grid-v">
        <Tip tip="Phase R (Red) AC line voltage">
          R {fmtNum(row.ac_r_voltage_v, 1)} V
        </Tip>
        <Tip tip="Phase Y (Yellow) AC line voltage">
          Y {fmtNum(row.ac_y_voltage_v, 1)} V
        </Tip>
        <Tip tip="Phase B (Blue) AC line voltage">
          B {fmtNum(row.ac_b_voltage_v, 1)} V
        </Tip>
        <Tip
          tip="Lifetime energy total from the inverter energy counter (MWh)."
          className="muted-inline"
        >
          Total energy {fmtNum((row.total_energy_kwh || 0) / 1000, 1)} MWh
        </Tip>
      </div>
    </article>
  )
}
