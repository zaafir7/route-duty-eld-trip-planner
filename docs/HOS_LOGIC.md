# RouteDuty HOS calculation logic

## 1. Inputs and route legs

The API geocodes three locations and asks OSRM for one route with two ordered legs:

1. Current location → pickup
2. Pickup → drop-off

Each leg provides route miles and estimated driving duration. The scheduler preserves that duration and distributes miles proportionally as the leg is split around HOS events.

## 2. Duty-state model

Every itinerary item is one of four record-of-duty statuses:

- `driving`
- `on_duty`
- `off_duty`
- `sleeper_berth`

Activity types such as pickup, drop-off, and fuel are represented as `on_duty`, while break, rest, and restart activities use the applicable non-driving status.

## 3. State tracked by the scheduler

The calculation loop maintains:

- Current clock time
- Driving hours in the current duty period
- Cumulative driving since the last qualifying 30-minute interruption
- Start time of the current 14-hour window
- Current conservative cycle usage
- Total route miles travelled
- Miles travelled since the last fuel stop

## 4. Rule priority before driving

Before any additional driving, the engine checks in this order:

1. **70-hour eligibility** — if cycle use is at or above 70, schedule a 34-hour restart.
2. **11-hour or 14-hour limit** — schedule a 10-hour sleeper-berth reset.
3. **8-hour interruption requirement** — schedule 30 minutes off duty when useful; if the 14-hour window would expire during that break, use the 10-hour reset instead.

This order avoids redundant rest. For example, a 34-hour restart also includes enough off-duty time to reset the daily driving clocks.

## 5. Driving-segment length

The next driving segment ends at the earliest of:

- Destination
- 11-hour driving limit
- 14-hour driving-window limit
- 8 cumulative driving hours since the last qualifying interruption
- 70-hour cycle balance
- 1,000 miles since the last fuel stop

The loop then processes the limiting event and continues.

## 6. Non-driving work is not incorrectly blocked

The 14-hour and 70-hour rules prohibit additional CMV driving. They do not require the driver to stop all work.

RouteDuty therefore allows:

- Pickup to finish after a cycle boundary
- Drop-off to finish after the 14-hour or 70-hour point
- Fueling to finish before a required restart

When further route driving remains, the necessary reset is inserted after the service task and before driving resumes.

## 7. Qualifying 30-minute interruption

The break clock resets after any consecutive non-driving segment of at least 30 minutes, including:

- Off-duty HOS break
- Sleeper berth
- 30-minute on-duty fuel stop
- One-hour pickup
- One-hour drop-off

The 30-minute interruption does not extend the 14-hour driving window or the 11-hour driving limit.

## 8. Fuel logic

The assessment requires fueling at least once every 1,000 miles. RouteDuty inserts a 30-minute on-duty fuel event whenever cumulative distance since the previous fuel event reaches 1,000 route miles.

A threshold reached at a pickup or final destination still produces a fuel event before the service activity, ensuring the generated plan never shows an interval greater than 1,000 miles. Because the assessment does not provide miles since the previous fuel event, the scheduler starts that counter at zero.

## 9. Cycle model

The exact rolling 8-day calculation cannot be reconstructed from a single aggregate number. RouteDuty uses:

```text
current cycle used + new on-duty time
```

A 34-hour restart resets this simplified cycle counter to zero. Non-driving work can make the displayed used total exceed 70, but no subsequent driving is allowed until a restart.

## 10. Time basis and daily logs

The user supplies a home-terminal IANA time zone. The backend rejects nonexistent and ambiguous departure wall times at daylight-saving transitions. At departure it resolves the UTC offset and uses that explicit home-terminal offset for every generated page.

This prevents the reviewer's browser location from changing the log times and guarantees every generated page is a 24-hour midnight-to-midnight grid. The application is a planning demonstration rather than a certified ELD; the selected departure offset is disclosed on every log.

Each trip segment is clipped at home-terminal midnight. Off-duty filler is inserted before the trip begins and after it ends so each page totals 24 hours. A segment continuing through midnight is not repeated in Remarks as a false status change, and the final transition to off duty is annotated at the trip-completion location.

## 11. Independent validation

After generation, a second pass replays the schedule from scratch and reports any:

- Gap or overlap
- Driving beyond 11 hours
- Driving after the 14th hour
- More than 8 driving hours without a qualifying interruption
- Driving past the 70-hour balance
- More than 1,000 miles without fuel
- Daily rest shorter than 10 hours
- Cycle restart shorter than 34 hours

The API also reconciles scheduled driving miles and hours against the route response and checks every daily page boundary and 24-hour total. If any replay or output-integrity check fails, the endpoint returns an explicit server error instead of presenting the invalid schedule.


## 12. Stop-location limitation

Fuel, break, rest, and restart markers are interpolated along the returned road geometry and reverse-geocoded to a nearby city/state for readable remarks. They are planning points, not a guarantee that the exact coordinate is a legal truck-parking or fueling facility. A driver or carrier must verify safe, legal, suitable facilities before operational use.
