# Final manual test checklist

Run these after deployment and capture the strongest examples for the Loom video.

## 1. Short same-day trip

```text
Current: Dallas, TX
Pickup: Austin, TX
Drop-off: Houston, TX
Cycle used: 0
Time zone: America/Chicago
```

Expected:

- Both route legs appear
- Pickup and drop-off are each one hour on duty
- No unnecessary 10-hour rest
- Daily status totals equal 24 hours

## 2. More than 8 driving hours

Use a route with more than 8 estimated driving hours after the pickup.

Expected:

- A 30-minute non-driving interruption appears before driving exceeds 8 cumulative hours
- The break does not reset the 14-hour window

## 3. More than 11 driving hours

Use a long interstate route such as Seattle, WA to Denver, CO after a nearby pickup.

Expected:

- The driver reaches no more than 11 driving hours in one duty period
- A 10-hour sleeper-berth rest appears
- Driving resumes with new 11-hour and 14-hour clocks

## 4. Fuel threshold

Use a trip longer than 1,000 miles.

Expected:

- Fuel marker at approximately route mile 1,000
- Each fuel event is 30 minutes on duty, not driving
- No distance interval exceeds 1,000 miles

## 5. Cycle nearly exhausted

```text
Current cycle used: 69.5
```

Expected:

- The driver may use the remaining legal driving balance
- A 34-hour restart appears before any driving that would exceed 70 hours
- Daily clocks also reset after the restart

## 6. Non-driving work at the cycle limit

Use a short route and a current cycle value that lets the driver reach the drop-off just below 70 hours.

Expected:

- The one-hour drop-off finishes even if cycle usage passes 70
- No unnecessary 34-hour restart is appended when the trip is complete
- Validation still passes because no driving occurs beyond 70

## 7. Midnight crossing

Start late in the home-terminal day.

Expected:

- The schedule is split into multiple log pages
- The first page ends at 24:00 and the next begins at 00:00
- Every page totals 24 hours

## 8. Time-zone independence

Generate a Central Time trip while viewing the frontend from a computer in another time zone.

Expected:

- Itinerary and log times remain in the selected home-terminal basis
- Browser location does not shift the displayed duty times

## 9. Invalid input and service failure

Try:

- Unknown location text
- Cycle below 0 or above 70
- Invalid API URL

Expected:

- Clear error message
- No broken result interface
- Form remains usable for another attempt

## 10. Production checks

```bash
cd backend
python manage.py test

cd ../frontend
npm run build
```

Then verify:

- Render health endpoint returns `status: ok`
- Vercel calls the Render URL successfully
- Map attribution is visible
- Print preview contains only daily log sheets
- Mobile layout remains usable

## 11. Daylight-saving input validation

Try a skipped local time such as `2026-03-08 02:30` in `America/Chicago`, and a repeated local time such as `2026-11-01 01:30`.

Expected:

- The request is rejected with a clear field-level message
- The backend does not silently shift or guess the departure instant

## 12. Non-driving work after a driving window

Use an edge case where a pickup or drop-off extends beyond the 14-hour driving window.

Expected:

- The service work is allowed to finish
- A 10-hour rest is inserted only before additional driving
- No unnecessary reset is appended after a completed trip

## 13. Remarks around midnight and trip completion

Use a schedule where a 10-hour rest crosses midnight.

Expected:

- The continuing rest line appears on both graph pages
- The second page does not invent a new `00:00` rest remark
- The final log contains a `Trip complete — off duty` remark at the drop-off location
- The odometer-style `Total mileage today` field remains blank because no odometer input is supplied
