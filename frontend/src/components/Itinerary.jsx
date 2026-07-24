const STATUS_LABELS = {
  driving: 'Driving',
  on_duty: 'On duty',
  off_duty: 'Off duty',
  sleeper_berth: 'Sleeper berth',
}

function formatDuration(hours) {
  const totalMinutes = Math.round(hours * 60)
  const wholeHours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  if (!wholeHours) return `${minutes} min`
  if (!minutes) return `${wholeHours} hr`
  return `${wholeHours} hr ${minutes} min`
}

export default function Itinerary({ itinerary }) {
  return (
    <div className="itinerary-list">
      {itinerary.map((item, index) => (
        <article className="itinerary-item" key={`${item.start}-${index}`}>
          <div className={`timeline-dot event-${item.event_type}`} aria-hidden="true" />
          <div className="itinerary-time">
            <strong>{item.start_display}</strong>
            <span>{formatDuration(item.duration_hours)}</span>
          </div>
          <div className="itinerary-copy">
            <div className="itinerary-title-row">
              <h3>{item.label}</h3>
              <span className={`status-pill status-${item.status}`}>{STATUS_LABELS[item.status]}</span>
            </div>
            <p>{item.location}</p>
            <div className="itinerary-metrics">
              {item.miles > 0 && <span className="mileage">{item.miles} route miles</span>}
              {(item.status === 'driving' || item.status === 'on_duty') && (
                <span>Cycle: {item.cycle_used_start} → {item.cycle_used_end} hrs</span>
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  )
}
