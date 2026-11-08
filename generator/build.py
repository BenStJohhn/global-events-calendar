#!/usr/bin/env python3
"""
Global Events Calendar generator.

Reads curated events from data/*.yaml, adds computed events (astronomy,
lunar and religious calendars, rule-based annual festivals), and writes
subscribable .ics feeds to docs/feeds/ plus a landing page at docs/index.html.

Run:  python3 generator/build.py            (window = today -14d .. today +18 months)
      python3 generator/build.py --today 2026-11-08
"""
from __future__ import annotations

import argparse
import calendar as pycal
import datetime as dt
import hashlib
import html
import math
import pathlib
from zoneinfo import ZoneInfo

import yaml
from icalendar import Alarm, Calendar, Event, vGeo, vText

import sky

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "docs"
UK = ZoneInfo("Europe/London")

FEEDS = {
    "cultural":   {"name": "🎭 Global Cultural Festivals", "emoji": "🎭", "color": "#E4572E",
                   "desc": "Festivals, carnivals, lunar and religious celebrations worldwide."},
    "adventure":  {"name": "🪂 Adventure & Sport", "emoji": "🪂", "color": "#17BEBB",
                   "desc": "Sailing, paragliding, MTB, ultra and marquee sporting events."},
    "sky":        {"name": "🌌 Sky & Nature (UK)", "emoji": "🌌", "color": "#2E4057",
                   "desc": "Moons, meteor showers, eclipses, planets and UK wildlife seasons, visible from the UK."},
    "music_arts": {"name": "🎸 Music & Arts", "emoji": "🎸", "color": "#76B041",
                   "desc": "Major music festivals, biennales, film and literature festivals."},
    "motorsport": {"name": "🏁 Motorsport", "emoji": "🏁", "color": "#D7263D",
                   "desc": "F1 (quali, sprint, race), WRC, Dakar & W2RC, British GT, GTWC Europe, rallycross."},
}
EXTRA_FEEDS = {
    "nudges": {"name": "📅 Booking Nudges", "color": "#FFC914",
               "desc": "A heads-up ~3 months before every ✈️ trip-worthy event, so flights and tickets are still sane."},
    "all":    {"name": "🌍 Everything", "color": "#888888",
               "desc": "Every feed combined in one calendar."},
}

STATUS_LABEL = {
    "confirmed": "✅ Confirmed",
    "estimated": "🟡 Estimated (pattern-based or provisional; check before booking)",
    "tbc": "❓ Date TBC (placeholder until the organisers announce)",
}
STATUS_SUFFIX = {"confirmed": "", "estimated": " (est.)", "tbc": " (TBC)"}
NUDGE_DAYS = 90
STAMP = dt.datetime(2026, 11, 8, tzinfo=dt.timezone.utc)  # replaced per build in build()


# ----------------------------------------------------------------------------- helpers
def to_date(v) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


def nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n>=1 -> nth weekday of month; n=-1 -> last. weekday 0=Mon."""
    if n > 0:
        d = dt.date(year, month, 1)
        d += dt.timedelta(days=(weekday - d.weekday()) % 7)
        return d + dt.timedelta(weeks=n - 1)
    last = dt.date(year, month, pycal.monthrange(year, month)[1])
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def easter(year: int, orthodox: bool = False) -> dt.date:
    from dateutil.easter import EASTER_ORTHODOX, EASTER_WESTERN, easter as _e
    return _e(year, EASTER_ORTHODOX if orthodox else EASTER_WESTERN)


def chinese(year: int, lmonth: int, lday: int) -> dt.date:
    import lunardate
    return lunardate.LunarDate(year, lmonth, lday).to_solar_date()


def hijri_dates(hmonth: int, hday: int, lo: dt.date, hi: dt.date):
    import hijridate
    out = []
    for hy in range(1446, 1453):
        try:
            g = hijridate.Hijri(hy, hmonth, hday).to_gregorian()
        except Exception:
            continue
        g = dt.date(g.year, g.month, g.day)
        if lo <= g <= hi:
            out.append(g)
    return out


def hebrew_dates(hmonth: int, hday: int, lo: dt.date, hi: dt.date):
    from convertdate import hebrew
    out = []
    for hy in range(5786, 5791):
        mm = 13 if (hmonth == 12 and hebrew.leap(hy)) else hmonth  # Purim etc. move to Adar II in leap years
        y, m, d = hebrew.to_gregorian(hy, mm, hday)
        g = dt.date(y, m, d)
        if lo <= g <= hi:
            out.append(g)
    return out


def uid_for(feed: str, key: str) -> str:
    return hashlib.sha1(f"{feed}|{key}".encode()).hexdigest()[:20] + "@global-events-calendar"


# ----------------------------------------------------------------------------- expansion
def expand_rule(ev: dict, lo: dt.date, hi: dt.date):
    """Yield (start_date, end_date_inclusive) for a rule-based annual event."""
    r = ev["rule"]
    kind = r["type"]
    days = int(r.get("days", 1))
    offset = int(r.get("offset", 0))
    starts = []
    if kind in ("hijri", "hebrew"):
        fn = hijri_dates if kind == "hijri" else hebrew_dates
        starts = [d + dt.timedelta(days=offset) for d in fn(r["month"], r["day"], lo - dt.timedelta(days=400), hi)]
    else:
        for y in range(lo.year - 1, hi.year + 2):
            try:
                if kind == "fixed":
                    d = dt.date(y, r["month"], r["day"])
                elif kind == "nth_weekday":
                    d = nth_weekday(y, r["month"], r["weekday"], r["n"])
                elif kind == "weekday_on_or_after":
                    d0 = dt.date(y, r["month"], r["day"])
                    d = d0 + dt.timedelta(days=(r["weekday"] - d0.weekday()) % 7)
                elif kind == "easter":
                    d = easter(y, r.get("orthodox", False))
                elif kind == "chinese":
                    d = chinese(y, r["month"], r["day"])
                else:
                    raise ValueError(f"unknown rule type {kind}")
            except Exception:
                continue
            starts.append(d + dt.timedelta(days=offset))
    for s in starts:
        if r.get("only_years") and s.year not in r["only_years"]:
            continue
        e = s + dt.timedelta(days=days - 1)
        if e >= lo and s <= hi:
            yield s, e


def normalise(feed: str, ev: dict, lo: dt.date, hi: dt.date):
    """Turn one YAML entry into one or more concrete event dicts."""
    base = {
        "feed": feed,
        "title": ev["title"],
        "hook": (ev.get("hook") or "").strip(),
        "location": ev.get("location", ""),
        "geo": ev.get("geo"),
        "url": ev.get("url", ""),
        "status": ev.get("status", "confirmed"),
        "trip": bool(ev.get("trip", False)),
        "notes": (ev.get("notes") or "").strip(),
    }
    if "rule" in ev:
        for s, e in expand_rule(ev, lo, hi):
            yield {**base, "allday": True, "start": s, "end": e,
                   "title": base["title"].replace("{year}", str(s.year)),
                   "key": f"{ev['title']}|{s.isoformat()}"}
        return
    start = ev["start"]
    if isinstance(start, dt.datetime) or (isinstance(start, str) and "T" in start):
        tz = ZoneInfo(ev.get("tz", "Europe/London"))
        sdt = start if isinstance(start, dt.datetime) else dt.datetime.fromisoformat(start)
        sdt = sdt.replace(tzinfo=tz) if sdt.tzinfo is None else sdt
        edt = sdt + dt.timedelta(minutes=int(ev.get("duration", 120)))
        if lo <= sdt.date() <= hi:
            yield {**base, "allday": False, "start": sdt, "end": edt,
                   "key": ev.get("key", f"{ev['title']}|{sdt.isoformat()}")}
        return
    s = to_date(start)
    e = to_date(ev.get("end", s))
    if e >= lo and s <= hi:
        yield {**base, "allday": True, "start": s, "end": e,
               "key": ev.get("key", f"{ev['title']}|{s.year}")}


def expand_f1(lo: dt.date, hi: dt.date):
    """F1 weekends -> Sprint / Qualifying / Race timed events (local times -> UTC)."""
    spec = yaml.safe_load((DATA / "f1.yaml").read_text())
    for rnd in spec["rounds"]:
        race_day = to_date(rnd["race_date"])
        tz = ZoneInfo(rnd["tz"])
        quali_day = race_day - dt.timedelta(days=1)
        sessions = []
        if rnd.get("sprint"):
            st = rnd.get("sprint_time") or _shift(rnd["quali_time"], -4)
            sessions.append(("Sprint", quali_day, st, 60))
        sessions.append(("Qualifying", quali_day, rnd["quali_time"], 60))
        sessions.append(("Grand Prix", race_day, rnd["race_time"], 120))
        times_status = rnd.get("times_status", "estimated")
        for name, day, hhmm, dur in sessions:
            h, m = map(int, str(hhmm).split(":"))
            sdt = dt.datetime(day.year, day.month, day.day, h, m, tzinfo=tz)
            if not (lo <= sdt.date() <= hi):
                continue
            label = "Race" if name == "Grand Prix" else name
            title = f"F1 {rnd['name']} – {label}"
            notes = ("Session time confirmed by F1." if times_status == "confirmed" else
                     "F1 publishes exact session times a few months out; the monthly refresh will lock this in.")
            if rnd.get("notes"):
                notes += " " + rnd["notes"].strip()
            yield {
                "feed": "motorsport", "title": title, "hook": rnd.get("hook", "").strip(),
                "location": rnd["location"], "geo": rnd.get("geo"), "url": "https://www.formula1.com/en/racing",
                "status": rnd.get("status", "confirmed"),
                "status_text": None if times_status == "confirmed" else
                "✅ Date confirmed · 🟡 start time estimated (from the circuit's usual slot)",
                "trip": bool(rnd.get("trip", False)) and name == "Grand Prix",
                "notes": notes, "allday": False, "start": sdt, "end": sdt + dt.timedelta(minutes=dur),
                "key": f"f1|{rnd['name']}|{race_day.year}|{name}",
            }


def _shift(hhmm: str, hours: int) -> str:
    h, m = map(int, str(hhmm).split(":"))
    return f"{(h + hours) % 24:02d}:{m:02d}"


# ----------------------------------------------------------------------------- ics writing
def make_vevent(e: dict, today: dt.date) -> Event:
    meta = FEEDS.get(e["feed"], {})
    v = Event()
    prefix = ("✈️ " if e["trip"] else "") + meta.get("emoji", "")
    v.add("summary", f"{prefix} {e['title']}{STATUS_SUFFIX[e['status']]}".strip())
    v.add("uid", uid_for(e["feed"], e["key"]))
    v.add("dtstamp", STAMP)
    if e["allday"]:
        v.add("dtstart", e["start"])
        v.add("dtend", e["end"] + dt.timedelta(days=1))
        v.add("transp", "TRANSPARENT")
    else:
        v.add("dtstart", e["start"].astimezone(dt.timezone.utc))
        v.add("dtend", e["end"].astimezone(dt.timezone.utc))
    lines = []
    if e["hook"]:
        lines.append(e["hook"])
    lines.append("")
    lines.append(f"Status: {e.get('status_text') or STATUS_LABEL[e['status']]}")
    if e["notes"]:
        lines.append(e["notes"])
    if e["trip"]:
        lines.append("✈️ Trip-worthy: there's a booking nudge in the 📅 Booking Nudges feed ~3 months ahead.")
    if not e["allday"]:
        local = e["start"].astimezone(e["start"].tzinfo)
        lines.append(f"Local start: {local:%a %d %b %H:%M} ({local.tzname()}). Your calendar shows it in your own time zone.")
    if e["url"]:
        lines.append(f"Official info: {e['url']}")
    v.add("description", "\n".join(lines).strip())
    if e["location"]:
        v.add("location", e["location"])
    if e["geo"]:
        lat, lon = e["geo"]
        v.add("geo", (float(lat), float(lon)))
        v.add("x-apple-structured-location", f"geo:{lat},{lon}",
              parameters={"VALUE": "URI", "X-TITLE": e["location"] or e["title"],
                          "X-APPLE-RADIUS": "500"})
    if e["url"]:
        v.add("url", e["url"])
    v.add("categories", [meta.get("name", e["feed"]).split(" ", 1)[-1]])
    if e["trip"]:
        a = Alarm()
        a.add("action", "DISPLAY")
        a.add("description", f"Booking nudge: {e['title']} is ~3 months away")
        a.add("trigger", dt.timedelta(days=-NUDGE_DAYS))
        v.add_component(a)
    return v


def make_nudge(e: dict) -> dict | None:
    sd = e["start"] if e["allday"] else e["start"].astimezone(UK).date()
    nd = sd - dt.timedelta(days=NUDGE_DAYS)
    return {
        "feed": "nudges", "title": f"Book now: {e['title']} (in ~3 months)",
        "hook": f"{e['title']} starts {sd:%a %d %b %Y}"
                + (f" in {e['location']}" if e["location"] else "")
                + ". Now's the time to sort flights, tickets and somewhere to sleep.\n\n" + e["hook"],
        "location": e["location"], "geo": e["geo"], "url": e["url"], "status": e["status"],
        "trip": False, "notes": "", "allday": True, "start": nd, "end": nd,
        "key": "nudge|" + e["key"], "nudge_date": nd,
    }


def write_calendar(path: pathlib.Path, name: str, desc: str, color: str, events: list[dict], today: dt.date):
    cal = Calendar()
    cal.add("prodid", "-//Ben St John//Global Events Calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", name)
    cal.add("x-wr-caldesc", desc)
    cal.add("x-wr-timezone", "Europe/London")
    cal.add("x-apple-calendar-color", color)
    cal.add("refresh-interval", dt.timedelta(hours=12), parameters={"VALUE": "DURATION"})
    cal.add("x-published-ttl", "PT12H")
    for e in sorted(events, key=sort_key):
        if e["feed"] == "nudges":
            ve = Event()
            ve.add("summary", "📅 " + e["title"])
            ve.add("uid", uid_for("nudges", e["key"]))
            ve.add("dtstamp", STAMP)
            ve.add("dtstart", e["start"])
            ve.add("dtend", e["start"] + dt.timedelta(days=1))
            ve.add("transp", "TRANSPARENT")
            desc_txt = e["hook"] + f"\n\nStatus of the event date: {STATUS_LABEL[e['status']]}"
            if e["url"]:
                desc_txt += f"\nOfficial info: {e['url']}"
                ve.add("url", e["url"])
            ve.add("description", desc_txt)
            if e["location"]:
                ve.add("location", e["location"])
            cal.add_component(ve)
        else:
            cal.add_component(make_vevent(e, today))
    path.write_bytes(cal.to_ical())


def sort_key(e):
    s = e["start"]
    return dt.datetime.combine(s, dt.time(0), tzinfo=dt.timezone.utc) if e["allday"] else s.astimezone(dt.timezone.utc)


# ----------------------------------------------------------------------------- main
def build(today: dt.date, base_url: str):
    global STAMP
    STAMP = dt.datetime(today.year, today.month, today.day, tzinfo=dt.timezone.utc)
    lo = today - dt.timedelta(days=14)
    hi = today + dt.timedelta(days=549)  # ~18 months
    events: list[dict] = []
    for feed in FEEDS:
        f = DATA / f"{feed}.yaml"
        if f.exists():
            for ev in yaml.safe_load(f.read_text()) or []:
                events.extend(normalise(feed, ev, lo, hi))
    events.extend(expand_f1(lo, hi))
    events.extend(sky.computed_events(lo, hi))

    # de-duplicate by (feed,key)
    seen, uniq = set(), []
    for e in events:
        k = (e["feed"], e["key"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    events = uniq

    nudges = []
    for e in events:
        if e["trip"]:
            n = make_nudge(e)
            if n and n["start"] >= today - dt.timedelta(days=1):
                nudges.append(n)

    OUT.joinpath("feeds").mkdir(parents=True, exist_ok=True)
    counts = {}
    for feed, meta in FEEDS.items():
        evs = [e for e in events if e["feed"] == feed]
        counts[feed] = len(evs)
        write_calendar(OUT / "feeds" / f"{feed}.ics", meta["name"], meta["desc"], meta["color"], evs, today)
    write_calendar(OUT / "feeds" / "nudges.ics", EXTRA_FEEDS["nudges"]["name"], EXTRA_FEEDS["nudges"]["desc"],
                   EXTRA_FEEDS["nudges"]["color"], nudges, today)
    counts["nudges"] = len(nudges)
    write_calendar(OUT / "feeds" / "all.ics", EXTRA_FEEDS["all"]["name"], EXTRA_FEEDS["all"]["desc"],
                   EXTRA_FEEDS["all"]["color"], events, today)
    counts["all"] = len(events)
    write_index(counts, events, today, lo, hi, base_url)
    return counts, events


def write_index(counts, events, today, lo, hi, base_url):
    host = base_url.split("://", 1)[-1].rstrip("/")
    rows = []
    for feed, meta in {**FEEDS, **EXTRA_FEEDS}.items():
        https = f"{base_url.rstrip('/')}/feeds/{feed}.ics"
        webcal = f"webcal://{host}/feeds/{feed}.ics"
        gcal = "https://calendar.google.com/calendar/r?cid=" + webcal
        rows.append(f"""
      <div class="feed" style="--c:{meta['color']}">
        <div class="feed-head"><h2>{html.escape(meta['name'])}</h2><span class="count">{counts.get(feed, 0)} events</span></div>
        <p>{html.escape(meta['desc'])}</p>
        <div class="btns">
          <a class="btn primary" href="{webcal}">Subscribe (Apple / Outlook)</a>
          <a class="btn" href="{gcal}" target="_blank" rel="noopener">Add to Google</a>
          <button class="btn" onclick="copy('{https}', this)">Copy link</button>
        </div>
      </div>""")
    upcoming = sorted([e for e in events if (e["start"] if e["allday"] else e["start"].date()) >= today],
                      key=sort_key)[:12]
    up_rows = "".join(
        f"<li><span class='d'>{(e['start'] if e['allday'] else e['start'].astimezone(UK)):%d %b}</span> "
        f"{'✈️ ' if e['trip'] else ''}{FEEDS[e['feed']]['emoji']} {html.escape(e['title'])}"
        f"{html.escape(STATUS_SUFFIX[e['status']])}</li>" for e in upcoming)
    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ben's Global Events Calendar</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--ink:#e9ecf1;--muted:#9aa3b2;--line:#2a2f3a}}
@media (prefers-color-scheme:light){{:root{{--bg:#f6f5f2;--card:#fff;--ink:#16181d;--muted:#5d6574;--line:#e3e1dc}}}}
*{{box-sizing:border-box}}body{{margin:0;font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--ink)}}
main{{max-width:760px;margin:0 auto;padding:32px 18px 64px}}
h1{{font-size:28px;margin:0 0 6px}} .sub{{color:var(--muted);margin:0 0 24px}}
.feed{{background:var(--card);border:1px solid var(--line);border-left:5px solid var(--c);border-radius:12px;padding:16px 18px;margin:12px 0}}
.feed-head{{display:flex;justify-content:space-between;align-items:baseline;gap:8px}}
.feed h2{{font-size:18px;margin:0}} .count{{color:var(--muted);font-size:13px;white-space:nowrap}}
.feed p{{color:var(--muted);margin:6px 0 12px;font-size:14px}}
.btns{{display:flex;flex-wrap:wrap;gap:8px}}
.btn{{font:inherit;font-size:14px;padding:8px 12px;border-radius:8px;border:1px solid var(--line);background:transparent;color:var(--ink);text-decoration:none;cursor:pointer}}
.btn.primary{{background:var(--c);border-color:var(--c);color:#fff}}
.legend,.up{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:20px 0;font-size:14px}}
.up ul{{list-style:none;padding:0;margin:8px 0 0}} .up li{{padding:3px 0;border-bottom:1px dashed var(--line)}}
.d{{display:inline-block;width:56px;color:var(--muted);font-variant-numeric:tabular-nums}}
footer{{color:var(--muted);font-size:13px;margin-top:28px}}
</style></head><body><main>
<h1>🌍 Ben's Global Events Calendar</h1>
<p class="sub">Festivals, motorsport, adventure, sky events and the arts, picked for an engineer with itchy feet.
Covers {lo:%d %b %Y} → {hi:%d %b %Y} (always 18 months ahead) and rebuilds itself every month.</p>
<div class="legend"><b>Reading an entry</b><br>
✈️ worth a trip (booking nudge ~3 months ahead) · <b>(est.)</b> date estimated from pattern/provisional · <b>(TBC)</b> placeholder until announced.
Every event has a hook, official link and map pin in its notes.</div>
{''.join(rows)}
<div class="up"><b>Coming up next</b><ul>{up_rows}</ul></div>
<footer>Built {dt.datetime.now(UK):%d %b %Y %H:%M} UK. Subscribe to the individual feeds to switch categories on and off, or to 🌍 Everything for one calendar.
Google Calendar refreshes subscribed feeds every ~12–24h; Apple lets you choose under the calendar's settings.</footer>
</main>
<script>function copy(t,b){{navigator.clipboard.writeText(t).then(()=>{{const o=b.textContent;b.textContent='Copied ✓';setTimeout(()=>b.textContent=o,1500)}})}}</script>
</body></html>"""
    (OUT / "index.html").write_text(page)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=None)
    ap.add_argument("--base-url", default="https://benstjohhn.github.io/global-events-calendar")
    a = ap.parse_args()
    t = dt.date.fromisoformat(a.today) if a.today else dt.datetime.now(UK).date()
    c, _ = build(t, a.base_url)
    for k, v in c.items():
        print(f"{k:12s} {v}")
