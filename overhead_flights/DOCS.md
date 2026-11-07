# Overhead Flights

A live map of the aircraft flying near your home. Open it from **Flights** in the Home Assistant sidebar.

## What's on the map
- **Labels** follow each plane, showing the airline logo, flight, route, altitude and speed. The button switches between full, compact and off.
- **Paths** draws the tracks of every flight.
- **Ahead** draws dashed lines showing where each plane will be shortly. The line turns orange when a plane is heading over your home.
- **Rain** overlays rain radar from RainViewer.
- **Filters** lets you hide planes on the ground, set an altitude range, pick an airport's arrivals or departures, or pick one airline.
- **Tour** shows each flight in turn.
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
