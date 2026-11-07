# Overhead Flights

A live map of the aircraft flying over your home. It runs as a **Home Assistant add-on**, with a sidebar panel through Ingress, or as a standalone desktop app on Mac, Windows or Linux.

![icon](overhead_flights/logo.png)

## Features
- Each plane appears as an icon, rotated to its heading and coloured by altitude.
- Each plane has a label that moves with it, showing the airline logo, flight number, aircraft type, route, altitude and speed. **Labels** switches between full, compact and off.
- Click a plane to see its flight track and the rest of its route. The map never re-centres itself; it stays where you put it.
- **Paths** draws every flight's track at once. Tracks cross each other, and the colour shows altitude.
- **What's that plane?** shows the plane highest in your sky right now. You get its photo, route and type, which way to look (e.g. "Look NW, 23° up"), and a sky-view compass.
- Every flight shows **where to look**: the compass direction, plus the angle above the horizon (allowing for the Earth's curve).
- **Ahead** draws a dashed line showing where each plane will be in `ahead_minutes`. The line turns orange and bold if the plane is heading over the house.
- **Rain** overlays the latest rain radar from RainViewer (free), refreshed every 10 minutes.
- **Filters:** hide planes on the ground, set a min/max altitude, show only arrivals or departures at a marked airport (or hide them), or pick one airline.
- **Stats** (`/stats`) shows:
  - flights per day and the busiest hours
  - top airlines and aircraft
  - the lowest overhead passes and rare visitors
  - a heatmap of where planes actually fly
  It builds up from `sightings.jsonl` and `heatmap.json` while the app runs.
- **Wall mode** (`/wall`) is a full-screen kiosk view. It tours automatically and shows a large flight card, a clock and the count of planes in the air. It dims between the `night_dim` hours.
- **Tour** shows each flight in turn for `tour_seconds` (default 5), nearest first, and starts again after the last one.
- Details include airline, origin and destination, aircraft type and photo, registration, altitude, speed, climb rate, and departure/arrival times.
- The app predicts how close each plane will pass and when.
- Any plane within the "overhead" radius goes into a "Passed overhead today" list, which is saved to `passes.jsonl`.

## Install as a Home Assistant add-on
[![Add repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fjmurphylaois%2Foverhead-flights)

1. Click the button above, or go to **Settings → Add-ons → Add-on Store → ⋮ → Repositories** and add `https://github.com/jmurphylaois/overhead-flights`.
2. Install **Overhead Flights** and start it. It appears as **Flights** in the sidebar.
3. Your home location comes from Home Assistant automatically. Everything else can be set on the add-on's **Configuration** tab (see [DOCS.md](overhead_flights/DOCS.md)).

The add-on supports `aarch64` (Raspberry Pi 4/5, etc.) and `amd64`.

## Run on a desktop instead
- **Mac:** double-click `run.command`, or run `./run.command` in Terminal.
- **Windows:** double-click `run.bat`. Python 3.10+ must be installed.
- **Phone or tablet on your Wi-Fi:** run `./run.command --lan`, then open `http://<computer-ip>:8750`.

The first run sets up a virtualenv. After that, the app opens at http://127.0.0.1:8750.

## Settings (`config.json`)
| key | meaning |
|---|---|
| latitude / longitude | your house location |
| radius_km | how far out to show aircraft (default 60) |
| overhead_km | distance that counts as "overhead" (default 5) |
| refresh_seconds | how often to poll the feed (default 10) |
| home_elevation_m | ground height at the house, used for look-up angles (default 90) |
| ahead_minutes | length of the Ahead projection lines (default 5) |
| night_dim | hours when wall mode dims, e.g. [22, 7] |
| tour_seconds | how long Tour stays on each flight (default 5) |
| airports | airports marked on the map (Dublin by default) |
| data_source | `adsb_lol` (default, open data) or `fr24_web` |
| fr24_api_key | optional official FR24 API key, used for airline/airport names and click-to-view tracks |
| fr24_api_per_minute | maximum official API calls per minute (default 8; the key allows 10) |
| use_paid_tracks | set to false to never spend the 40 credits a track lookup costs |
| port | web port (default 8750) |

### Adding your own FlightRadar24 API key (optional)
An official FR24 API key fills in airline and airport names (1 credit each, cached permanently). It can also fetch tracks for flights you click when no other track is available (40 credits each).
1. Get a key at [fr24api.flightradar24.com](https://fr24api.flightradar24.com), then copy the whole API token, including the part after the `|`.
2. **Home Assistant add-on:** paste the token into **FlightRadar24 API key** on the add-on's Configuration tab, then save and restart. See [DOCS.md](overhead_flights/DOCS.md#adding-your-own-flightradar24-api-key-optional).
3. **Desktop:** add the token to `config.json` next to `run.command`, then restart the app:
   ```json
   "fr24_api_key": "your-token-here",
   "fr24_api_per_minute": 8
   ```
   `config.json` is listed in `.gitignore`, so the key never gets committed.

### Official API credit use
Live positions always come from the free public feed, which costs no credits. The official key is only used for:
- **Airline and airport names:** 1 credit each. They're saved in `names_cache.json`, so each one is looked up only once.
- **Tracks for flights you click:** 40 credits each. This only happens when the free feed can't supply the track, and the result is reused for 5 minutes. Tour mode never uses it.

Polling live positions through the official API instead would cost about 112 credits every 10 seconds, so the app doesn't do that.

## Data sources
The default source is open data:
- Positions and tracks come from **[adsb.lol](https://adsb.lol)** (ODbL).
- Routes and airlines come from **[adsbdb](https://www.adsbdb.com)**.
- Photos come from **[planespotters.net](https://www.planespotters.net)**.

No key is needed. Setting `"data_source": "fr24_web"` switches to FlightRadar24's public website feed instead. That feed is unofficial and for personal use only.

An official FR24 API key is optional. If you add one, it's only used for name lookups and click-to-view tracks (see the credit notes above).

## License
MIT. See [LICENSE](LICENSE).
