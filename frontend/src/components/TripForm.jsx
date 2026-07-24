import { useMemo, useState } from 'react'

const TIME_ZONES = [
  ['America/New_York', 'Eastern — America/New_York'],
  ['America/Chicago', 'Central — America/Chicago'],
  ['America/Denver', 'Mountain — America/Denver'],
  ['America/Phoenix', 'Arizona — America/Phoenix'],
  ['America/Los_Angeles', 'Pacific — America/Los_Angeles'],
  ['America/Anchorage', 'Alaska — America/Anchorage'],
  ['Pacific/Honolulu', 'Hawaii — Pacific/Honolulu'],
  ['UTC', 'UTC'],
]

function defaultStartTime(timeZone) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date())
  const value = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${value.year}-${value.month}-${value.day}T${value.hour}:${value.minute}`
}

function browserTimeZone() {
  const detected = Intl.DateTimeFormat().resolvedOptions().timeZone
  return TIME_ZONES.some(([value]) => value === detected) ? detected : 'America/Chicago'
}

const SAMPLE = {
  current_location: 'Dallas, TX',
  pickup_location: 'Oklahoma City, OK',
  dropoff_location: 'Chicago, IL',
  current_cycle_used: '12',
  home_terminal_timezone: 'America/Chicago',
  driver_name: 'Alex Morgan',
  co_driver_name: '',
  carrier_name: 'Northstar Freight LLC',
  main_office_address: 'Dallas, TX',
  home_terminal_address: 'Dallas, TX',
  vehicle_numbers: 'TRK-101 / TRL-101',
  shipping_document_number: 'BOL-2026-001',
  manifest_number: 'MAN-2026-001',
  shipper_commodity: 'General freight',
}

export default function TripForm({ onSubmit, loading }) {
  const initial = useMemo(() => {
    const initialZone = browserTimeZone()
    return {
      current_location: '',
      pickup_location: '',
      dropoff_location: '',
      current_cycle_used: '0',
      start_time_local: defaultStartTime(initialZone),
      home_terminal_timezone: initialZone,
      driver_name: '',
      co_driver_name: '',
      carrier_name: '',
      main_office_address: '',
      home_terminal_address: '',
      vehicle_numbers: '',
      shipping_document_number: '',
      manifest_number: '',
      shipper_commodity: '',
    }
  }, [])

  const [form, setForm] = useState(initial)
  const [showDetails, setShowDetails] = useState(false)

  const update = (key) => (event) => {
    setForm((current) => ({ ...current, [key]: event.target.value }))
  }

  const handleSubmit = (event) => {
    event.preventDefault()
    onSubmit({
      ...form,
      current_cycle_used: Number.parseFloat(form.current_cycle_used || '0'),
    })
  }

  const loadSample = () => {
    setForm((current) => ({
      ...current,
      ...SAMPLE,
      start_time_local: defaultStartTime(SAMPLE.home_terminal_timezone),
    }))
    setShowDetails(true)
  }

  return (
    <form className="panel form-panel" onSubmit={handleSubmit}>
      <div className="panel-heading">
        <div>
          <span className="section-kicker">Required assessment inputs</span>
          <h2>Plan a compliant property-carrying trip</h2>
        </div>
        <button className="text-button" type="button" onClick={loadSample}>
          Load demo trip
        </button>
      </div>

      <div className="field-grid">
        <div className="field">
          <label htmlFor="current_location">Current location</label>
          <input
            id="current_location"
            placeholder="Dallas, TX"
            value={form.current_location}
            onChange={update('current_location')}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="pickup_location">Pickup location</label>
          <input
            id="pickup_location"
            placeholder="Oklahoma City, OK"
            value={form.pickup_location}
            onChange={update('pickup_location')}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="dropoff_location">Drop-off location</label>
          <input
            id="dropoff_location"
            placeholder="Chicago, IL"
            value={form.dropoff_location}
            onChange={update('dropoff_location')}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="current_cycle_used">Current cycle used (hours)</label>
          <input
            id="current_cycle_used"
            type="number"
            min="0"
            max="70"
            step="0.25"
            value={form.current_cycle_used}
            onChange={update('current_cycle_used')}
            required
          />
        </div>
      </div>

      <div className="planning-grid">
        <div className="field">
          <label htmlFor="start_time_local">Trip start — home-terminal local time</label>
          <input
            id="start_time_local"
            type="datetime-local"
            value={form.start_time_local}
            onChange={update('start_time_local')}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="home_terminal_timezone">Home-terminal time zone</label>
          <select
            id="home_terminal_timezone"
            value={form.home_terminal_timezone}
            onChange={update('home_terminal_timezone')}
            required
          >
            {TIME_ZONES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select>
        </div>
        <div className="details-control">
          <button
            className="details-toggle"
            type="button"
            aria-expanded={showDetails}
            onClick={() => setShowDetails((value) => !value)}
          >
            {showDetails ? 'Hide daily-log details' : 'Add daily-log details'}
          </button>
          <span>Optional fields make the generated sheets submission-ready.</span>
        </div>
      </div>

      {showDetails && (
        <div className="details-grid">
          <div className="field">
            <label htmlFor="driver_name">Driver / certification name</label>
            <input id="driver_name" value={form.driver_name} onChange={update('driver_name')} />
          </div>
          <div className="field">
            <label htmlFor="co_driver_name">Co-driver</label>
            <input id="co_driver_name" value={form.co_driver_name} onChange={update('co_driver_name')} />
          </div>
          <div className="field">
            <label htmlFor="carrier_name">Carrier</label>
            <input id="carrier_name" value={form.carrier_name} onChange={update('carrier_name')} />
          </div>
          <div className="field">
            <label htmlFor="main_office_address">Main office</label>
            <input id="main_office_address" value={form.main_office_address} onChange={update('main_office_address')} />
          </div>
          <div className="field">
            <label htmlFor="home_terminal_address">Home terminal</label>
            <input id="home_terminal_address" value={form.home_terminal_address} onChange={update('home_terminal_address')} />
          </div>
          <div className="field">
            <label htmlFor="vehicle_numbers">Truck / trailer</label>
            <input id="vehicle_numbers" value={form.vehicle_numbers} onChange={update('vehicle_numbers')} />
          </div>
          <div className="field">
            <label htmlFor="shipping_document_number">Shipping document</label>
            <input id="shipping_document_number" value={form.shipping_document_number} onChange={update('shipping_document_number')} />
          </div>
          <div className="field">
            <label htmlFor="manifest_number">DVL / manifest</label>
            <input id="manifest_number" value={form.manifest_number} onChange={update('manifest_number')} />
          </div>
          <div className="field">
            <label htmlFor="shipper_commodity">Shipper &amp; commodity</label>
            <input id="shipper_commodity" value={form.shipper_commodity} onChange={update('shipper_commodity')} />
          </div>
        </div>
      )}

      <div className="submit-row">
        <button className="primary" type="submit" disabled={loading}>
          {loading ? 'Building route and daily logs…' : 'Generate RouteDuty plan'}
        </button>
        <span className="form-note">
          Free OpenStreetMap services are cached and rate-limited; generation can take several seconds.
        </span>
      </div>
    </form>
  )
}
