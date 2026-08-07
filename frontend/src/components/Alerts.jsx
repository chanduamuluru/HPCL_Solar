import { useMemo } from 'react'
import { fmtChartDate, fmtNum } from '../lib/format'

const HEAT_ALERT_C = 75
const STRING_MATCH_ANOMALY_PCT = 50

function istToday() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
}

function dayLabel(dateKey, todayKey) {
  if (dateKey === todayKey) return `Today · ${fmtChartDate(dateKey)}`
  const [y, m, d] = String(todayKey).split('-').map(Number)
  const yday = new Date(Date.UTC(y, m - 1, d))
  yday.setUTCDate(yday.getUTCDate() - 1)
  const ydayKey = yday.toISOString().slice(0, 10)
  if (dateKey === ydayKey) return `Yesterday · ${fmtChartDate(dateKey)}`
  return fmtChartDate(dateKey)
}

/** Build day-level alerts from inverter_daily_stats rows. */
export function alertsFromDaily(rows) {
  const out = []
  for (const r of rows || []) {
    const d = r.reading_date
    const inv = r.inverter_id
    if (!d || inv == null) continue

    const ov = Number(r.overvoltage_count || 0)
    if (ov > 0) {
      out.push({
        day: d,
        level: ov >= 50 ? 'high' : 'medium',
        code: 'overvoltage',
        inverter_id: inv,
        message: `Inv ${inv}: ${ov} overvoltage sample${ov === 1 ? '' : 's'} (>253 V)`,
      })
    }

    const faults = Number(r.fault_sample_count || 0)
    if (faults > 0) {
      out.push({
        day: d,
        level: 'high',
        code: 'fault',
        inverter_id: inv,
        message: `Inv ${inv}: ${faults} fault / protection sample${faults === 1 ? '' : 's'}`,
      })
    }

    const match = Number(r.string_voltage_match_pct || 0)
    if (inv === 1 && match > STRING_MATCH_ANOMALY_PCT) {
      out.push({
        day: d,
        level: 'medium',
        code: 'string_anomaly',
        inverter_id: 1,
        message: `Inv 1: PV1/PV2 matched ${fmtNum(match, 1)}% of samples — string diagnostics unreliable`,
      })
    }

    const hs = r.max_heatsink_temp_c
    if (hs != null && Number(hs) >= HEAT_ALERT_C) {
      out.push({
        day: d,
        level: 'medium',
        code: 'heatsink',
        inverter_id: inv,
        message: `Inv ${inv}: heatsink peaked at ${fmtNum(hs, 1)} °C (alert ≥ ${HEAT_ALERT_C})`,
      })
    }
  }
  return out
}

function groupAlertsByDay(liveAlerts, dailyRows, todayKey) {
  const map = new Map()

  const ensure = (day) => {
    if (!map.has(day)) map.set(day, [])
    return map.get(day)
  }

  for (const a of liveAlerts || []) {
    ensure(todayKey).push({ ...a, day: todayKey, source: 'live' })
  }

  for (const a of alertsFromDaily(dailyRows)) {
    // Avoid duplicating live string/fault noise for today when live already covers it
    if (a.day === todayKey) {
      const live = map.get(todayKey) || []
      const dup = live.some(
        (x) => x.code === a.code && (x.inverter_id ?? null) === (a.inverter_id ?? null),
      )
      if (dup) continue
    }
    ensure(a.day).push({ ...a, source: 'daily' })
  }

  return [...map.entries()]
    .sort((a, b) => String(b[0]).localeCompare(String(a[0])))
    .map(([day, items]) => ({
      day,
      label: dayLabel(day, todayKey),
      count: items.length,
      alerts: items.sort((x, y) => {
        const rank = { high: 0, medium: 1, low: 2 }
        return (rank[x.level] ?? 9) - (rank[y.level] ?? 9)
      }),
    }))
}

export default function Alerts({ alerts, dailyRows, todayDate }) {
  const todayKey = todayDate || istToday()
  const groups = useMemo(
    () => groupAlertsByDay(alerts, dailyRows, todayKey),
    [alerts, dailyRows, todayKey],
  )
  const total = groups.reduce((n, g) => n + g.count, 0)

  return (
    <section className="tab-panel active">
      <div className="panel">
        <div className="panel-head row-between">
          <div>
            <h2>Alerts</h2>
            <p className="muted">
              Day-wise · string anomaly, stale feed, faults, overvoltage, heatsink
            </p>
          </div>
          <p className="muted">{total ? `${total} alert${total === 1 ? '' : 's'}` : 'No alerts'}</p>
        </div>

        {!groups.length ? (
          <p className="muted">No alerts in the selected period</p>
        ) : (
          <div className="alerts-by-day">
            {groups.map((g) => (
              <section className="alerts-day" key={g.day}>
                <header className="alerts-day-h">
                  <h3>{g.label}</h3>
                  <span className="alerts-day-count">{g.count}</span>
                </header>
                <div className="alerts-list">
                  {g.alerts.map((a, i) => (
                    <div
                      className={`alert-row ${a.level || 'medium'}`}
                      key={`${g.day}-${a.code}-${a.inverter_id ?? 'p'}-${a.source}-${i}`}
                    >
                      <div className="alert-row-main">
                        <strong>{(a.code || 'alert').replace(/_/g, ' ')}</strong>
                        <span className="alert-msg"> — {a.message}</span>
                      </div>
                      {a.source === 'live' && (
                        <span className="alert-tag">Active</span>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </section>
  )
}
