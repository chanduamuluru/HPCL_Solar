/** Shared formatters for dashboard UI */

export const COLORS = { 1: '#00a0b0', 2: '#2dd4a8', 3: '#8b7cf6' }

export const STATUS_PILL = {
  0: ['Standby', 'pill-warn'],
  1: ['Starting', 'pill-warn'],
  2: ['Normal', 'pill-ok'],
  3: ['Fault', 'pill-bad'],
}

export function fmtKw(w) {
  if (w == null) return '0.00'
  return (Number(w) / 1000).toFixed(Number(w) >= 10000 ? 1 : 2)
}

export function fmtNum(v, d = 1) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toFixed(d)
}

export function fmtIst(iso) {
  if (!iso) return '—'
  return (
    new Date(iso).toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }) + ' IST'
  )
}

export function fmtAge(sec) {
  if (sec == null) return ''
  if (sec < 60) return `${Math.round(sec)}s ago`
  if (sec < 3600) return `${Math.round(sec / 60)}m ago`
  const h = Math.floor(sec / 3600)
  const m = Math.round((sec % 3600) / 60)
  return `${h}h ${m}m ago`
}

export function deltaClass(pct) {
  if (pct == null) return 'flat'
  if (pct > 0.5) return 'up'
  if (pct < -0.5) return 'down'
  return 'flat'
}

export function fmtPct(pct) {
  if (pct == null) return '—'
  return `${pct > 0 ? '+' : ''}${fmtNum(pct, 1)}`
}

export function fmtActiveHours(minutes) {
  if (minutes == null || Number.isNaN(Number(minutes))) return '—'
  const m = Math.max(0, Math.round(Number(minutes)))
  const h = Math.floor(m / 60)
  const rem = m % 60
  if (h <= 0) return `${rem}m`
  return `${h}h ${String(rem).padStart(2, '0')}m`
}

export function fmtChartDate(isoOrDay) {
  if (!isoOrDay) return '—'
  if (/^\d{4}-\d{2}-\d{2}$/.test(isoOrDay)) {
    const [y, m, d] = isoOrDay.split('-').map(Number)
    const dt = new Date(Date.UTC(y, m - 1, d, 12))
    return dt.toLocaleDateString('en-IN', {
      timeZone: 'Asia/Kolkata',
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    })
  }
  return new Date(isoOrDay).toLocaleDateString('en-IN', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

export function labelTime(iso) {
  return new Date(iso).toLocaleTimeString('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

export function istMinutesOfDay(iso) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(new Date(iso))
  const h = Number(parts.find((p) => p.type === 'hour').value)
  const m = Number(parts.find((p) => p.type === 'minute').value)
  return h * 60 + m
}

export function fullDaySlotLabels(stepMin = 15) {
  const labels = []
  for (let m = 0; m < 24 * 60; m += stepMin) {
    const hh = String(Math.floor(m / 60)).padStart(2, '0')
    const mm = String(m % 60).padStart(2, '0')
    labels.push(`${hh}:${mm}`)
  }
  return labels
}

export function buildReportRows(apiRows) {
  const byDate = {}
  for (const r of apiRows || []) {
    const d = r.reading_date
    if (!byDate[d]) {
      byDate[d] = {
        reading_date: d,
        inv1_kwh: null,
        inv2_kwh: null,
        inv3_kwh: null,
        peak_ac_w: 0,
        sample_count: 0,
        rated_dc_w: 0,
      }
    }
    const key = `inv${r.inverter_id}_kwh`
    if (key in byDate[d]) byDate[d][key] = r.max_today_energy_kwh
    byDate[d].peak_ac_w += Number(r.max_ac_power_w || 0)
    byDate[d].sample_count += Number(r.sample_count || 0)
    byDate[d].rated_dc_w += Number(r.rated_dc_w || 0)
  }
  return Object.values(byDate)
    .map((r) => {
      const total =
        Number(r.inv1_kwh || 0) + Number(r.inv2_kwh || 0) + Number(r.inv3_kwh || 0)
      const sy = r.rated_dc_w > 0 ? (total * 1000.0) / r.rated_dc_w : null
      return {
        ...r,
        total_kwh: Math.round(total * 100) / 100,
        specific_yield_kwh_per_kw: sy != null ? Math.round(sy * 1000) / 1000 : null,
      }
    })
    .sort((a, b) => String(b.reading_date).localeCompare(String(a.reading_date)))
}

export function downloadCsv(filename, lines) {
  const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
}
