function formatHours(value) {
  const minutes = Math.round(Number(value) * 60)
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  if (!hours) return `${remainder} min`
  return remainder ? `${hours} hr ${remainder} min` : `${hours} hr`
}

export default function RouteInstructions({ legs }) {
  return (
    <div className="route-leg-grid">
      {legs.map((leg) => (
        <article className="route-leg" key={leg.index}>
          <div className="route-leg-header">
            <div>
              <span>Leg {leg.index + 1}</span>
              <h3>{leg.from_name} → {leg.to_name}</h3>
            </div>
            <div className="route-leg-metrics">
              <strong>{leg.miles} mi</strong>
              <span>{formatHours(leg.driving_hours)}</span>
            </div>
          </div>
          {leg.instructions.length ? (
            <ol className="instruction-list">
              {leg.instructions.map((step, index) => (
                <li key={`${step.instruction}-${index}`}>
                  <span>{step.instruction}</span>
                  <small>{step.distance_miles} mi</small>
                </li>
              ))}
            </ol>
          ) : (
            <p className="empty-instructions">No major maneuvers were returned for this route leg.</p>
          )}
        </article>
      ))}
    </div>
  )
}
