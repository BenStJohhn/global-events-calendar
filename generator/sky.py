"""Computed sky events for a UK observer (Bristol-ish), using PyEphem."""
from __future__ import annotations

import datetime as dt
import math
from zoneinfo import ZoneInfo

import ephem

UK = ZoneInfo("Europe/London")
UTC = dt.timezone.utc
KM_PER_AU = 149_597_870.7

MOON_NAMES = {
    1: ("Wolf Moon", "named for hungry winter packs howling outside Anglo-Saxon villages"),
    2: ("Snow Moon", "traditionally the snowiest month in the northern hemisphere"),
    3: ("Worm Moon", "when thawing soil brings the earthworms (and the birds) back"),
    4: ("Pink Moon", "named for the pink wild phlox of spring, not the Moon's colour, sadly"),
    5: ("Flower Moon", "everything's blooming; bluebell woods are at their best around now"),
    6: ("Strawberry Moon", "the lowest-riding full moon of the year: big, golden and syrupy on the horizon"),
    7: ("Buck Moon", "when deer antlers are in full velvet growth"),
    8: ("Sturgeon Moon", "named for when the Great Lakes sturgeon were easiest to catch"),
    9: ("Corn Moon", "harvest-time light for bringing the crops in"),
    10: ("Hunter's Moon", "bright autumn nights once used for hunting ahead of winter"),
    11: ("Beaver Moon", "the time to set traps before the swamps froze"),
    12: ("Cold Moon", "the long-nights moon, riding highest in the sky of the whole year"),
}

# name, peak month/day (night of), ZHR-ish, radiant note, hook
METEOR_SHOWERS = [
    ("Quadrantids", 1, 3, 110, "Short, sharp peak of only a few hours, so it's a gamble, but one of the year's strongest. Radiant high in the north-east after midnight."),
    ("Lyrids", 4, 22, 18, "One of the oldest recorded showers (Chinese records from 687 BC). Modest rates, occasional bright fireballs, best before dawn."),
    ("Eta Aquariids", 5, 6, 50, "Debris from Halley's Comet itself. Low radiant from the UK, so expect a handful of long 'earthgrazers' just before dawn."),
    ("Perseids", 8, 12, 100, "The summer classic: warm nights, fast bright meteors with trains. Lie back facing north-east after 11pm."),
    ("Draconids", 10, 8, 10, "Usually a trickle, occasionally a storm. Unusually, best in the evening rather than before dawn."),
    ("Orionids", 10, 21, 20, "Halley's Comet again, the autumn return leg. Swift meteors from Orion's raised club, best after midnight."),
    ("Leonids", 11, 17, 15, "Fastest meteors of the year at 71 km/s. Famous for historic storms; usually a modest show nowadays."),
    ("Geminids", 12, 14, 150, "The king of showers: slow, bright, colourful, and visible from mid-evening. Wrap up warm; it's worth it."),
]


def _ukdate(d: ephem.Date) -> dt.datetime:
    return d.datetime().replace(tzinfo=UTC).astimezone(UK)


def _moon_illum(when_utc: dt.datetime) -> float:
    m = ephem.Moon(when_utc.strftime("%Y/%m/%d %H:%M"))
    return m.phase  # % illuminated


def _ev(title, start, hook, notes="", status="confirmed", trip=False, location="Visible across the UK",
        geo=None, url="", allday=True, end=None, key=None, duration=60):
    e = {"feed": "sky", "title": title, "hook": hook, "notes": notes, "status": status, "trip": trip,
         "location": location, "geo": geo, "url": url, "allday": allday}
    if allday:
        e["start"] = start
        e["end"] = end or start
    else:
        e["start"] = start
        e["end"] = start + dt.timedelta(minutes=duration)
    e["key"] = key or f"sky|{title}|{(start if allday else start.date()).isoformat()}"
    return e


def full_and_new_moons(lo: dt.date, hi: dt.date):
    out = []
    d = ephem.Date(lo.strftime("%Y/%m/%d"))
    fulls = []
    while True:
        d = ephem.next_full_moon(d)
        t = _ukdate(d)
        if t.date() > hi:
            break
        fulls.append(t)
        d = ephem.Date(d + 1)
    # Harvest moon = full moon nearest the September equinox
    harvest = set()
    for y in {f.year for f in fulls}:
        eq = _ukdate(ephem.next_autumnal_equinox(f"{y}/6/1"))
        near = min((f for f in fulls if f.year == y), key=lambda f: abs((f - eq).total_seconds()), default=None)
        if near and abs((near - eq).days) < 20:
            harvest.add(near)
    month_count = {}
    for t in fulls:
        month_count.setdefault((t.year, t.month), []).append(t)
    for t in fulls:
        moon = ephem.Moon(t.astimezone(UTC).strftime("%Y/%m/%d %H:%M"))
        km = moon.earth_distance * KM_PER_AU
        name, why = MOON_NAMES[t.month]
        if t in harvest:
            name, why = "Harvest Moon", "the full moon nearest the autumn equinox, rising at almost the same time several nights running"
        elif any(h for h in harvest if h < t and (t - h).days < 40):
            name, why = "Hunter's Moon", "the first full moon after the Harvest Moon, traditionally the hunting moon"
        tags = []
        if len(month_count[(t.year, t.month)]) == 2 and t == month_count[(t.year, t.month)][1]:
            tags.append("Blue Moon")
        if km < 361_000:
            tags.append("Supermoon")
        elif km > 404_000:
            tags.append("Micromoon")
        tag = f" ({', '.join(tags)})" if tags else ""
        hook = (f"Full {name}{tag}: {why}. Peak at {t:%H:%M} UK time; catch it rising at dusk on the "
                f"evening closest to the peak for the classic giant-on-the-horizon photo.")
        if "Supermoon" in tags:
            hook += f" Only {km:,.0f} km away, up to ~14% bigger and ~30% brighter than a micromoon."
        out.append(_ev(f"Full {name}{tag}", t.date(), hook,
                       notes=f"Exact full moon: {t:%a %d %b %Y %H:%M %Z}. Earth–Moon distance {km:,.0f} km.",
                       key=f"sky|fullmoon|{t.date().isoformat()}"))
    # new moons = dark-sky windows
    d = ephem.Date(lo.strftime("%Y/%m/%d"))
    while True:
        d = ephem.next_new_moon(d)
        t = _ukdate(d)
        if t.date() > hi:
            break
        season = ("Milky Way core is up late; head somewhere properly dark" if 4 <= t.month <= 9
                  else "long, moonless nights: ideal for deep-sky photography and spotting faint aurora")
        out.append(_ev("New Moon: dark-sky window", t.date(),
                       f"No moon to wash out the stars for the few nights either side. {season}. "
                       f"Exmoor, the Brecon Beacons and Galloway are International Dark Sky Reserves.",
                       notes=f"Exact new moon: {t:%a %d %b %Y %H:%M %Z}.", key=f"sky|newmoon|{t.date().isoformat()}"))
        d = ephem.Date(d + 1)
    return out


def seasons(lo: dt.date, hi: dt.date):
    out = []
    d = ephem.Date(lo.strftime("%Y/%m/%d"))
    while True:
        eq = ephem.next_equinox(d)
        so = ephem.next_solstice(d)
        nxt = min(eq, so)
        t = _ukdate(nxt)
        if t.date() > hi:
            break
        m = t.month
        if m == 3:
            title, hook = "March Equinox: spring begins", "Day and night roughly equal. Equinoxes also tilt the odds towards geomagnetic storms (the Russell–McPherron effect), so it's a good fortnight for aurora alerts. Also Nowruz, Persian New Year."
        elif m == 6:
            title, hook = "Summer Solstice: longest day", "Peak daylight: northern Scotland barely gets dark at all. Sunrise at Stonehenge lines up with the Heel Stone, and the free solstice open access draws thousands."
        elif m == 9:
            title, hook = "September Equinox: autumn begins", "Equal day and night, and the start of the equinox aurora boost. Also the gateway to proper dark-sky season."
        else:
            title, hook = "Winter Solstice: shortest day", "The turning point. Stonehenge and Newgrange both frame the midwinter sun. From here the evenings start getting lighter."
        out.append(_ev(title, t.date(), hook, notes=f"Exact moment: {t:%a %d %b %Y %H:%M %Z}.",
                       key=f"sky|season|{t.date().isoformat()}"))
        d = ephem.Date(nxt + 1)
    return out


def meteor_showers(lo: dt.date, hi: dt.date):
    out = []
    for y in range(lo.year, hi.year + 1):
        for name, m, day, zhr, hook in METEOR_SHOWERS:
            d = dt.date(y, m, day)
            if not (lo <= d <= hi):
                continue
            illum = _moon_illum(dt.datetime(y, m, day, 2, 0, tzinfo=UTC) + dt.timedelta(days=1))
            if illum < 25:
                moon = f"🌑 Moon only {illum:.0f}% lit: excellent, dark skies."
            elif illum < 60:
                moon = f"🌓 Moon {illum:.0f}% lit: decent, observe while it's below the horizon."
            else:
                moon = f"🌕 Moon {illum:.0f}% lit: the moonlight will drown the fainter meteors; look for fireballs."
            out.append(_ev(f"{name} meteor shower peak", d,
                           f"{hook} Up to ~{zhr}/hr under perfect skies (realistically a fraction of that). {moon}",
                           notes="Peak night shown; the night either side is usually worthwhile too.",
                           status="estimated", key=f"sky|meteor|{name}|{y}",
                           url="https://www.imo.net/resources/calendar/"))
    return out


def oppositions(lo: dt.date, hi: dt.date):
    out = []
    bodies = {"Mars": (ephem.Mars, "Mars at its closest and brightest, glowing orange all night. Even small telescopes can pick out the polar cap."),
              "Jupiter": (ephem.Jupiter, "Jupiter at its biggest and brightest, up all night. Binoculars show the four Galilean moons lined up."),
              "Saturn": (ephem.Saturn, "Saturn at its best for the year, rising at sunset. Any telescope shows the rings."),
              }
    for name, (cls, hook) in bodies.items():
        prev, prev2 = None, None
        d = lo - dt.timedelta(days=2)
        while d <= hi + dt.timedelta(days=1):
            b = cls(d.strftime("%Y/%m/%d"))
            el = abs(math.degrees(float(b.elong)))
            if prev is not None and prev2 is not None and prev > el and prev > prev2 and prev > 170:
                od = d - dt.timedelta(days=1)
                if lo <= od <= hi:
                    out.append(_ev(f"{name} at opposition", od, hook,
                                   notes="Opposition: the planet is opposite the Sun, so it's visible all night and at its brightest. Good for a couple of weeks either side.",
                                   key=f"sky|opp|{name}|{od.isoformat()}"))
            prev2, prev = prev, el
            d += dt.timedelta(days=1)
    return out


def clock_changes(lo: dt.date, hi: dt.date):
    import calendar as pc
    out = []
    for y in range(lo.year, hi.year + 1):
        for m, title, hook in ((3, "Clocks go forward (BST begins)", "Lose an hour in bed, gain light evenings. Sunsets jump past 7pm."),
                               (10, "Clocks go back (GMT returns)", "Extra hour in bed. Darker evenings mean stargazing before dinner.")):
            last = dt.date(y, m, pc.monthrange(y, m)[1])
            d = last - dt.timedelta(days=(last.weekday() - 6) % 7)
            if lo <= d <= hi:
                out.append(_ev(title, d, hook, location="UK", key=f"sky|clocks|{d.isoformat()}"))
    return out


def computed_events(lo: dt.date, hi: dt.date):
    return (full_and_new_moons(lo, hi) + seasons(lo, hi) + meteor_showers(lo, hi)
            + oppositions(lo, hi) + clock_changes(lo, hi))
