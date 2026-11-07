# Changelog

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
