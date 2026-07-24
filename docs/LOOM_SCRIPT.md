# 3–5 minute Loom walkthrough

## 0:00–0:25 — Introduction

> This is RouteDuty, a Django REST Framework and React application for planning a property-carrying trip and producing Hours-of-Service-compliant daily logs.

Briefly show the four required inputs. Mention the optional start time, home-terminal time zone, and logbook details.

## 0:25–1:20 — Live application demo

Load the sample trip and generate it.

Show:

- Summary cards
- Route through current location, pickup, and drop-off
- Markers for fuel, break, rest, and service events
- Separate route-leg instructions

Mention that driving duration comes from the routing service instead of a hard-coded average speed.

## 1:20–2:10 — HOS itinerary

Scroll through the chronological itinerary.

Explain:

- 8-hour cumulative-driving interruption
- 11-hour driving maximum
- 14-hour driving window
- 10-hour reset
- 70-hour balance and 34-hour restart
- Pickup, drop-off, and fuel as on-duty/not-driving work

Point out that the app does not incorrectly prevent non-driving work after the 14-hour or 70-hour point; it only prevents subsequent driving.

## 2:10–2:55 — Daily log sheets

Show one or more completed log sheets.

Highlight:

- Four duty-status lines
- Vertical status changes
- Total hours for each row
- City/state remarks
- Shipping and carrier fields
- Cycle recap
- 24-hour total check
- Print button

Mention that all logs use the selected home-terminal time basis rather than the viewer's browser time.

## 2:55–3:40 — Code structure

Open:

- `backend/trips/hos_calculator.py`
- `backend/trips/mapping.py`
- `frontend/src/components/LogSheet.jsx`

Explain that one itinerary model drives the map, timeline, and daily sheets. Show the independent `validate_plan` replay.

## 3:40–4:10 — Tests and deployment

Show:

```bash
python manage.py test
npm run build
```

Then show the live Render health endpoint, Vercel application, and GitHub README.

## Closing line

> The main focus was accurate rule ordering, transparent assumptions, and a polished interface that can be reviewed quickly. The repository includes full setup, deployment, logic documentation, and test cases.
