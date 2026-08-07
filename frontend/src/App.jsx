import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { fetchJson } from './lib/api'
import {
  buildReportRows,
  fmtChartDate,
  fmtIst,
  fmtNum,
} from './lib/format'
import Overview from './components/Overview'
import Analytics, { exportAnalyticsCsv } from './components/Analytics'
import History from './components/History'
import Reports, { exportReportCsv } from './components/Reports'
import Alerts from './components/Alerts'

const THEME_KEY = 'HPCL Solar_theme'
const TAB_KEY = 'HPCL Solar_tab'
const SIDEBAR_KEY = 'HPCL Solar_sidebar_collapsed'
const POLL_MS = 15000
const WEATHER_TTL_MS = 30 * 1000

function plantStatusText(inverters) {
  const statuses = (inverters || []).map((r) => r.status_code)
  if (statuses.includes(3)) return 'Fault'
  if (statuses.length && statuses.every((s) => s === 0)) return 'Standby'
  return 'Normal'
}

async function loadSeriesPoints(chartMode, todayDate) {
  let url
  let caption = '—'
  if (chartMode === 'day' && todayDate) {
    url = `/api/series?day=${todayDate}&bucket_seconds=120`
    caption = fmtChartDate(todayDate)
  } else {
    const hours = Number(chartMode) || 6
    const bucket = hours <= 6 ? 60 : hours <= 12 ? 120 : 300
    url = `/api/series?hours=${hours}&bucket_seconds=${bucket}`
    caption = `Last ${hours} h`
  }
  const data = await fetchJson(url)
  const points = data.points || []
  if (chartMode !== 'day' && points.length) {
    const last = points[points.length - 1].bucket_ts
    caption = `${fmtChartDate(last)} · last ${Number(chartMode) || 6} h`
  } else if (chartMode === 'day' && data.day) {
    caption = fmtChartDate(data.day)
  } else if (chartMode === 'day' && points.length) {
    caption = fmtChartDate(points[0].bucket_ts)
  }
  return { points, caption }
}

export default function App() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem(THEME_KEY) || 'dark',
  )
  const [tab, setTab] = useState(() => localStorage.getItem(TAB_KEY) || 'overview')
  const [latest, setLatest] = useState(null)
  const [compare, setCompare] = useState(null)
  const [weather, setWeather] = useState(null)
  const [seriesPoints, setSeriesPoints] = useState([])
  const [chartMode, setChartMode] = useState('day')
  const [chartCaption, setChartCaption] = useState('—')
  const [sysOffline, setSysOffline] = useState(false)
  const [analyticsRange, setAnalyticsRange] = useState('yesterday')
  const [analytics, setAnalytics] = useState(null)
  const [dailyRows, setDailyRows] = useState([])
  const [historyDays, setHistoryDays] = useState(14)
  const [historyRows, setHistoryRows] = useState([])
  const [reportRows, setReportRows] = useState([])
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem(SIDEBAR_KEY) === '1',
  )

  const tabRef = useRef(tab)
  const chartModeRef = useRef(chartMode)
  const analyticsRangeRef = useRef(analyticsRange)
  const historyDaysRef = useRef(historyDays)
  const weatherCacheRef = useRef({ data: null, at: 0 })
  const compareRef = useRef(null)
  const abortRef = useRef(null)

  tabRef.current = tab
  chartModeRef.current = chartMode
  analyticsRangeRef.current = analyticsRange
  historyDaysRef.current = historyDays

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  useEffect(() => {
    localStorage.setItem(TAB_KEY, tab)
  }, [tab])

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? '1' : '0')
  }, [sidebarCollapsed])

  const sideNav = useMemo(() => {
    if (tab === 'reports') return 'reports'
    if (tab === 'history') return 'history'
    return 'dashboard'
  }, [tab])

  const refresh = useCallback(async () => {
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac

    const currentTab = tabRef.current
    const needsCompare = currentTab === 'overview' || currentTab === 'analytics'
    const now = Date.now()
    const wxCached =
      weatherCacheRef.current.data &&
      now - weatherCacheRef.current.at < WEATHER_TTL_MS
        ? weatherCacheRef.current.data
        : null

    try {
      const tasks = {
        latest: fetchJson('/api/latest'),
      }
      if (needsCompare) tasks.compare = fetchJson('/api/compare')
      if (!wxCached) tasks.weather = fetchJson('/api/weather')

      if (currentTab === 'overview') {
        // series needs today_date from compare — fetch after, or in parallel with placeholder
      } else if (currentTab === 'analytics') {
        tasks.analytics = fetchJson(
          `/api/analytics?range=${analyticsRangeRef.current}`,
        )
        tasks.daily14 = fetchJson('/api/daily?days=14')
      } else if (currentTab === 'alerts') {
        tasks.dailyAlerts = fetchJson('/api/daily?days=14')
      } else if (currentTab === 'reports') {
        tasks.daily30 = fetchJson('/api/daily?days=30')
      } else if (currentTab === 'history') {
        tasks.dailyHist = fetchJson(
          `/api/daily?days=${historyDaysRef.current}`,
        )
      }

      const keys = Object.keys(tasks)
      const values = await Promise.all(keys.map((k) => tasks[k]))
      if (ac.signal.aborted) return
      const result = Object.fromEntries(keys.map((k, i) => [k, values[i]]))

      setLatest(result.latest)
      if (result.compare) {
        setCompare(result.compare)
        compareRef.current = result.compare
      }
      if (result.weather) {
        weatherCacheRef.current = { data: result.weather, at: now }
        setWeather(result.weather)
      } else if (wxCached) {
        setWeather(wxCached)
      }
      if (result.analytics) setAnalytics(result.analytics)
      if (result.daily14) setDailyRows(result.daily14.rows || [])
      if (result.dailyAlerts) setDailyRows(result.dailyAlerts.rows || [])
      if (result.daily30) setReportRows(result.daily30.rows || [])
      if (result.dailyHist) setHistoryRows(result.dailyHist.rows || [])

      if (currentTab === 'overview') {
        const todayDate =
          result.compare?.today_date || compareRef.current?.today_date
        const { points, caption } = await loadSeriesPoints(
          chartModeRef.current,
          todayDate,
        )
        if (ac.signal.aborted) return
        setSeriesPoints(points)
        setChartCaption(caption)
      }

      setSysOffline(false)
    } catch (err) {
      if (ac.signal.aborted) return
      console.error(err)
      setSysOffline(true)
    }
  }, [])

  // Stable poll: mount once; re-run when tab / range / history days change
  useEffect(() => {
    refresh()
    const id = setInterval(refresh, POLL_MS)
    return () => {
      clearInterval(id)
      abortRef.current?.abort()
    }
  }, [refresh, tab, analyticsRange, historyDays])

  const skipChartModeFetch = useRef(true)

  // Chart window change — series only (initial load handled by refresh())
  useEffect(() => {
    if (skipChartModeFetch.current) {
      skipChartModeFetch.current = false
      return
    }
    if (tabRef.current !== 'overview') return
    let cancelled = false
    ;(async () => {
      try {
        const todayDate = compareRef.current?.today_date
        const { points, caption } = await loadSeriesPoints(chartMode, todayDate)
        if (!cancelled) {
          setSeriesPoints(points)
          setChartCaption(caption)
        }
      } catch (err) {
        console.error(err)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [chartMode])

  const alerts = latest?.alerts || []
  const alertCount = alerts.length
  const pulseEff = (() => {
    const effs = (latest?.inverters || [])
      .map((r) => r.efficiency_pct)
      .filter((v) => v != null)
    return effs.length ? fmtNum(Math.max(...effs), 1) : '—'
  })()

  const stale = !!latest?.plant?.is_stale
  const clock = fmtIst(latest?.server_time || new Date().toISOString())

  return (
    <div className={`app${sidebarCollapsed ? ' sidebar-collapsed' : ''}`}>
      <div className="sidebar-wrap">
        <aside className="sidebar">
          <div className="side-brand">
            <img
              className="logo-mark"
              src="/img/hprge-logo.png"
              alt="HPRGE"
              width={44}
              height={44}
            />
            <div className="side-brand-text">
              <p className="logo-name">HPCL Solar</p>
              <p className="logo-site">Devanagonthi Terminal</p>
            </div>
          </div>

          <div className="plant-card">
            <div className="plant-icon" aria-hidden="true">
              ☀
            </div>
            <div>
              <p className="plant-id">Plant #402</p>
              <p className="plant-status">
                <span className="dot ok" /> Status:{' '}
                <strong>{plantStatusText(latest?.inverters)}</strong>
              </p>
            </div>
          </div>

          <nav className="side-nav">
            {[
              ['dashboard', '▣', 'Dashboard', () => setTab('overview')],
              ['history', '◷', 'Day wise History', () => setTab('history')],
              ['reports', '☰', 'Reports', () => setTab('reports')],
            ].map(([nav, icon, label, fn]) => (
              <a
                key={nav}
                className={`side-link${sideNav === nav ? ' active' : ''}`}
                href="#"
                title={label}
                onClick={(e) => {
                  e.preventDefault()
                  fn?.()
                }}
              >
                <span className="si">{icon}</span>
                <span className="side-link-label">{label}</span>
              </a>
            ))}
          </nav>

          <div className="side-pulse lite-only">
            <p className="pulse-label">Live System Pulse</p>
            <p className="pulse-val">
              <span>{pulseEff}</span>
              <span className="pulse-unit">%</span>
            </p>
            <p className="pulse-sub">Efficiency rating (peak)</p>
          </div>

          <div className="side-foot">
            <a className="side-link" href="#" title="Support">
              <span className="si">◷</span>
              <span className="side-link-label">Support</span>
            </a>
            <a className="side-link" href="#" title="Logout">
              <span className="si">↪</span>
              <span className="side-link-label">Logout</span>
            </a>
          </div>
        </aside>
        <button
          type="button"
          className="sidebar-toggle"
          title={sidebarCollapsed ? 'Open menu' : 'Close menu'}
          aria-label={sidebarCollapsed ? 'Open side menu' : 'Close side menu'}
          aria-expanded={!sidebarCollapsed}
          onClick={() => setSidebarCollapsed((v) => !v)}
        >
          <span className="chev" aria-hidden="true">
            ‹
          </span>
        </button>
      </div>

      <div className="shell">
        <header className="topbar">
          <nav className="tabs" role="tablist">
            {[
              ['overview', 'Overview'],
              ['analytics', 'Analytics'],
              ['alerts', 'Alerts'],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={`tab${tab === id ? ' active' : ''}`}
                onClick={() => setTab(id)}
              >
                {label}
                {id === 'alerts' && alertCount > 0 && (
                  <span className="badge">{alertCount}</span>
                )}
              </button>
            ))}
          </nav>

          <div className="top-right">
            <div className="time-block">
              <p className="clock">{clock}</p>
              <p
                className={`sys-status ${
                  sysOffline ? 'stale' : stale ? 'stale' : 'live'
                }`}
              >
                {sysOffline
                  ? 'Offline'
                  : stale
                    ? 'System stale'
                    : 'System normal'}
              </p>
            </div>
            <button
              type="button"
              className="icon-btn"
              title="Toggle lite theme"
              aria-pressed={theme === 'lite'}
              onClick={() => setTheme((t) => (t === 'lite' ? 'dark' : 'lite'))}
            >
              <span>{theme === 'lite' ? '☾' : '☀'}</span>
            </button>
            <button
              type="button"
              className="icon-btn"
              title="Alerts"
              aria-label="Open alerts"
              onClick={() => setTab('alerts')}
            >
              🔔
              {alertCount > 0 && (
                <span className="badge float">{alertCount}</span>
              )}
            </button>
          </div>
        </header>

        <main className="content">
          {tab === 'overview' && (
            <Overview
              latest={latest}
              compare={compare}
              weather={weather}
              seriesPoints={seriesPoints}
              chartMode={chartMode}
              chartCaption={chartCaption}
              theme={theme}
              onChartMode={setChartMode}
            />
          )}
          {tab === 'analytics' && (
            <Analytics
              data={analytics}
              dailyRows={dailyRows}
              range={analyticsRange}
              theme={theme}
              onRange={setAnalyticsRange}
              onExport={() => exportAnalyticsCsv(dailyRows)}
            />
          )}
          {tab === 'alerts' && (
            <Alerts
              alerts={alerts}
              dailyRows={dailyRows}
              todayDate={compare?.today_date || latest?.plant?.today_date}
            />
          )}
          {tab === 'history' && (
            <History
              rows={historyRows}
              days={historyDays}
              onDays={setHistoryDays}
            />
          )}
          {tab === 'reports' && (
            <Reports
              apiRows={reportRows}
              onExport={(rows) =>
                exportReportCsv(rows || buildReportRows(reportRows))
              }
            />
          )}
        </main>
      </div>
    </div>
  )
}
