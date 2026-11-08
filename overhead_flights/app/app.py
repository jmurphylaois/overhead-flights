"""Overhead Flights — live map of aircraft passing over your house.

Desktop:  python app.py            (opens http://127.0.0.1:8750 in your browser)
          python app.py --lan      (also reachable from phones/tablets on your network)
          Settings live in config.json in the data folder (OF_DATA_DIR, default: this folder).

Home Assistant add-on: settings come from the add-on's Configuration tab (/data/options.json),
data is kept in /data, and the home location defaults to Home Assistant's own.
"""
import argparse
import gzip
import re
import atexit
import signal
import sys
import json
import math
import os
import threading
import time
import webbrowser
import urllib.error
import urllib.request
from datetime import datetime, date
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from FlightRadarAPI import FlightRadar24API

ROOT = Path(__file__).resolve().parent                      # code + static files
ADDON_OPTIONS = Path("/data/options.json")
IS_ADDON = ADDON_OPTIONS.exists()
DATA = Path("/data") if IS_ADDON else Path(os.environ.get("OF_DATA_DIR", ROOT))
CONFIG_PATH = DATA / "config.json"
LOG_PATH = DATA / "passes.jsonl"

DEFAULT_CONFIG = {
    "home_name": "Home",
    "data_source": "adsb_lol",   # "adsb_lol" (open data, default) or "fr24_web" (FlightRadar24's website feed)
    "latitude": 53.0388414,
    "longitude": -7.3034089,
    "radius_km": 110,       # how far out to show aircraft (110 km takes in Dublin Airport)
    "overhead_km": 5,       # within this horizontal distance counts as "overhead"
    "refresh_seconds": 10,
    "tour_seconds": 5,      # how long Tour mode stays on each flight
    "home_elevation_m": 90, # ground height at the house, for look-up angles
    "ahead_minutes": 5,     # length of the "where it's going" projection lines
    "night_dim": [22, 7],   # wall mode dims between these hours (24h clock)
    "airports": [],         # e.g. [{"name": "Dublin Airport", "iata": "DUB", "lat": 53.4213, "lon": -6.2701}]
    "port": 8750,
}


def ha_location():
    """Inside the add-on: ask Home Assistant for its configured home location."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        print("No SUPERVISOR_TOKEN available; cannot read Home Assistant's location", flush=True)
        return {}
    try:
        req = urllib.request.Request("http://supervisor/core/api/config",
                                     headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req, timeout=15) as r:
            c = json.load(r)
        return {"latitude": c["latitude"], "longitude": c["longitude"],
                "home_name": c.get("location_name") or "Home", "elevation": c.get("elevation")}
    except Exception as e:  # noqa: BLE001
        print("Could not read Home Assistant location:", e, flush=True)
        return {}


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if IS_ADDON:
        opts = json.loads(ADDON_OPTIONS.read_text())
        loc = ha_location()
        cfg.update({k: v for k, v in opts.items() if v not in (None, "") and k not in ("night_dim_start", "night_dim_end")})
        cfg["night_dim"] = [opts.get("night_dim_start", 22), opts.get("night_dim_end", 7)]
        if not opts.get("latitude") or not opts.get("longitude"):
            if not loc:
                raise SystemExit("No home location: set latitude/longitude in the add-on configuration.")
            cfg["latitude"], cfg["longitude"] = loc["latitude"], loc["longitude"]
        cfg["home_name"] = loc.get("home_name", "Home")
        if opts.get("home_elevation_m") in (None, "") and loc.get("elevation") is not None:
            cfg["home_elevation_m"] = loc["elevation"]
        return cfg
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    cfg.update(json.loads(CONFIG_PATH.read_text()))
    return cfg


CFG = load_config()
api = FlightRadar24API()
app = Flask(__name__, static_folder=str(ROOT / "static"))
lock = threading.Lock()


# ---------- geometry ----------
def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass(deg):
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) // 45) % 8]


def compass16(deg):
    pts = "N NNE NE ENE E ESE SE SSE S SSW SW WSW W WNW NW NNW".split()
    return pts[int((deg + 11.25) // 22.5) % 16]


def elevation_angle(dist_km, alt_ft):
    """Degrees above the horizon you'd look to see the plane (allowing for the Earth's curve)."""
    d = max(dist_km * 1000, 1.0)
    h = alt_ft * 0.3048 - CFG.get("home_elevation_m", 0)
    drop = d * d / (2 * 6371000 * 1.17)   # curvature, with standard atmospheric refraction
    return round(math.degrees(math.atan2(h - drop, d)), 1)


def closest_approach(dist_km, brg_to_plane, heading, speed_kt):
    """Predict closest horizontal pass distance and minutes until it, assuming a straight track."""
    # angle between the plane's heading and the direction from plane back to home
    to_home = (brg_to_plane + 180) % 360
    diff = math.radians(((heading - to_home + 540) % 360) - 180)
    along = dist_km * math.cos(diff)          # km still to travel toward the closest point
    cross = abs(dist_km * math.sin(diff))     # km off to the side at closest point
    if along <= 0 or speed_kt < 50:
        return round(dist_km, 1), None        # moving away / slow: closest is now
    mins = along / (speed_kt * 1.852) * 60
    return round(cross, 1), round(mins, 1)


# ---------- rate limiting ----------
class RateLimiter:
    """Non-blocking sliding-window limiter: try_acquire() is True if a request may be made now."""
    def __init__(self, per_minute):
        self.per_minute, self.stamps, self.lock = per_minute, [], threading.Lock()
        self.paused_until = 0.0

    def try_acquire(self):
        now = time.time()
        with self.lock:
            if now < self.paused_until:
                return False
            self.stamps = [t for t in self.stamps if now - t < 60]
            if len(self.stamps) >= self.per_minute:
                return False
            self.stamps.append(now)
            return True

    def pause(self, seconds):
        self.paused_until = time.time() + seconds


free_limiter = RateLimiter(8)                                   # FR24 public feed details
paid_limiter = RateLimiter(CFG.get("fr24_api_per_minute", 8))   # official API (key allows 10/min)


# ---------- official FR24 API (your key) — used sparingly: names (1 credit) and tracks (40 credits) ----------
def fr24_get(path):
    key = CFG.get("fr24_api_key")
    if not key or not paid_limiter.try_acquire():
        return None
    req = urllib.request.Request("https://fr24api.flightradar24.com/api" + path, headers={
        "Authorization": "Bearer " + key, "Accept-Version": "v1",
        "Accept": "application/json", "User-Agent": "overhead-flights/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            paid_limiter.pause(65)
        return {"_error": e.code}
    except Exception:  # noqa: BLE001
        return {"_error": "network"}


# airline / airport names never change, so keep them on disk and only ever look each one up once
NAMES_PATH = DATA / "names_cache.json"
try:
    NAMES = json.loads(NAMES_PATH.read_text())
except (OSError, ValueError):
    NAMES = {}
NAMES.setdefault("airlines", {})
NAMES.setdefault("airports", {})
name_failed = {}   # code -> time of a failed lookup, so we don't retry endlessly


def save_names():
    NAMES_PATH.write_text(json.dumps(NAMES, indent=1, sort_keys=True))


def lookup_name(kind, code):
    """kind is 'airlines' (ICAO code) or 'airports' (IATA code). Returns True if a request was used."""
    d = fr24_get(f"/static/{kind}/{code}/light")
    if d is None:
        return False
    if "_error" in d:
        name_failed[(kind, code)] = time.time()
    else:
        NAMES[kind][code] = {k: d.get(k) for k in ("name", "iata", "icao")}
        save_names()
    return True


# ---------- per-flight details from the public feed (photo, times, airport cities, full track) ----------
static_cache = {}   # flight id -> dict
trail_cache = {}    # flight id -> (fetched_at, details)
paid_tracks = {}    # flight id -> (fetched_at, track points) from the official API
history = {}        # flight id -> positions we've seen ourselves (fallback track)
wanted = []         # flight ids the browser asked about most recently (looked up first)


def fetch_details(fid):
    if not free_limiter.try_acquire():
        raise RuntimeError("rate limited, waiting")
    class _F:  # get_flight_details only needs .id
        id = fid
    try:
        return api.get_flight_details(_F)
    except Exception as e:
        if "429" in str(e):
            free_limiter.pause(120)
        raise


def summarise_details(d):
    g = lambda *ks: _dig(d, *ks)
    def airport(side):
        a = g("airport", side) or {}
        pos = a.get("position") or {}
        return {
            "name": a.get("name"),
            "iata": (a.get("code") or {}).get("iata"),
            "city": (pos.get("region") or {}).get("city"),
            "country": (pos.get("country") or {}).get("name"),
            "lat": pos.get("latitude"),
            "lon": pos.get("longitude"),
        }
    thumbs = g("aircraft", "images", "medium") or g("aircraft", "images", "thumbnails") or []
    t = g("time") or {}
    return {
        "airline": g("airline", "name"),
        "aircraft": g("aircraft", "model", "text"),
        "origin": airport("origin"),
        "destination": airport("destination"),
        "photo": thumbs[0]["src"] if thumbs else None,
        "photo_credit": thumbs[0].get("copyright") if thumbs else None,
        "status": g("status", "text"),
        "dep_scheduled": _dig(t, "scheduled", "departure"),
        "dep_actual": _dig(t, "real", "departure"),
        "arr_scheduled": _dig(t, "scheduled", "arrival"),
        "arr_estimated": _dig(t, "estimated", "arrival") or _dig(t, "other", "eta"),
    }


def _dig(d, *keys):
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def try_free_details(fid):
    try:
        d = fetch_details(fid)
    except Exception:  # noqa: BLE001
        return False
    static_cache[fid] = summarise_details(d)
    trail_cache[fid] = (time.time(), d)
    return True


def enricher():
    """Background worker: fills in names and details a little at a time, inside both rate limits."""
    while True:
        try:
            with lock:
                flights = list(feed["flights"])
            now = time.time()
            # 1) airline + airport names via the official API (1 credit each, cached forever)
            for kind, codes in (("airlines", [f["airline_icao"] for f in flights]),
                                ("airports", [c for f in flights for c in (f["origin"], f["destination"])])):
                for code in dict.fromkeys(c for c in codes if c):
                    if code not in NAMES[kind] and now - name_failed.get((kind, code), 0) > 3600:
                        lookup_name(kind, code)
            order = [i for i in wanted if i] + [f["id"] for f in flights]
            if CFG.get("data_source") == "fr24_web":
                # 2) photo/times/airport cities from FR24's public feed: flights being viewed first
                for fid in dict.fromkeys(order):
                    if fid not in static_cache and any(f["id"] == fid for f in flights):
                        if not try_free_details(fid):
                            break
            else:
                # 2) open data: routes from adsbdb, tracks + model names from adsb.lol
                by_id = {f["id"]: f for f in flights}
                for fid in dict.fromkeys(order):
                    f = by_id.get(fid)
                    if not f:
                        continue
                    if f["callsign"] and f["callsign"] not in adsb_route and not fetch_route(f["callsign"]):
                        break
                    if fid not in adsb_trace and not f["on_ground"] and not fetch_trace(fid):
                        break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)


# ---------- overhead pass log ----------
active_passes = {}  # flight id -> best record while it is within overhead_km


def log_passes(flights):
    seen = set()
    for f in flights:
        if f["distance_km"] <= CFG["overhead_km"] and not f["on_ground"]:
            seen.add(f["id"])
            rec = active_passes.get(f["id"])
            if rec is None or f["distance_km"] < rec["distance_km"]:
                active_passes[f["id"]] = {
                    "id": f["id"], "time": datetime.now().isoformat(timespec="seconds"),
                    "callsign": f["callsign"], "flight": f["number"], "airline": f.get("airline"),
                    "from": f["origin"], "to": f["destination"], "aircraft": f.get("aircraft") or f["aircraft_code"],
                    "registration": f["registration"], "altitude_ft": f["altitude_ft"],
                    "distance_km": f["distance_km"],
                }
    # flights that have left the overhead zone: write their closest approach to disk
    for fid in list(active_passes):
        if fid not in seen:
            with LOG_PATH.open("a") as fh:
                fh.write(json.dumps(active_passes.pop(fid)) + "\n")


def todays_passes():
    today = date.today().isoformat()
    out = []
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text().splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r["time"].startswith(today):
                out.append(r)
    out += list(active_passes.values())
    return sorted(out, key=lambda r: r["time"], reverse=True)


# ---------- every flight seen (for the stats page) ----------
SIGHT_PATH = DATA / "sightings.jsonl"
HEAT_PATH = DATA / "heatmap.json"
active_sight = {}   # flight id -> running record while it is in range


def log_sightings(flights):
    now = int(time.time())
    live = set()
    for f in flights:
        live.add(f["id"])
        r = active_sight.get(f["id"])
        if r is None:
            r = active_sight[f["id"]] = {
                "id": f["id"], "first": now, "min_dist": 1e9, "min_alt": None, "ground_only": True}
        r.update(last=now, callsign=f["callsign"], number=f["number"], registration=f["registration"],
                 airline_icao=f["airline_icao"], type=f["aircraft_code"],
                 origin=f["origin"], destination=f["destination"])
        if f.get("airline"): r["airline"] = f["airline"]
        if f.get("aircraft"): r["aircraft"] = f["aircraft"]
        if not f["on_ground"]:
            r["ground_only"] = False
            if f["distance_km"] < r["min_dist"]:
                r.update(min_dist=f["distance_km"], alt_at_min=f["altitude_ft"], max_elev=f["elevation_deg"])
            if r["min_alt"] is None or f["altitude_ft"] < r["min_alt"]:
                r["min_alt"] = f["altitude_ft"]
    for fid in [k for k in active_sight if k not in live]:
        r = active_sight.pop(fid)
        if r["min_dist"] < 1e9:          # skip aircraft only ever seen parked
            with SIGHT_PATH.open("a") as fh:
                fh.write(json.dumps(r) + "\n")


# heatmap: count airborne positions on a ~2 km grid, sampled every 30 s
HEAT_CELL = 0.02
try:
    HEAT = json.loads(HEAT_PATH.read_text())
except (OSError, ValueError):
    HEAT = {"since": int(time.time()), "cells": {}}
_heat_last = {"sample": 0.0, "save": time.time()}


def add_heat(flights):
    now = time.time()
    if now - _heat_last["sample"] < 30:
        return
    _heat_last["sample"] = now
    for f in flights:
        if not f["on_ground"]:
            k = f"{round(f['lat'] / HEAT_CELL)},{round(f['lon'] / HEAT_CELL)}"
            HEAT["cells"][k] = HEAT["cells"].get(k, 0) + 1
    if now - _heat_last["save"] > 300:
        HEAT_PATH.write_text(json.dumps(HEAT))
        _heat_last["save"] = now


def save_on_exit():
    try:
        HEAT_PATH.write_text(json.dumps(HEAT))
        with SIGHT_PATH.open("a") as fh:
            for r in active_sight.values():
                if r["min_dist"] < 1e9:
                    fh.write(json.dumps(r) + "\n")
        active_sight.clear()
    except OSError:
        pass


atexit.register(save_on_exit)
# make a normal stop (logout, shutdown, kill) run the save too, not just Ctrl+C
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))


def read_sightings():
    out = []
    if SIGHT_PATH.exists():
        for line in SIGHT_PATH.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out + [dict(r) for r in active_sight.values() if r["min_dist"] < 1e9]


def compute_stats(days):
    allrecs = read_sightings()
    cutoff = time.time() - days * 86400
    recs = [r for r in allrecs if r["first"] >= cutoff]
    ov = CFG["overhead_km"]
    lt = time.localtime
    def name(r):
        return r.get("airline") or (NAMES["airlines"].get(r.get("airline_icao") or "") or {}).get("name") \
            or r.get("airline_icao") or "Private / unknown"
    # per-day counts for the selected window
    by_day = {}
    for i in range(days - 1, -1, -1):
        by_day[time.strftime("%Y-%m-%d", lt(time.time() - i * 86400))] = {"all": 0, "overhead": 0}
    hours = [0] * 24
    airlines, types = {}, {}
    # friendly model name per ICAO type code (e.g. B738 -> "Boeing 737-8AS"), from any record that has one
    model = {}
    for r in allrecs:
        if r.get("type") and r.get("aircraft"):
            model[r["type"]] = r["aircraft"]
    tname = lambda r: model.get(r.get("type")) or r.get("aircraft") or r.get("type") or "Unknown"
    for r in recs:
        d = time.strftime("%Y-%m-%d", lt(r["first"]))
        if d in by_day:
            by_day[d]["all"] += 1
            by_day[d]["overhead"] += r["min_dist"] <= ov
        hours[lt(r["first"]).tm_hour] += 1
        airlines[name(r)] = airlines.get(name(r), 0) + 1
        t = tname(r)
        types[t] = types.get(t, 0) + 1
    top = lambda d, n=10: sorted(d.items(), key=lambda kv: -kv[1])[:n]
    overhead = [r for r in recs if r["min_dist"] <= ov]
    lowest = sorted(overhead, key=lambda r: r.get("alt_at_min") or 0)[:8]
    # rarest: aircraft types seen only once in the whole history, most recent first
    all_types = {}
    for r in allrecs:
        if r.get("type"):
            all_types[r["type"]] = all_types.get(r["type"], 0) + 1
    rare = [r | {"aircraft": tname(r)} for r in allrecs if r.get("type") and all_types[r["type"]] == 1]
    rare = sorted(rare, key=lambda r: -r["first"])[:8]
    slim = lambda r: {k: r.get(k) for k in ("number", "callsign", "registration", "airline_icao", "type", "aircraft",
                                            "origin", "destination", "first", "min_dist", "alt_at_min", "max_elev")} | {"airline": name(r)}
    heat = []
    for k, c in HEAT["cells"].items():
        a, b = k.split(",")
        heat.append([round(int(a) * HEAT_CELL, 3), round(int(b) * HEAT_CELL, 3), c])
    return {
        "days": days, "total": len(recs), "overhead_total": len(overhead),
        "collecting_since": min([r["first"] for r in allrecs], default=int(time.time())),
        "heat_since": HEAT["since"],
        "by_day": [{"day": d, **v} for d, v in by_day.items()],
        "by_hour": hours,
        "airlines": top(airlines), "types": top(types),
        "lowest": [slim(r) for r in lowest], "rare": [slim(r) for r in rare],
        "heat": heat,
    }


# ---------- adsb.lol / adsbdb / planespotters (open data source) ----------
UA = {"User-Agent": "overhead-flights/1.1 (+https://github.com/jmurphylaois/overhead-flights)"}
open_limiter = RateLimiter(30)     # adsbdb route lookups + adsb.lol trace files
photo_limiter = RateLimiter(20)    # planespotters.net
adsb_route = {}   # callsign -> adsbdb flightroute dict, or {} when unknown
adsb_trace = {}   # hex -> (fetched_at, model description, [[lat, lon, alt, ts], ...])
adsb_photo = {}   # hex -> {"src", "credit", "link"} or {}
adsb_latest = {}  # hex -> latest position object (for detail requests)


def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={**UA, "Accept": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return json.loads(raw)


class Pos:
    """One aircraft position, with the same attribute names as FlightRadarAPI's Flight objects."""
    def __init__(self, **kw):
        self.__dict__.update(kw)


def fetch_positions_adsb():
    lat, lon = CFG["latitude"], CFG["longitude"]
    nm = min(250, int(CFG["radius_km"] / 1.852) + 1)
    j = http_json(f"https://api.adsb.lol/v2/point/{lat}/{lon}/{nm}")
    now = time.time()
    out = []
    for a in j.get("ac", []):
        if "lat" not in a or a.get("seen_pos", 0) > 60:
            continue
        # skip airport ground vehicles and obstacles (ADS-B categories C1-C7) and blank transponders
        if str(a.get("category", "")).startswith("C") or (a.get("flight") or "").strip() in ("00000000", ""
           ) and a.get("alt_baro") == "ground" and not a.get("t"):
            continue
        cs = (a.get("flight") or "").strip()
        if cs and set(cs) <= {"0"}:
            cs = ""                       # blank transponder callsign
        alt = a.get("alt_baro")
        ground = alt == "ground"
        icao = cs[:3] if re.match(r"^[A-Z]{3}\d", cs) else None
        p = Pos(id=a["hex"], latitude=a["lat"], longitude=a["lon"], heading=round(a.get("track", a.get("true_heading", 0)) or 0),
                altitude=0 if ground else int(alt or a.get("alt_geom") or 0), ground_speed=round(a.get("gs") or 0),
                vertical_speed=int(a.get("baro_rate", a.get("geom_rate", 0)) or 0), on_ground=1 if ground else 0,
                squawk=a.get("squawk", ""), aircraft_code=a.get("t") or "", registration=a.get("r") or "",
                callsign=cs, airline_icao=icao, airline_iata=None, number="",
                origin_airport_iata="", destination_airport_iata="", time=int(now - a.get("seen_pos", 0)))
        info = adsb_info(p)
        p.number = info.get("number") or ""
        p.airline_iata = info.get("airline_iata")
        p.origin_airport_iata = (info.get("origin") or {}).get("iata") or ""
        p.destination_airport_iata = (info.get("destination") or {}).get("iata") or ""
        adsb_latest[p.id] = p
        out.append(p)
    return out


def route_plausible(o, d, lat, lon):
    """Route databases go stale (callsigns get reused), so reject a route the plane clearly isn't flying."""
    try:
        if haversine_km(lat, lon, o["latitude"], o["longitude"]) < 40 or haversine_km(lat, lon, d["latitude"], d["longitude"]) < 40:
            return True
        R = 6371.0
        d13 = haversine_km(o["latitude"], o["longitude"], lat, lon)
        d12 = haversine_km(o["latitude"], o["longitude"], d["latitude"], d["longitude"])
        t13 = math.radians(bearing_deg(o["latitude"], o["longitude"], lat, lon))
        t12 = math.radians(bearing_deg(o["latitude"], o["longitude"], d["latitude"], d["longitude"]))
        xt = math.asin(math.sin(d13 / R) * math.sin(t13 - t12)) * R      # km off the great-circle route
        return abs(xt) < 150 and d13 < d12 + 100
    except (KeyError, TypeError, ValueError):
        return True


def adsb_info(p):
    """Airline, route, aircraft model and photo for one aircraft, from the caches the enricher fills."""
    r = adsb_route.get(p.callsign) or {}
    al = r.get("airline") or {}
    o, d = r.get("origin") or {}, r.get("destination") or {}
    ok = bool(o and d) and route_plausible(o, d, p.latitude, p.longitude)
    ap = lambda a: {"name": a.get("name"), "iata": a.get("iata_code"), "city": a.get("municipality"),
                    "country": a.get("country_name"), "lat": a.get("latitude"), "lon": a.get("longitude")}
    names_al = (NAMES["airlines"].get(p.airline_icao or "") or {})
    model = (adsb_trace.get(p.id) or (0, None, None))[1]
    ph = adsb_photo.get(p.id) or {}
    return {
        "airline": al.get("name") or names_al.get("name"), "airline_iata": al.get("iata") or names_al.get("iata"),
        "number": r.get("callsign_iata") or "",
        "aircraft": model, "origin": ap(o) if ok else {}, "destination": ap(d) if ok else {},
        "photo": ph.get("src"), "photo_credit": ph.get("credit"), "photo_link": ph.get("link"),
    }


def fetch_route(cs):
    if not re.match(r"^[A-Z0-9]{3,8}$", cs):
        adsb_route[cs] = {}
        return True
    if not open_limiter.try_acquire():
        return False
    try:
        adsb_route[cs] = http_json(f"https://api.adsbdb.com/v0/callsign/{cs}")["response"]["flightroute"]
    except urllib.error.HTTPError as e:
        adsb_route[cs] = {}
        if e.code == 429:
            open_limiter.pause(60)
    except Exception:  # noqa: BLE001
        adsb_route[cs] = {}
    return True


def fetch_trace(hexid):
    """Today's track for one aircraft from adsb.lol, trimmed to the current flight."""
    if not open_limiter.try_acquire():
        return False
    try:
        j = http_json(f"https://adsb.lol/data/traces/{hexid[-2:]}/trace_full_{hexid}.json")
    except Exception:  # noqa: BLE001
        adsb_trace[hexid] = (time.time(), None, [])
        return True
    base = j.get("timestamp", 0)
    pts = []
    for row in j.get("trace", []):
        alt = row[3]
        pts.append([row[1], row[2], 0 if alt == "ground" or alt is None else alt, int(base + row[0])])
    # keep only the current leg: walk back from the end until a long gap or the plane was on the ground
    start = len(pts) - 1
    while start > 0 and pts[start][3] - pts[start - 1][3] < 1200 and pts[start - 1][2] > 0:
        start -= 1
    desc = j.get("desc")
    if desc:
        # "BOEING 737 MAX 8" -> "Boeing 737 MAX 8"
        desc = " ".join(w.capitalize() if w.isalpha() and w != "MAX" else w for w in desc.split())
    adsb_trace[hexid] = (time.time(), desc, thin(pts[start:], 400))
    return True


def fetch_photo(p):
    if p.id in adsb_photo:
        return
    if not photo_limiter.try_acquire():
        return
    try:
        ph = (http_json(f"https://api.planespotters.net/pub/photos/hex/{p.id}").get("photos") or [])
        if not ph and p.registration:
            ph = http_json(f"https://api.planespotters.net/pub/photos/reg/{p.registration}").get("photos") or []
        adsb_photo[p.id] = {"src": ph[0]["thumbnail_large"]["src"], "credit": ph[0].get("photographer"),
                            "link": ph[0].get("link")} if ph else {}
    except Exception:  # noqa: BLE001
        adsb_photo[p.id] = {}


def adsb_track(fid, refresh=False):
    got = adsb_trace.get(fid)
    if got is None or (refresh and time.time() - got[0] > 60):
        fetch_trace(fid)
        got = adsb_trace.get(fid)
    return list(got[2]) if got else []


# ---------- live feed ----------
feed = {"fetched": 0, "flights": [], "error": None}


def refresh_feed():
    lat, lon = CFG["latitude"], CFG["longitude"]
    if CFG.get("data_source") == "fr24_web":
        raw = api.get_flights(bounds=api.get_bounds_by_point(lat, lon, CFG["radius_km"] * 1000))
    else:
        raw = fetch_positions_adsb()
    flights = []
    for f in raw:
        dist = haversine_km(lat, lon, f.latitude, f.longitude)
        if dist > CFG["radius_km"]:
            continue
        brg = bearing_deg(lat, lon, f.latitude, f.longitude)
        cpa_km, cpa_min = closest_approach(dist, brg, f.heading, f.ground_speed)
        info = (static_cache.get(f.id) or {}) if CFG.get("data_source") == "fr24_web" else adsb_info(f)
        al = NAMES["airlines"].get(f.airline_icao) or {}
        ap_o = NAMES["airports"].get(f.origin_airport_iata) or {}
        ap_d = NAMES["airports"].get(f.destination_airport_iata) or {}
        flights.append({
            "id": f.id, "callsign": f.callsign or "", "number": f.number or "",
            "lat": f.latitude, "lon": f.longitude, "heading": f.heading,
            "altitude_ft": f.altitude, "speed_kt": f.ground_speed, "vspeed_fpm": f.vertical_speed,
            "on_ground": bool(f.on_ground), "squawk": f.squawk,
            "aircraft_code": f.aircraft_code, "registration": f.registration,
            "origin": f.origin_airport_iata, "destination": f.destination_airport_iata,
            "airline_icao": f.airline_icao, "airline_iata": f.airline_iata or al.get("iata"),
            "airline": info.get("airline") or al.get("name"), "aircraft": info.get("aircraft"),
            "origin_city": _dig(info, "origin", "city") or ap_o.get("name"),
            "destination_city": _dig(info, "destination", "city") or ap_d.get("name"),
            "distance_km": round(dist, 1), "bearing": round(brg), "direction": compass(brg),
            "look_dir": compass16(brg), "elevation_deg": elevation_angle(dist, f.altitude or 0),
            "cpa_km": cpa_km, "cpa_min": cpa_min,
        })
        h = history.setdefault(f.id, [])
        if not h or h[-1][3] != f.time:
            h.append([f.latitude, f.longitude, f.altitude, f.time])
    flights.sort(key=lambda x: x["distance_km"])
    live_cs = {f["callsign"] for f in flights}
    for cs in [c for c in adsb_route if c not in live_cs]:
        adsb_route.pop(cs, None)
    log_passes(flights)
    log_sightings(flights)
    add_heat(flights)
    # forget cached info for flights no longer around
    live = {f["id"] for f in flights}
    for cache in (static_cache, trail_cache, paid_tracks, history, adsb_trace, adsb_photo, adsb_latest):
        for fid in [k for k in cache if k not in live]:
            cache.pop(fid, None)
    return flights


def poller():
    backoff = 0
    while True:
        try:
            flights = refresh_feed()
            with lock:
                feed.update(fetched=time.time(), flights=flights, error=None)
            backoff = 0
        except Exception as e:  # noqa: BLE001
            with lock:
                feed["error"] = f"{type(e).__name__}: {e}"
            # rate limited: back off 30s, 60s, 120s... (max 5 min) and pause detail lookups too
            if "429" in str(e):
                backoff = min(300, max(30, backoff * 2))
                free_limiter.pause(backoff)
                print(f"FR24 feed rate-limited; waiting {backoff}s", flush=True)
        time.sleep(max(5, CFG["refresh_seconds"], backoff))


# ---------- HTTP ----------
@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/stats")
def stats_page():
    return send_from_directory(app.static_folder, "stats.html")


@app.get("/wall")
def wall_page():
    return send_from_directory(app.static_folder, "index.html")


@app.get("/embed")
def embed_page():
    """Compact view for a dashboard card: map + small touring flight card, no side panel."""
    return send_from_directory(app.static_folder, "index.html")


@app.get("/api/stats")
def api_stats():
    days = max(1, min(int(request.args.get("days", 7)), 365))
    return jsonify(compute_stats(days))


@app.get("/api/config")
def api_config():
    return jsonify({k: CFG[k] for k in ("home_name", "latitude", "longitude", "radius_km", "overhead_km", "refresh_seconds", "tour_seconds", "airports",
                                  "ahead_minutes", "night_dim", "home_elevation_m", "data_source")})


@app.get("/api/flights")
def api_flights():
    with lock:
        return jsonify({**feed, "passes_today": todays_passes()})


def thin(points, max_pts=160):
    """Downsample a track (keeping first and last points) so drawing every flight stays fast."""
    if len(points) <= max_pts:
        return points
    step = len(points) / (max_pts - 1)
    return [points[int(i * step)] for i in range(max_pts - 1)] + [points[-1]]


@app.get("/api/paths")
def api_paths():
    """Track for every live flight: the public-feed trail when we have it, else positions we've recorded."""
    with lock:
        live = [f["id"] for f in feed["flights"]]
    out = {}
    adsb = CFG.get("data_source") != "fr24_web"
    for fid in live:
        if adsb:
            pts = list((adsb_trace.get(fid) or (0, None, []))[2])
            last_ts = pts[-1][3] if pts else 0
            pts += [p for p in history.get(fid, []) if p[3] > last_ts]
            out[fid] = [[round(p[0], 4), round(p[1], 4), p[2]] for p in thin(pts)]
            continue
        _, d = trail_cache.get(fid, (0, None))
        if d is not None:
            pts = [[p["lat"], p["lng"], p.get("alt", 0), p.get("ts")] for p in reversed(d.get("trail") or [])]
        else:
            pts = list((paid_tracks.get(fid) or (0, []))[1])
        last_ts = pts[-1][3] if pts else 0
        pts += [p for p in history.get(fid, []) if p[3] > last_ts]
        out[fid] = [[round(p[0], 4), round(p[1], 4), p[2]] for p in thin(pts)]
    return jsonify(out)


def paid_track(fid):
    """Full track from the official API (40 credits) — only for flights you click on, cached 5 min."""
    got = paid_tracks.get(fid)
    if got and time.time() - got[0] < 300:
        return got[1]
    d = fr24_get(f"/flight-tracks?flight_id={fid}")
    if not d or "_error" in d or not isinstance(d, list) or not d:
        return got[1] if got else None
    pts = [[p["lat"], p["lon"], p.get("alt", 0),
            int(datetime.fromisoformat(p["timestamp"].replace("Z", "+00:00")).timestamp())]
           for p in d[0].get("tracks", [])]
    paid_tracks[fid] = (time.time(), pts)
    return pts


@app.get("/api/flight/<fid>")
def api_flight(fid):
    manual = request.args.get("manual") == "1"   # a click, not Tour mode
    wanted.insert(0, fid)
    del wanted[5:]
    if CFG.get("data_source") != "fr24_web":
        p = adsb_latest.get(fid)
        if p is None:
            return jsonify({"error": "unknown flight"}), 404
        fetch_photo(p)
        trail = adsb_track(fid, refresh=manual)
        if not trail and manual and CFG.get("use_paid_tracks", True):
            trail = paid_track(fid) or []
        last_ts = trail[-1][3] if trail else 0
        trail += [q for q in history.get(fid, []) if q[3] > last_ts]
        return jsonify({**adsb_info(p), "trail": trail, "partial": False})
    fetched, d = trail_cache.get(fid, (0, None))
    if d is None or (manual and time.time() - fetched > 60):
        try_free_details(fid)
        fetched, d = trail_cache.get(fid, (0, None))
    if d is not None:
        info = summarise_details(d)
        trail = [[p["lat"], p["lng"], p.get("alt", 0), p.get("ts")] for p in (d.get("trail") or [])]
        trail.reverse()  # FR24 returns newest first
    else:
        info = static_cache.get(fid) or {}
        trail = (paid_track(fid) if manual and CFG.get("use_paid_tracks", True) else None) \
            or (paid_tracks.get(fid, (0, None))[1]) or []
    # append newer positions from the live feed since the track was fetched
    last_ts = trail[-1][3] if trail else 0
    trail = trail + [p for p in history.get(fid, []) if p[3] > last_ts]
    return jsonify({**info, "trail": trail, "partial": d is None})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lan", action="store_true", help="listen on all interfaces so other devices can connect")
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    args = ap.parse_args()
    threading.Thread(target=poller, daemon=True).start()
    threading.Thread(target=enricher, daemon=True).start()
    host = "0.0.0.0" if (args.lan or IS_ADDON) else "127.0.0.1"
    port = 8750 if IS_ADDON else CFG["port"]
    url = f"http://127.0.0.1:{port}"
    if not args.no_browser and not IS_ADDON:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Overhead Flights running on {host}:{port} — home {CFG['latitude']:.4f},{CFG['longitude']:.4f}, "
          f"radius {CFG['radius_km']} km" + (", official FR24 key set" if CFG.get("fr24_api_key") else ""), flush=True)
    try:
        from waitress import serve
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
