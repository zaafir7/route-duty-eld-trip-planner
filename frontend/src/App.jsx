import { useState } from 'react'
import TripForm from './components/TripForm.jsx'
import RouteMap from './components/RouteMap.jsx'
import RouteInstructions from './components/RouteInstructions.jsx'
import Itinerary from './components/Itinerary.jsx'
import LogSheet from './components/LogSheet.jsx'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

function extractErrorMessage(payload) {
  if (!payload) return ''
  if (typeof payload === 'string') return payload
  if (Array.isArray(payload)) return payload.map(extractErrorMessage).filter(Boolean).join(' ')
  if (typeof payload === 'object') {
    if (payload.error) {
      return [extractErrorMessage(payload.error), extractErrorMessage(payload.details)]
        .filter(Boolean)
        .join(' ')
    }
    return Object.entries(payload)
      .map(([field, value]) => {
        const message = extractErrorMessage(value)
        return message ? `${field.replaceAll('_', ' ')}: ${message}` : ''
      })
      .filter(Boolean)
      .join(' ')
  }
  return String(payload)
}

function StatCard({ value, label, detail }) {
  return (
    <article className="stat-card">
      <strong>{value}</strong>
      <span>{label}</span>
      {detail && <small>{detail}</small>}
    </article>
  )
}

function ValidationBadge({ validation }) {
  return validation.passed
    ? <span className="validation-badge validation-pass">HOS checks passed</span>
    : <span className="validation-badge validation-fail">Review generated plan</span>
}

export default function App() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (payload) => {
    setLoading(true)
    setError('')
    setResult(null)

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 150_000)

    try {
      const response = await fetch(`${API_BASE}/api/plan-trip/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
      const contentType = response.headers.get('content-type') || ''
      const data = contentType.includes('application/json')
        ? await response.json()
        : { error: await response.text() }
      if (!response.ok) {
        throw new Error(extractErrorMessage(data) || 'Unable to build the trip.')
      }
      setResult(data)
      window.setTimeout(() => {
        document.getElementById('trip-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 50)
    } catch (err) {
      const message = err.name === 'AbortError'
        ? 'The mapping request timed out. Please retry or use more specific city-and-state locations.'
        : err.message
      setError(message || 'Unable to reach the trip-planning service.')
    } finally {
      window.clearTimeout(timeoutId)
      setLoading(false)
    }
  }

  const notices = result
    ? [...result.validation.issues, ...(result.validation.warnings || [])]
    : []

  return (
    <div className="app-shell">
      <header className="site-header">
        <div>
          <span className="eyebrow">RouteDuty</span>
          <h1>Trip planning that understands duty status.</h1>
          <p>
            A Django and React planner that routes a property-carrying trip, schedules required HOS stops,
            and draws complete daily records of duty status.
          </p>
        </div>
        <div className="header-rule-card">
          <strong>70 hrs / 8 days</strong>
          <span>11-hour drive · 14-hour window</span>
        </div>
      </header>

      <TripForm onSubmit={handleSubmit} loading={loading} />

      {error && (
        <div className="error-banner" role="alert">
          <strong>Trip could not be generated.</strong>
          <span>{error}</span>
        </div>
      )}

      {loading && (
        <div className="loading-panel" aria-live="polite">
          <div className="loading-track"><span /></div>
          <p>Geocoding, routing, placing compliant stops, resolving remarks, and drawing log sheets…</p>
        </div>
      )}

      {result && (
        <main id="trip-results" className="results-stack">
          <section className="result-heading">
            <div>
              <span className="section-kicker">Generated output</span>
              <h2>{result.locations.current.short_name} → {result.locations.dropoff.short_name}</h2>
              <p className="result-subtitle">
                {result.trip_summary.start_display} to {result.trip_summary.end_display} · {result.time_basis.description}
              </p>
            </div>
            <div className="result-actions">
              <ValidationBadge validation={result.validation} />
              <button className="secondary-button" type="button" onClick={() => window.print()}>
                Print daily logs
              </button>
            </div>
          </section>

          {notices.length > 0 && (
            <div className="warning-banner">
              {notices.map((issue) => <span key={issue}>{issue}</span>)}
            </div>
          )}

          <section className="stats-grid" aria-label="Trip summary">
            <StatCard value={result.trip_summary.total_miles} label="Route miles" detail="Road-route distance" />
            <StatCard value={result.trip_summary.total_driving_hours} label="Driving hours" detail="Routing-service duration" />
            <StatCard value={result.trip_summary.total_trip_hours} label="Elapsed trip hours" detail="Includes duty and rest" />
            <StatCard value={result.trip_summary.num_log_days} label="Daily log sheets" detail="Midnight-to-midnight" />
            <StatCard value={result.trip_summary.fuel_stops} label="Fuel stops" detail="Every 1,000 route miles" />
            <StatCard
              value={result.trip_summary.cycle_hours_available_at_end}
              label="Cycle hours available"
              detail={`${result.trip_summary.cycle_used_at_end} hours used at completion`}
            />
          </section>

          <section className="panel map-panel">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">Mapped route</span>
                <h2>Route, pickup, fuel, breaks, rests, and drop-off</h2>
              </div>
              <div className="map-legend" aria-label="Map marker legend">
                <span><i className="legend-dot pickup" /> Pickup</span>
                <span><i className="legend-dot fuel" /> Fuel</span>
                <span><i className="legend-dot break" /> Break</span>
                <span><i className="legend-dot rest" /> 10-hour rest</span>
                <span><i className="legend-dot restart" /> 34-hour restart</span>
                <span><i className="legend-dot dropoff" /> Drop-off</span>
              </div>
            </div>
            <RouteMap route={result.route} locations={result.locations} />
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">Route instructions</span>
                <h2>Current location → pickup → drop-off</h2>
              </div>
              <span className="panel-meta">{result.route.map_estimated_hours} estimated driving hours</span>
            </div>
            <RouteInstructions legs={result.route.legs} />
          </section>

          <section className="panel">
            <div className="panel-heading">
              <div>
                <span className="section-kicker">Chronological schedule</span>
                <h2>Driver itinerary</h2>
              </div>
              <span className="panel-meta">{result.itinerary.length} scheduled activities</span>
            </div>
            <Itinerary itinerary={result.itinerary} />
          </section>

          <section className="assumptions-panel">
            <div>
              <span className="section-kicker">Calculation basis</span>
              <h2>Rules and disclosed assumptions</h2>
            </div>
            <ul>
              {result.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}
            </ul>
          </section>

          <section className="logs-section">
            <div className="logs-heading">
              <div>
                <span className="section-kicker">Record of duty status</span>
                <h2>Completed driver’s daily logs</h2>
              </div>
              <p>
                Each page uses the home-terminal time basis, includes all four duty statuses, and totals exactly 24 hours.
              </p>
            </div>
            {result.daily_logs.map((day) => <LogSheet day={day} key={day.date} />)}
          </section>
        </main>
      )}

      <footer>
        RouteDuty is a planning demonstration, not a certified ELD, legal compliance opinion, or commercial-truck navigation system.
      </footer>
    </div>
  )
}
