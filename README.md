# RouteDuty

**RouteDuty** is a full-stack trip planner for property-carrying commercial drivers. It accepts a current location, pickup location, drop-off location, and current 70-hour/8-day cycle usage, then returns:

- A road route through all three locations
- Separate current-to-pickup and pickup-to-drop-off route legs
- Major route instructions
- A chronological Hours-of-Service itinerary
- Mapped pickup, fuel, 30-minute break, 10-hour rest, 34-hour restart, and drop-off markers
- Completed midnight-to-midnight Driver's Daily Log sheets for every trip day
- Duty-status totals, route mileage, remarks, cycle recap, and print-ready output

The required stack is **Django REST Framework** and **React/Vite**.

## Why this implementation is reliable

The scheduling engine independently models driving eligibility rather than treating every HOS limit as a ban on work. In particular:

- The **14-hour window** and **70-hour cycle** restrict additional driving, not non-driving work.
- Pickup, drop-off, and fueling can finish even when a driving limit has been reached.
- A reset is inserted only before the next driving segment when required.
- Pickup, drop-off, and a 30-minute fuel stop can satisfy the required interruption of driving because they are consecutive non-driving periods of at least 30 minutes.
- The schedule uses the route service's returned driving duration instead of a hard-coded average speed.
- Fuel is inserted at every full 1,000-route-mile threshold.
- Every generated daily log covers exactly 24 hours using one explicit home-terminal time basis.
- Remarks are emitted only at actual itinerary events; a status continuing through midnight is not mislabeled as a new change.
- Output integrity checks fail closed if route miles, driving duration, page boundaries, or daily totals do not reconcile.
- Nonexistent or ambiguous local departure times at daylight-saving transitions are rejected rather than silently shifted.
- Internal validation replays the finished itinerary and checks the 11-hour, 14-hour, 8-hour break, 70-hour, fuel, rest, and restart constraints.

The detailed calculation design is documented in [`docs/HOS_LOGIC.md`](docs/HOS_LOGIC.md).

## FMCSA assumptions implemented

RouteDuty implements the assessment's property-carrying assumptions:

- 11 hours maximum driving after 10 consecutive hours off duty
- No driving after the 14th consecutive hour after coming on duty
- 30 consecutive minutes without driving after 8 cumulative driving hours
- 70 hours on duty during 8 consecutive days
- Optional 34-hour restart when the simplified cycle balance is exhausted
- One hour on duty for pickup
- One hour on duty for drop-off
- Fueling for 30 on-duty minutes at every 1,000 route miles, assuming zero miles since fuel at departure
- No adverse-driving, short-haul, or split-sleeper exception

Primary references:

- FMCSA Hours of Service summary: https://www.fmcsa.dot.gov/regulations/hours-service/summary-hours-service-regulations
- 49 CFR § 395.3: https://www.ecfr.gov/current/title-49/subtitle-B/chapter-III/subchapter-B/part-395/subpart-A/section-395.3
- Supplied FMCSA Driver's Guide: `FMCSA-HOS-395-DRIVERS-GUIDE-TO-HOS (April 2022)`

## Important disclosed limitation

The assessment supplies only a single `current_cycle_used` value. A precise rolling 8-day calculation would also require the driver's on-duty totals for each preceding day. RouteDuty therefore uses a conservative balance model:

```text
available cycle hours = 70 - current cycle used
```

When driving eligibility is exhausted, the planner schedules a 34-hour restart. This limitation is shown in the interface and returned in the API assumptions instead of being hidden.

The route is generated with the public OSRM `driving` profile. It is a road-route estimate, not certified commercial-truck navigation and does not account for truck height, weight, hazmat, or local restriction data. En-route stop markers are approximate positions along that route; an operational user must verify a safe, legal, suitable fuel or parking facility.

## Technology stack

### Backend

- Python 3.10+
- Django 5.2 LTS
- Django REST Framework
- `requests`
- Django cache for geocoding results
- WhiteNoise and Gunicorn for deployment

### Frontend

- React 18
- Vite
- React Leaflet / Leaflet
- SVG-based duty-status graph rendering
- Responsive and print-specific CSS

### Free mapping services

- Nominatim for geocoding and reverse geocoding
- OSRM for route geometry, route distance, duration, and instructions
- OpenStreetMap tiles for display

Nominatim calls are cached, serialised, and rate-limited to respect its public-use policy.

## Project structure

```text
eld-trip-planner/
├── backend/
│   ├── eld_project/
│   │   └── settings.py
│   ├── trips/
│   │   ├── hos_calculator.py   # HOS scheduling, daily logs, validation
│   │   ├── mapping.py          # geocoding, routing, reverse geocoding
│   │   ├── serializers.py      # API input validation
│   │   ├── views.py            # API orchestration
│   │   └── tests.py            # unit and API tests
│   ├── scripts/stress_validate_hos.py
│   ├── manage.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── App.jsx
│   │   └── index.css
│   ├── .env.example
│   ├── package.json
│   └── vercel.json
├── docs/
│   ├── HOS_LOGIC.md
│   ├── TEST_CASES.md
│   ├── LOOM_SCRIPT.md
│   ├── SUBMISSION_CHECKLIST.md
│   ├── VALIDATION.md
│   └── reference/blank-paper-log.png
├── .github/workflows/ci.yml
├── render.yaml
└── README.md
```

## Run locally

### 1. Backend

From the project root:

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```bash
# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows Command Prompt
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

Install and run:

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Django uses safe development defaults locally. To override settings, provide normal operating-system environment variables such as `NOMINATIM_USER_AGENT`, `OSRM_BASE_URL`, or `CORS_ALLOWED_ORIGINS`; Render supplies production variables from `render.yaml`.

Backend URLs:

- Health check: `http://localhost:8000/api/health/`
- Trip endpoint: `http://localhost:8000/api/plan-trip/`

### 2. Frontend

Open another terminal from the project root:

```bash
cd frontend
npm install
```

Create the environment file:

```bash
# Windows
copy .env.example .env

# macOS/Linux
cp .env.example .env
```

Start Vite:

```bash
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`.

## API request example

```json
{
  "current_location": "Dallas, TX",
  "pickup_location": "Oklahoma City, OK",
  "dropoff_location": "Chicago, IL",
  "current_cycle_used": 12,
  "start_time_local": "2026-07-22T08:00",
  "home_terminal_timezone": "America/Chicago",
  "driver_name": "Alex Morgan",
  "carrier_name": "Northstar Freight LLC",
  "main_office_address": "Dallas, TX",
  "home_terminal_address": "Dallas, TX",
  "vehicle_numbers": "TRK-101 / TRL-101",
  "shipping_document_number": "BOL-2026-001",
  "manifest_number": "MAN-2026-001",
  "shipper_commodity": "General freight"
}
```

The API requires only the four assessment fields. The interface pre-populates a start time and home-terminal time zone so the daily logs are deterministic; the remaining logbook fields are optional.

## Tests

Run the complete backend test suite:

```bash
cd backend
python manage.py test
```

Build the frontend production bundle:

```bash
cd frontend
npm run build
```

Test coverage includes:

- Current-to-pickup driving before pickup
- Map-duration consistency
- 30-minute interruption after 8 cumulative driving hours
- Pickup satisfying the break requirement
- 10-hour daily reset after 11 driving hours
- Fuel at the exact final 1,000-mile threshold
- Non-driving work completing after the 70-hour point
- A 34-hour restart occurring before subsequent driving
- Multiple 24-hour daily logs in the home-terminal time basis
- Non-driving service after the 14-hour driving window
- Daylight-saving skipped and repeated departure times
- Multiple 1,000-mile fuel thresholds
- API validation and response structure
- Randomised schedule replay through the independent validator

See [`docs/VALIDATION.md`](docs/VALIDATION.md) for the independent stress replay and [`docs/TEST_CASES.md`](docs/TEST_CASES.md) for the manual review checklist.

## Deployment

### Backend — Render

1. Push the repository to GitHub.
2. Create a Render Blueprint from the repository.
3. Render reads `render.yaml` and deploys the `backend` directory using the current Blueprint `runtime: python` format.
4. Copy the deployed API URL.

The public Nominatim policy asks applications to identify themselves. Set a more specific value in Render when the repository URL is available:

```text
NOMINATIM_USER_AGENT=RouteDuty/1.0 (https://github.com/your-user/your-repository)
```

### Frontend — Vercel

1. Import the same repository into Vercel.
2. Set the root directory to `frontend`.
3. Add:

```text
VITE_API_BASE_URL=https://your-render-service.onrender.com
```

4. Deploy.

## Loom walkthrough

A timed 3–5 minute walkthrough is included in [`docs/LOOM_SCRIPT.md`](docs/LOOM_SCRIPT.md). The final deployment and handoff steps are in [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md).

## Disclaimer

RouteDuty is a hiring-assessment demonstration. It is not a certified ELD, dispatch system, carrier compliance service, or commercial-truck navigation product.
