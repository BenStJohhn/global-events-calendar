# Monthly refresh checklist

This is what the monthly scheduled task does. It's also a manual checklist if you ever want to run it yourself.

1. **Upgrade anything marked `estimated` or `tbc`** in `data/*.yaml` that has been officially announced since the last run.
   Search for the official source, update the dates, set `status: confirmed`, and keep the `key:` unchanged so calendar apps update the event in place instead of duplicating it.
2. **F1 session times** (`data/f1.yaml`): when F1 publishes the timetable for a weekend, set `quali_time` / `race_time` / `sprint_time` (circuit-local) and `times_status: confirmed`.
3. **Fill the rolling horizon**: the window is today → +18 months. Add events for any month that has just come into range, such as next year's festival dates, newly announced calendars (Euro RX, WRC 2028, F1 2028, Dakar 2028), and new one-offs worth a trip.
4. **Watch for cancellations and moves**, especially Middle East rounds (Bahrain, Saudi, Qatar, Abu Dhabi, WRC Saudi, Dakar). If something is cancelled, delete it or set `status: tbc` with a note.
5. Run `python generator/build.py`, then check the counts and spot-check a few entries.
6. Commit with a short summary of what changed and push to `main`. The GitHub Action rebuilds and publishes.

## Adding an event

```yaml
- title: "Event name"
  start: 2027-06-23          # or 2027-06-23T21:00 with tz: Europe/Sofia and duration: 120 (minutes)
  end: 2027-06-27            # inclusive; omit for one-day
  status: confirmed          # confirmed | estimated | tbc
  trip: true                 # ✈️ + booking nudge 90 days before
  location: "Venue, City, Country"
  geo: [51.155, -2.585]
  url: https://official.site
  hook: "2–3 lines on why it's worth it, written with some character."
  notes: "Optional caveats."
  key: unique-id-if-the-title-repeats   # optional
```

For annually recurring events, use a `rule:` instead of `start:`. The types are `fixed`, `nth_weekday`, `weekday_on_or_after`, `easter`, `chinese`, `hijri` and `hebrew` (see the header of `data/cultural.yaml`).
