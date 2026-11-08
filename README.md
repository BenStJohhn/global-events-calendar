# 🌍 Global Events Calendar

A set of calendar feeds you can subscribe to, built around my own interests: festivals around the world, motorsport, adventure sport, UK sky and nature events, and music and the arts. Each feed can be switched on or off on its own in Apple or Google Calendar.

**Subscribe:** https://benstjohhn.github.io/global-events-calendar/

| Feed | What's in it |
|---|---|
| 🎭 Cultural | Carnivals, lunar and religious festivals, folk festivals worldwide |
| 🪂 Adventure & Sport | Sailing (America's Cup, Fastnet…), paragliding (X-Alps, Coupe Icare), MTB, ultras, Tour de France GB, RWC 2027 |
| 🌌 Sky & Nature (UK) | Named full moons, supermoons, new-moon dark skies, meteor showers with moonlight rating, eclipses, oppositions, UK wildlife seasons |
| 🎸 Music & Arts | Glastonbury, Coachella, Fringe, documenta 16, Venice Biennale, Eurovision, film festivals |
| 🏁 Motorsport | F1 sprint, qualifying and race sessions; WRC; Dakar & W2RC; British GT; GTWC Europe; rallycross; bonus Le Mans and IoM TT |
| 📅 Booking Nudges | All-day reminder 90 days before every ✈️ trip-worthy event (this works in Google Calendar, which ignores alarms in subscribed feeds) |
| 🌍 Everything | All five main feeds combined |

Every entry has a hook, a confidence tag (✅ confirmed / 🟡 est. / ❓ TBC), the official link and a map pin.

## How it works
- `data/*.yaml`: curated events, with rules for recurring ones
- `generator/build.py` + `generator/sky.py`: computes the astronomy (PyEphem) and the lunar, Islamic and Hebrew calendar dates, then writes the `.ics` feeds to `docs/feeds/`
- A GitHub Action rebuilds weekly to keep the window rolling forward 18 months
- A monthly Claude scheduled task researches new and changed dates and commits updates (see `REFRESH.md`)

Local build: `pip install -r requirements.txt && python generator/build.py`
