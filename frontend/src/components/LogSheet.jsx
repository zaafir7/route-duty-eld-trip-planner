const ROWS = [
  { key: 'off_duty', label: '1. Off Duty' },
  { key: 'sleeper_berth', label: '2. Sleeper Berth' },
  { key: 'driving', label: '3. Driving' },
  { key: 'on_duty', label: '4. On Duty (Not Driving)' },
]

const LEFT = 142
const TOP = 42
const HOUR_WIDTH = 30
const ROW_HEIGHT = 42
const GRID_WIDTH = HOUR_WIDTH * 24
const GRID_HEIGHT = ROW_HEIGHT * ROWS.length
const TOTAL_X = LEFT + GRID_WIDTH + 52
const SVG_WIDTH = TOTAL_X + 72
const SVG_HEIGHT = TOP + GRID_HEIGHT + 24

const xForHour = (hour) => LEFT + hour * HOUR_WIDTH
const yForStatus = (status) => TOP + ROWS.findIndex((row) => row.key === status) * ROW_HEIGHT + ROW_HEIGHT / 2

function buildDutyPath(segments) {
  if (!segments.length) return ''
  let path = `M ${xForHour(segments[0].start_hour)} ${yForStatus(segments[0].status)}`
  segments.forEach((segment, index) => {
    const y = yForStatus(segment.status)
    if (index > 0) path += ` L ${xForHour(segment.start_hour)} ${y}`
    path += ` L ${xForHour(segment.end_hour)} ${y}`
  })
  return path
}

function formatLogDate(value) {
  const [year, month, day] = value.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC',
  })
}

const formatHours = (value) => Number(value).toFixed(2).replace(/\.00$/, '')
const fieldValue = (value) => value || '—'

function hourLabel(hour) {
  if (hour === 0 || hour === 24) return 'Midnight'
  if (hour === 12) return 'Noon'
  return String(hour % 12)
}

export default function LogSheet({ day }) {
  const log = day.logbook
  const recap = day.cycle_recap
  const dutyPath = buildDutyPath(day.segments)
  const complete = Math.abs(day.total_logged_hours - 24) < 0.01

  return (
    <article className="paper-log">
      <div className="paper-log-heading">
        <div>
          <span>U.S. Department of Transportation</span>
          <h3>Driver’s Daily Log</h3>
          <small>One calendar day — 24 hours</small>
        </div>
        <div className="paper-log-copy-note">
          <strong>Original</strong> — Submit to carrier within 13 days<br />
          <strong>Duplicate</strong> — Driver retains possession for 8 days
        </div>
      </div>

      <div className="log-route-line">
        <div><span>From</span><strong>{fieldValue(log.from_location)}</strong></div>
        <div><span>To</span><strong>{fieldValue(log.to_location)}</strong></div>
      </div>

      <div className="log-fields log-fields-four">
        <div className="log-field"><span>Date</span><strong>{formatLogDate(day.date)}</strong></div>
        <div className="log-field"><span>Total miles driving today</span><strong>{day.miles_driven}</strong></div>
        <div className="log-field"><span>Total mileage today</span><strong>—</strong><small>Odometer reading not supplied.</small></div>
        <div className="log-field"><span>Truck / tractor / trailer</span><strong>{fieldValue(log.vehicle_numbers)}</strong></div>
        <div className="log-field log-field-wide"><span>Name of carrier or carriers</span><strong>{fieldValue(log.carrier_name)}</strong></div>
        <div className="log-field"><span>Main office address</span><strong>{fieldValue(log.main_office_address)}</strong></div>
        <div className="log-field"><span>Home terminal address</span><strong>{fieldValue(log.home_terminal_address)}</strong></div>
        <div className="log-field"><span>Driver’s signature / certification</span><strong>{fieldValue(log.driver_name)}</strong><small>I certify these entries are true and correct.</small></div>
        <div className="log-field"><span>Co-driver</span><strong>{fieldValue(log.co_driver_name)}</strong></div>
        <div className="log-field log-field-wide"><span>Home-terminal time basis</span><strong>{fieldValue(log.home_terminal_time_basis)}</strong></div>
      </div>

      <div className="log-grid-scroll">
        <svg className="eld-grid" viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`} role="img" aria-label={`Duty status graph for ${day.date}`}>
          <rect x="0" y="0" width={SVG_WIDTH} height={SVG_HEIGHT} fill="#ffffff" />
          {ROWS.map((row, index) => (
            <g key={row.key}>
              <rect x={LEFT} y={TOP + index * ROW_HEIGHT} width={GRID_WIDTH} height={ROW_HEIGHT} fill={index % 2 ? '#fbfcfe' : '#ffffff'} />
              <text x={LEFT - 12} y={TOP + index * ROW_HEIGHT + ROW_HEIGHT / 2 + 4} textAnchor="end" className="grid-row-label">{row.label}</text>
              <text x={TOTAL_X} y={TOP + index * ROW_HEIGHT + ROW_HEIGHT / 2 + 4} textAnchor="middle" className="grid-total">{formatHours(day.totals_hours[row.key])}</text>
            </g>
          ))}
          {Array.from({ length: 97 }, (_, index) => {
            const quarter = index / 4
            const isHour = index % 4 === 0
            const isSixHour = index % 24 === 0
            return <line key={index} x1={xForHour(quarter)} x2={xForHour(quarter)} y1={TOP} y2={TOP + GRID_HEIGHT} className={isSixHour ? 'grid-major-line' : isHour ? 'grid-hour-line' : 'grid-quarter-line'} />
          })}
          {Array.from({ length: ROWS.length + 1 }, (_, index) => (
            <line key={index} x1={LEFT} x2={LEFT + GRID_WIDTH} y1={TOP + index * ROW_HEIGHT} y2={TOP + index * ROW_HEIGHT} className="grid-horizontal-line" />
          ))}
          {Array.from({ length: 25 }, (_, hour) => (
            <text key={hour} x={xForHour(hour)} y={TOP - 13} textAnchor={hour === 0 ? 'start' : hour === 24 ? 'end' : 'middle'} className={hour === 0 || hour === 12 || hour === 24 ? 'grid-hour-label grid-hour-label-wide' : 'grid-hour-label'}>{hourLabel(hour)}</text>
          ))}
          <text x={TOTAL_X} y={TOP - 13} textAnchor="middle" className="grid-hour-label grid-hour-label-wide">Total hours</text>
          <path d={dutyPath} className="duty-status-path" />
        </svg>
      </div>

      <div className="remarks-heading">
        <strong>Remarks</strong>
        <span>Generated duty changes and operational activity notes</span>
      </div>
      <div className="remarks-table-wrap">
        <table className="remarks-table">
          <thead><tr><th>Time</th><th>Activity</th><th>Location / note</th></tr></thead>
          <tbody>
            {day.remarks.map((remark, index) => (
              <tr key={`${remark.time}-${remark.label}-${index}`}>
                <td>{remark.time}</td><td>{remark.label}</td><td>{remark.location || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="log-support-grid">
        <div><span>Shipping documents</span><strong>{fieldValue(log.shipping_document_number)}</strong></div>
        <div><span>DVL or manifest no.</span><strong>{fieldValue(log.manifest_number)}</strong></div>
        <div><span>Shipper &amp; commodity</span><strong>{fieldValue(log.shipper_commodity)}</strong></div>
      </div>

      <div className="log-recap">
        <div><span>Cycle used at start</span><strong>{formatHours(recap.cycle_used_start)} hrs</strong></div>
        <div><span>On-duty hours today</span><strong>{formatHours(recap.on_duty_hours_today)} hrs</strong></div>
        <div><span>Cycle used at end</span><strong>{formatHours(recap.cycle_used_end)} hrs</strong></div>
        <div><span>Cycle hours available</span><strong>{formatHours(recap.cycle_hours_available_end)} hrs</strong></div>
        <div><span>34-hour restart</span><strong>{recap.restart_completed ? 'Completed' : 'Not completed'}</strong></div>
      </div>

      <div className="log-total-check">
        <span>Four status lines total</span>
        <strong>{formatHours(day.total_logged_hours)} hours</strong>
        <span className={complete ? 'check-pass' : 'check-fail'}>{complete ? 'Complete' : 'Review'}</span>
      </div>
    </article>
  )
}
