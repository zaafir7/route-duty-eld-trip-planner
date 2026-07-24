# RouteDuty submission checklist

Complete these items after pushing the final code to your own GitHub repository.

## Repository

- Replace `your-user/your-repository` in the Nominatim user-agent guidance with the real public repository URL.
- Confirm the repository contains no `.env`, API secrets, `node_modules`, database, or virtual environment.
- Run the GitHub Actions workflow and confirm both jobs pass.
- Add two screenshots to the README after the hosted application is live: the route/timeline and one completed daily log.

## Backend deployment — Render

- Deploy the root `render.yaml` as a Blueprint.
- Confirm the health endpoint returns JSON at `/api/health/`.
- Set `NOMINATIM_USER_AGENT` to `RouteDuty/1.0 (<public repository URL or contact URL>)`.
- Copy the final HTTPS backend origin.

## Frontend deployment — Vercel

- Import the repository and select `frontend` as the root directory.
- Set `VITE_API_BASE_URL` to the Render origin without a trailing slash.
- Deploy and generate the sample trip once.
- Confirm map tiles, markers, route instructions, timeline, log pages, and print preview all work.

## Final validation

Run locally or confirm the CI equivalents:

```bash
cd backend
python manage.py test
python manage.py check

cd ../frontend
npm install
npm run build
```

Manually test:

- A short same-day trip
- A trip requiring the 30-minute interruption
- A trip requiring a 10-hour rest
- A trip longer than 1,000 miles
- A trip beginning near 70 cycle hours
- A late start that crosses midnight
- An invalid location
- Mobile layout and print preview

## Loom and submission message

- Follow `docs/LOOM_SCRIPT.md` and keep the recording between three and five minutes.
- Show the live application first, then the HOS engine, validator, tests, and repository structure.
- Submit the live Vercel URL, GitHub URL, and Loom URL together.
