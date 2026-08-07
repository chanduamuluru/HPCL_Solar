import { useEffect, useRef } from 'react'
import Chart from 'chart.js/auto'
import {
  COLORS,
  fullDaySlotLabels,
  istMinutesOfDay,
  labelTime,
} from '../lib/format'

function applyThemeDefaults() {
  const lite = document.documentElement.getAttribute('data-theme') === 'lite'
  Chart.defaults.color = lite ? '#6b7280' : '#8b9bb4'
  Chart.defaults.borderColor = lite
    ? 'rgba(28,35,48,0.08)'
    : 'rgba(148,163,184,0.12)'
  Chart.defaults.font.family = "'DM Sans', sans-serif"
}

function fmtKwValue(v) {
  if (v == null || Number.isNaN(v)) return '—'
  return `${Number(v).toLocaleString('en-IN', {
    maximumFractionDigits: 3,
    minimumFractionDigits: 0,
  })} kW`
}

function fmtGhiValue(v) {
  if (v == null || Number.isNaN(v)) return '—'
  return `${Number(v).toLocaleString('en-IN', { maximumFractionDigits: 0 })} W/m²`
}

/** HTML tooltip outside the canvas so it is never clipped by chart edges. */
function externalTooltip(tipEl) {
  return (context) => {
    const { chart, tooltip } = context
    if (!tipEl) return

    if (tooltip.opacity === 0) {
      tipEl.style.opacity = '0'
      tipEl.style.pointerEvents = 'none'
      return
    }

    const title = tooltip.title?.[0] || ''
    const lines = (tooltip.dataPoints || [])
      .map((dp) => {
        const label = dp.dataset.label || ''
        const dashed = /\(yday\)/i.test(label) || /GHI/i.test(label)
        const color = dp.dataset.borderColor || '#94a3b8'
        const isGhi = /GHI/i.test(label) || dp.dataset.yAxisID === 'yGhi'
        const value = isGhi ? fmtGhiValue(dp.parsed?.y) : fmtKwValue(dp.parsed?.y)
        return `<div class="chart-tip-row">
          <span class="chart-tip-swatch${dashed ? ' is-dash' : ''}" style="--sw:${color}"></span>
          <span>${label}: ${value}</span>
        </div>`
      })
      .join('')

    tipEl.innerHTML = `<div class="chart-tip-title">${title}</div>${lines}`
    tipEl.style.opacity = '1'
    tipEl.style.pointerEvents = 'none'

    const { offsetLeft: posX, offsetTop: posY } = chart.canvas
    const caretX = tooltip.caretX
    const caretY = tooltip.caretY
    const wrap = tipEl.parentElement
    const wrapW = wrap?.clientWidth || chart.width
    const tipW = tipEl.offsetWidth
    const tipH = tipEl.offsetHeight

    let left = posX + caretX + 12
    let top = posY + caretY - tipH / 2

    if (left + tipW > wrapW - 8) left = posX + caretX - tipW - 12
    if (left < 8) left = 8
    if (top < 8) top = 8
    if (wrap && top + tipH > wrap.clientHeight - 8) {
      top = Math.max(8, wrap.clientHeight - tipH - 8)
    }

    tipEl.style.left = `${left}px`
    tipEl.style.top = `${top}px`
  }
}

const chartPlugins = {
  legend: { labels: { boxWidth: 12, usePointStyle: false } },
  tooltip: {
    enabled: false,
  },
}

export function PowerChart({ points, theme }) {
  const canvasRef = useRef(null)
  const tipRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    applyThemeDefaults()
    if (!canvasRef.current) return
    if (chartRef.current) chartRef.current.destroy()
    chartRef.current = new Chart(canvasRef.current, {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          ...chartPlugins,
          tooltip: {
            enabled: false,
            external: externalTooltip(tipRef.current),
          },
        },
        elements: { point: { radius: 0 }, line: { tension: 0.35, borderWidth: 2 } },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 18 } },
          y: {
            title: { display: true, text: 'kW' },
            grid: { color: 'rgba(148,163,184,0.08)' },
          },
          yGhi: {
            position: 'right',
            title: { display: true, text: 'GHI W/m²' },
            grid: { drawOnChartArea: false },
            beginAtZero: true,
          },
        },
      },
    })
    return () => {
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [theme])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.options.plugins.tooltip.external = externalTooltip(tipRef.current)
    const byInv = { 1: [], 2: [], 3: [] }
    const times = new Set()
    const ghiByTime = new Map()
    for (const p of points || []) {
      if (!byInv[p.inverter_id]) continue
      byInv[p.inverter_id].push(p)
      times.add(p.bucket_ts)
      if (p.ghi_wm2 != null && !ghiByTime.has(p.bucket_ts)) {
        ghiByTime.set(p.bucket_ts, Number(p.ghi_wm2))
      }
    }
    const labels = [...times].sort()
    chart.data.labels = labels.map(labelTime)
    const invSets = [1, 2, 3].map((id) => {
      const m = new Map(byInv[id].map((p) => [p.bucket_ts, p]))
      return {
        label: `Inv ${id}`,
        data: labels.map((t) => (m.get(t) ? m.get(t).ac_power_w / 1000 : null)),
        borderColor: COLORS[id],
        backgroundColor: COLORS[id] + '33',
        yAxisID: 'y',
      }
    })
    const hasGhi = labels.some((t) => ghiByTime.has(t))
    chart.data.datasets = hasGhi
      ? [
          ...invSets,
          {
            label: 'GHI',
            data: labels.map((t) => (ghiByTime.has(t) ? ghiByTime.get(t) : null)),
            borderColor: '#f59e0b',
            backgroundColor: 'transparent',
            borderDash: [4, 3],
            borderWidth: 1.5,
            fill: false,
            yAxisID: 'yGhi',
            order: 0,
          },
        ]
      : invSets
    chart.options.scales.yGhi.display = hasGhi
    chart.update('none')
  }, [points, theme])

  return (
    <div className="chart-wrap">
      <canvas ref={canvasRef} />
      <div className="chart-tip" ref={tipRef} />
    </div>
  )
}

export function AnalyticsChart({ seriesYday, seriesToday, stepMin = 15, theme }) {
  const canvasRef = useRef(null)
  const tipRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    applyThemeDefaults()
    if (!canvasRef.current) return
    if (chartRef.current) chartRef.current.destroy()
    chartRef.current = new Chart(canvasRef.current, {
      type: 'line',
      data: { labels: [], datasets: [] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          ...chartPlugins,
          tooltip: {
            enabled: false,
            external: externalTooltip(tipRef.current),
          },
        },
        elements: {
          point: { radius: 0 },
          line: { tension: 0.4, borderWidth: 2, fill: true },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkipPadding: 18 } },
          y: {
            title: { display: true, text: 'kW' },
            grid: { color: 'rgba(148,163,184,0.08)' },
          },
        },
      },
    })
    return () => {
      chartRef.current?.destroy()
      chartRef.current = null
    }
  }, [theme])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    chart.options.plugins.tooltip.external = externalTooltip(tipRef.current)
    const labels = fullDaySlotLabels(stepMin)
    const slotIndex = (iso) => Math.floor(istMinutesOfDay(iso) / stepMin)
    const mapDay = (pts) => {
      const byInv = { 1: new Map(), 2: new Map(), 3: new Map() }
      for (const p of pts || []) {
        if (!byInv[p.inverter_id]) continue
        byInv[p.inverter_id].set(slotIndex(p.bucket_ts), (p.ac_power_w || 0) / 1000)
      }
      return byInv
    }
    const yday = mapDay(seriesYday)
    const today = mapDay(seriesToday)
    chart.data.labels = labels
    chart.data.datasets = [
      ...[1, 2, 3].map((id) => ({
        label: `Inv ${id} (yday)`,
        data: labels.map((_, i) => (yday[id].has(i) ? yday[id].get(i) : null)),
        borderColor: COLORS[id],
        backgroundColor: 'transparent',
        borderWidth: 2,
        borderDash: [5, 4],
        fill: false,
      })),
      ...[1, 2, 3].map((id) => ({
        label: `Inv ${id} (today)`,
        data: labels.map((_, i) => (today[id].has(i) ? today[id].get(i) : null)),
        borderColor: COLORS[id],
        backgroundColor: COLORS[id] + '33',
        borderWidth: 2,
        fill: true,
      })),
    ]
    chart.options.scales.x.ticks = {
      maxRotation: 0,
      autoSkip: false,
      callback(value, index) {
        return index % 8 === 0 ? this.getLabelForValue(value) : ''
      },
    }
    chart.update('none')
  }, [seriesYday, seriesToday, stepMin, theme])

  return (
    <div className="chart-wrap">
      <canvas ref={canvasRef} />
      <div className="chart-tip" ref={tipRef} />
    </div>
  )
}
