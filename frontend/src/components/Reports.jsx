import { buildReportRows, downloadCsv, fmtKw, fmtNum } from '../lib/format'

export default function Reports({ apiRows, onExport }) {
  const rows = buildReportRows(apiRows)

  return (
    <section className="tab-panel active">
      <div className="panel">
        <div className="panel-head row-between">
          <div>
            <h2>Daily generation report</h2>
            <p className="muted">Plant totals by Asia/Kolkata day · last 30 days</p>
          </div>
          <button type="button" className="link-btn" onClick={() => onExport(rows)}>
            Export CSV
          </button>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th className="inv-col-1">Inv 1 kWh</th>
                <th className="inv-col-2">Inv 2 kWh</th>
                <th className="inv-col-3">Inv 3 kWh</th>
                <th>Total kWh</th>
                <th>Peak AC</th>
                <th>Yield</th>
                <th>Samples</th>
              </tr>
            </thead>
            <tbody>
              {!rows.length ? (
                <tr>
                  <td colSpan={8} className="muted">
                    No daily stats yet
                  </td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.reading_date}>
                    <td>{r.reading_date}</td>
                    <td className="inv-col-1">{fmtNum(r.inv1_kwh, 2)}</td>
                    <td className="inv-col-2">{fmtNum(r.inv2_kwh, 2)}</td>
                    <td className="inv-col-3">{fmtNum(r.inv3_kwh, 2)}</td>
                    <td>{fmtNum(r.total_kwh, 2)}</td>
                    <td>{fmtKw(r.peak_ac_w)} kW</td>
                    <td>{fmtNum(r.specific_yield_kwh_per_kw, 3)}</td>
                    <td>{r.sample_count ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

export function exportReportCsv(rows) {
  if (!rows?.length) return
  const cols = [
    'reading_date',
    'inv1_kwh',
    'inv2_kwh',
    'inv3_kwh',
    'total_kwh',
    'peak_ac_w',
    'specific_yield_kwh_per_kw',
    'sample_count',
  ]
  const header = [
    'date',
    'inv1_kwh',
    'inv2_kwh',
    'inv3_kwh',
    'total_kwh',
    'peak_ac_w',
    'yield_kwh_per_kw',
    'samples',
  ]
  const lines = [header.join(',')].concat(
    rows.map((r) => cols.map((c) => r[c] ?? '').join(',')),
  )
  downloadCsv('HPCL_Solar_daily_generation_report.csv', lines)
}
