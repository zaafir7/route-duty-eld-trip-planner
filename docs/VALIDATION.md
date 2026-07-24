# Validation strategy

RouteDuty uses several layers of validation rather than relying only on visual inspection.

## Automated Django tests

```bash
cd backend
python manage.py check
python manage.py test
```

The test suite covers rule boundaries, non-driving work after driving limits, cycle restarts, exact fuel thresholds, midnight splitting, daylight-saving input validation, API orchestration, and deterministic randomized plans.

## Independent stress replay

The pure scheduling engine can also be replayed without Django or mapping dependencies:

```bash
cd backend
python scripts/stress_validate_hos.py --iterations 20000
```

The script independently tracks the 11-hour, 14-hour, 8-hour interruption, 70-hour, 10-hour rest, 34-hour restart, and 1,000-mile fuel constraints. It also reconciles route distance, route duration, daily mileage, page boundaries, and displayed 24-hour status totals.

The final reviewed build passed 20,000 deterministic randomized schedules and 2,000 complete randomized daily-log reconciliations using seed `20260722`.

## Frontend production check

```bash
cd frontend
npm install
npm run build
```

GitHub Actions repeats Django checks/tests and the Vite production build on every push and pull request.
