import { useEffect } from 'react'
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'

const EVENT_SYMBOLS = {
  current: 'C',
  pickup: 'P',
  dropoff: 'D',
  fuel: 'F',
  break: 'B',
  rest: 'R',
  restart: '34',
}

function markerIcon(type, symbol = EVENT_SYMBOLS[type] || '•') {
  return L.divIcon({
    className: '',
    html: `<div class="route-marker route-marker-${type}"><span>${symbol}</span></div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -18],
  })
}

function FitRoute({ positions }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length) map.fitBounds(L.latLngBounds(positions), { padding: [36, 36], maxZoom: 9 })
  }, [map, positions])
  return null
}

function groupEvents(events) {
  const grouped = new Map()
  events.forEach((event) => {
    const key = `${event.lat.toFixed(5)}:${event.lon.toFixed(5)}`
    const group = grouped.get(key) || { lat: event.lat, lon: event.lon, events: [] }
    group.events.push(event)
    grouped.set(key, group)
  })
  return [...grouped.values()]
}

export default function RouteMap({ route, locations }) {
  if (!route?.geometry?.length || !locations) return null

  const positions = route.geometry.map(([lon, lat]) => [lat, lon])
  const center = positions[Math.floor(positions.length / 2)]
  const eventGroups = groupEvents(route.events || [])

  return (
    <div className="map-container">
      <MapContainer center={center} zoom={5} style={{ height: '100%', width: '100%' }}>
        <FitRoute positions={positions} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Polyline positions={positions} pathOptions={{ color: '#f3a712', weight: 5, opacity: 0.9 }} />

        <Marker position={[locations.current.lat, locations.current.lon]} icon={markerIcon('current')}>
          <Popup><strong>Current location</strong><br />{locations.current.display_name}</Popup>
        </Marker>

        {eventGroups.map((group, index) => {
          const single = group.events.length === 1
          const type = single ? group.events[0].event_type : 'multi'
          const symbol = single ? undefined : String(group.events.length)
          return (
            <Marker
              key={`${group.lat}-${group.lon}-${index}`}
              position={[group.lat, group.lon]}
              icon={markerIcon(type, symbol)}
            >
              <Popup>
                {group.events.map((event, eventIndex) => (
                  <div className="grouped-map-event" key={`${event.event_type}-${event.start}-${eventIndex}`}>
                    <strong>{event.label}</strong><br />
                    {event.start_display}<br />
                    {event.location}<br />
                    Route mile {event.route_mile}
                  </div>
                ))}
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>
    </div>
  )
}
