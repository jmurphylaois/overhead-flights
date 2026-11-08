# Overhead Flights

A live map of the aircraft flying near your home. Open it from **Flights** in the Home Assistant sidebar.

## What's on the map
- **Labels** follow each plane, showing the airline logo, flight, route, altitude and speed. The button switches between full, compact and off.
- **Paths** draws the tracks of every flight.
- **Ahead** draws dashed lines showing where each plane will be shortly. The line turns orange when a plane is heading over your home.
- **Rain** overlays rain radar from RainViewer.
- **Filters** lets you hide planes on the ground, set an altitude range, pick an airport's arrivals or departures, or pick one airline.
- **Tour** shows each flight in turn.
- **Overhead alerts** count down to the next plane passing over your home. A red banner appears for emergency squawks (7700, 7600, 7500).
- **Badges** mark unusual aircraft: military, rescue, giants, and first-time or rare types. Unusual aircraft jump the tour queue.
- The **Today strip** (wall mode and dashboard card) sums up the day so far.
- **What's that plane?** shows the aircraft highest in your sky and which way to look.

## Stats
Open **Stats** from the sidebar header. It shows:
- flights per day and the busiest hours
- top airlines and aircraft
- the lowest overhead passes and rare visitors
- a heatmap of where planes fly near you

History builds up for as long as the add-on runs.

## Wall-screen mode
Open **Wall mode** for a full-screen, auto-touring view with a clock that dims at night. To show it on a tablet without logging in, set a host port for `8750/tcp` on the **Network** tab and open `http://<home-assistant-ip>:<port>/wall`.

## Adding your own FlightRadar24 API key (optional)
The add-on works without a key. An official FR24 API key improves names and tracks:
- Airline and airport names are always filled in, at 1 credit each. Each name is looked up once and then cached permanently.
- When you click a flight whose track isn't otherwise available, the add-on can fetch it, at 40 credits per track.

Live positions never use credits.

1. Get a key from the FlightRadar24 API portal at [fr24api.flightradar24.com](https://fr24api.flightradar24.com). Any plan works, including the Explorer plan.
2. Copy the API token from **Key management**. It looks like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx|xxxxxxxx…`. Copy the whole value, including the part after the `|`.
3. In Home Assistant, go to **Settings → Add-ons → Overhead Flights → Configuration**:
   - Paste the token into **FlightRadar24 API key**.
   - Set **FR24 API calls per minute** below your plan's limit. The default is 8, which suits a 10-requests-a-minute plan.
   - Turn off **Use FR24 credits for tracks** if you only want the 1-credit name lookups.
4. Click **Save**, then **Restart** the add-on. The log should say `official FR24 key set`.

The key is stored in Home Assistant's add-on configuration. It's only ever sent to `fr24api.flightradar24.com`.

## Data sources
- **`adsb_lol` (default).** It needs no key.
  - Live positions and tracks come from [adsb.lol](https://adsb.lol), a community network of ADS-B receivers. Its data is open under the ODbL.
  - Airline names and routes come from [adsbdb](https://www.adsbdb.com).
    - Callsigns get reused, so a route is only shown when the plane is actually flying it.
    - Some flights will show no route.
  - Aircraft photos come from [planespotters.net](https://www.planespotters.net), credited to the photographer and linked.
- **`fr24_web`:**
  - Uses FlightRadar24's public website feed, which has richer routes, departure/arrival times and photos.
  - It's unofficial and meant for personal use only, and FR24 may rate-limit it.
- **FR24 API key (optional):** with your own official key, the add-on also looks up airline and airport names (1 credit each, cached), and tracks of flights you click if no other track is available (40 credits).
- Airline logos come from avs.io (plus FR24's logos in `fr24_web` mode). Rain radar comes from RainViewer and the map tiles from Esri.
