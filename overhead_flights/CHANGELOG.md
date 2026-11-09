# Changelog

## 1.4.0
- **Ships on the map:** live AIS positions from [aisstream.io](https://aisstream.io), using a free key set in the new **AISStream API key** option.
  - Moving ships get a heading-pointed icon, a dotted trail and a smaller label, coloured by type (passenger, cargo, tanker, fishing, tug/pilot, rescue, naval, sailing).
  - Moored and anchored ships show as small dots, labelled on hover.
  - Click a ship for its speed, destination, ETA, length, call sign and a MarineTraffic link.
  - A **Ships** button turns the layer on and off. Dashboard card 1.4.0 adds `ships: true`.
  - Ship names, types and destinations are remembered in `ships_static.json`, because ships only broadcast them every few minutes.
- **Notable ships** get badges and a pulsing ring:
  - **IRISH NAVY:** Irish Naval Service "LÉ" ships, Irish-flagged only, so French "LE …" cruise ships aren't tagged.
  - **RNLI:** lifeboats.
  - **NAVY:** other navies.
  - **RESCUE:** search-and-rescue craft.
- When a notable ship is at sea, the wall view and dashboard card tour to it automatically. It gets the target ring and a ship card showing distance and direction from home.
- Notable ships seen today appear in the Today strip.

## 1.3.2
- Dashboard card 1.3.2 adds `tour_seconds`, which sets how long the tour shows each plane on that card (2–600). Without it, the card uses the add-on's Tour seconds.

## 1.3.1
- **Highlighted plane:** on a wall or card view, the plane the card is showing gets a glowing target ring with corner brackets, and its label is outlined to match.
- **More aircraft photos:**
  - When FlightRadar24 has no photo, the app looks for one on Planespotters.net by registration.
  - If there's still none, it shows a Wikipedia photo of the aircraft type, labelled "Type photo".
- **Big-screen scaling:**
  - Dashboard card 1.3.1 adds `scale` (1–4). It enlarges the flight card, labels, clock chip, alert banner and Today strip for screens read from across the room.
  - The Today strip now wraps rather than cutting off, and sits below the status chip.

## 1.3.0
- **Overhead countdown:** a banner counts down to a plane passing over the house. The tour holds on that plane and its card gets bigger until it has gone by.
- **Emergency squawks:** 7700, 7600 and 7500 get a red banner, and the tour stays on that plane.
- **Unusual aircraft** get badges and a pulsing ring on the map, and they jump the tour queue:
  - military
  - rescue and air ambulance
  - giants (A380, 747, An-124, Beluga and similar)
  - types seen for the first time, or only rarely, at your home. This only counts aircraft flying at 200 kt or more, so local light aircraft don't flood it.
- **Today strip:** shows flights, overhead passes, busiest hour, lowest pass and notable visitors. There is a new `/api/today` endpoint behind it.
- Dashboard card 1.3.0 adds new options:
  - `paths`, `alerts` and `summary`
  - `height` accepts any CSS height (e.g. `78vh`)
- The desktop version's default location is now Dublin city centre. Set your own in `config.json`.

## 1.2.0
- New `/embed` view, used by the new **Overhead Flights dashboard card** (`card/overhead-flights-card.js`) to show the live map inside any dashboard. It has:
  - a compact touring flight card
  - an "N in the air · next overhead" status chip

## 1.1.1
- The project moved to github.com/jmurphylaois/overhead-flights.
- Added step-by-step instructions for adding your own FR24 API key.

## 1.1.0
- New default data source: **adsb.lol** open data (ODbL), with routes from **adsbdb** and photos from **planespotters.net** (credited and linked).
  - It needs no API key.
  - Flight tracks come from adsb.lol and are trimmed to the current flight.
  - Routes the plane clearly isn't flying are rejected, because route databases go stale.
  - Airport ground vehicles are filtered out.
- FlightRadar24's website feed is still available as `data_source: fr24_web`, for personal use.

## 1.0.2
- When FlightRadar24 rate-limits the feed, the app now backs off automatically (30 s, doubling to 5 min) instead of retrying every 10 s.

## 1.0.1
- Fixed: the app now starts with the Supervisor environment, so it can read the home location from Home Assistant.

## 1.0.0
- First release as a Home Assistant add-on. The app opens from the sidebar via Ingress.
- Features:
  - live map
  - flight tracks and Paths view
  - airline logos
  - Tour mode
  - "What's that plane?" with a sky view and where-to-look angles
  - Ahead projection lines
  - rain radar
  - filters
  - stats page with heatmap
  - wall-screen mode
