#!/usr/bin/env python3
"""Runs ON THE PULSE VPS (inside the Pulse Garmin container, which has the Garmin login and mounts the dashboard folder at /work).

Exports training sessions as the data.json Pulse Studio renders from, plus the index the laptop's session picker reads.
One session = one reel: HYROX (Pulse HYROX watch app), run, ride, strength (Garmin activities of the last PULSE_EXPORT_DAYS, 30).
  python export_session.py 2026-11-01 [--type run]  -> every session of that date (or of that type) → /work/site/sessions/<date>-<type>.json
  python export_session.py <garmin activity id>     -> that one session (several of a type on one day: <date>-<type>-<id>.json)
  python export_session.py --sync                   -> export every session not exported yet (or exported before its HR arrived), rewrite index.json
  python export_session.py --index                  -> only rewrite index.json (no Garmin login)
Cron (every 10 min): */10 * * * * docker exec <garmin container> python /work/pulse-studio-server/export_session.py --sync

HYROX: laps from hyrox_watch.json, 200 m splits from erg.json (ErgData). Run/ride: the workout structure from Garmin's lap labels (warm-up, rep1..N with their recoveries, cool-down; tempo block; or distance parts for a steady run).
Strength: Garmin has no reliable exercise sets, so only totals + HR every 5 s (the laptop matches each scene's clip shoot time to it).
All: second-by-second HR from the Garmin activity details (unofficial API, same login garmin_pull.py uses), HR zones from the summary.
"""
import sys, json, os, argparse, fcntl, time
sys.path.insert(0, "/work")
SITE = "/work/site"; OUT = f"{SITE}/sessions"
DAYS = int(os.environ.get("PULSE_EXPORT_DAYS", "30"))
TYPES = {"running": "run", "treadmill_running": "run", "trail_running": "run", "track_running": "run", "virtual_run": "run",
         "road_biking": "ride", "cycling": "ride", "indoor_cycling": "ride", "mountain_biking": "ride", "gravel_cycling": "ride", "virtual_ride": "ride",
         "strength_training": "strength"}
PARTS = 8

def trace(hr, a, b, n=40):
    pts = [v for s, v in hr if a <= s <= b]
    if not pts: return []
    step = max(1, len(pts) // n)
    return [round(sum(pts[i:i + step]) / len(pts[i:i + step])) for i in range(0, len(pts), step)][:n]

def every(hr, step=5):
    """HR resampled every `step` s from the activity start (gaps carry the last value) — for matching clip shoot times."""
    b = {}
    for t, v in hr: b.setdefault(int(t // step), []).append(v)
    out, last = [], None
    for i in range(max(b) + 1 if b else 0):
        if i in b: last = round(sum(b[i]) / len(b[i]))
        out.append(last)
    return out

_G = None
def garmin():
    global _G
    if _G is None:
        import garmin_pull as gp
        _G = gp.login_or_none() or False
    return _G or None

def hr_series(aid):
    g = garmin()
    if not g: return []
    d = g.get_activity_details(int(aid), maxchart=5000, maxpoly=0)
    keys = [m["key"] for m in d.get("metricDescriptors", [])]
    ih = keys.index("directHeartRate"); it = keys.index("sumElapsedDuration") if "sumElapsedDuration" in keys else keys.index("sumDuration")
    return [[m["metrics"][it], m["metrics"][ih]] for m in d.get("activityDetailMetrics", []) if m["metrics"][ih] is not None]

def zones(act):
    return [round(act.get(f"hrTimeInZone_{i}", 0) or 0, 1) for i in range(1, 6)]

def _type_key(a):
    t = a.get("activityType")
    return t.get("typeKey") if isinstance(t, dict) else (t or a.get("type"))

def garmin_acts():
    acts = json.load(open(f"{SITE}/garmin.json")).get("activities") or {}
    return list(acts.values()) if isinstance(acts, dict) else acts

def all_sessions():
    """Every session that can become a reel: HYROX watch sessions + typed Garmin activities of the last DAYS days."""
    out = []
    try: hw = json.load(open(f"{SITE}/hyrox_watch.json"))["sessions"].values()
    except (OSError, KeyError, ValueError): hw = []
    for s in hw:
        out.append({"id": str(s["id"]), "date": s["date"], "type": "hyrox", "start": s.get("start"), "total_s": s["total_s"],
                    "avg_hr": s.get("avg_hr"), "max_hr": s.get("max_hr"), "kcal": s.get("kcal"),
                    "stations": [l["key"] for l in s["laps"] if l["key"] != "rest"], "raw": s})
    watch_ids = {x["id"] for x in out}
    since = time.strftime("%Y-%m-%d", time.localtime(time.time() - DAYS * 86400))
    for a in garmin_acts():
        typ = TYPES.get(_type_key(a)); start = str(a.get("startTimeLocal") or "")
        if not typ or str(a.get("activityId")) in watch_ids or start[:10] < since: continue
        out.append({"id": str(a["activityId"]), "date": start[:10], "type": typ, "start": start.replace(" ", "T"), "total_s": a.get("duration"),
                    "avg_hr": a.get("averageHR"), "max_hr": a.get("maxHR"), "kcal": None, "distance_m": a.get("distance") or None,
                    "name": a.get("activityName"), "stations": [], "raw": a})
    return sorted(out, key=lambda x: (x["date"], str(x.get("start") or "")))

def rel_file(s, all_s):
    same = [x for x in all_s if x["date"] == s["date"] and x["type"] == s["type"]]
    return f"sessions/{s['date']}-{s['type']}.json" if len(same) == 1 else f"sessions/{s['date']}-{s['type']}-{s['id']}.json"

def export_hyrox(s):
    date = s["date"]
    erg = json.load(open(f"{SITE}/erg.json"))
    items = erg if isinstance(erg, list) else (erg.get("items") or erg.get("results") or list(erg.values()))
    if isinstance(items, dict): items = list(items.values())
    E = {x["type"]: x for x in items if isinstance(x, dict) and str(x.get("start_utc", "")).startswith(date)}
    act = next((a for a in garmin_acts() if str(a.get("activityId")) == str(s["id"])), None) or {}
    hr = hr_series(s["id"])
    t = 0; out = {}
    for l in s["laps"]:
        a, b = t, t + l["s"]; t = b
        if l["key"] == "rest": continue
        out[l["key"]] = {"station": l["station"], "s": l["s"], "hr": l.get("hr"), "max": l.get("max"), "steps": l.get("steps"), "m": l.get("m"), "trace": trace(hr, a, b)}
    for key, et in (("skierg", "skierg"), ("row", "rower")):
        if key in out and et in E:
            e = E[et]; out[key]["splits"] = [[x["time_s"], x["pace_500"], x["spm"], x.get("avg_hr")] for x in e.get("splits", [])]
            out[key]["erg"] = [e["time_s"], e["pace_500"], e["spm"], e.get("stroke_count")]
    out["_session"] = {"date": date, "type": "hyrox", "total_s": s["total_s"], "avg_hr": s["avg_hr"], "max_hr": s["max_hr"], "kcal": s.get("kcal"),
                       "full_trace": trace(hr, 0, t, 120), "zones": zones(act), "start": s.get("start"), "start_utc": act.get("startTimeGMT"),
                       "hr5": every(hr), "order": [l["key"] for l in s["laps"] if l["key"] != "rest"], "id": str(s["id"])}
    return out

def _km(m):
    v = round(m / 1000, 1)
    return str(int(v)) if v == int(v) else str(v)

def _groups(laps, n=PARTS):
    """Contiguous groups of laps, at most n (a 20 × 1 km run → 8 parts of 2–3 km)."""
    if len(laps) <= n: return [[l] for l in laps]
    k, r = divmod(len(laps), n); out, i = [], 0
    for j in range(n):
        size = k + (1 if j < r else 0); out.append(laps[i:i + size]); i += size
    return out

def _pace(sec, m):
    if not m: return None
    v = sec / m * 1000; return f"{int(v // 60)}:{int(round(v % 60)):02d}"

def _part(key, station, laps, a, b, hr, extra=None):
    m = sum(x["m"] for x in laps); sec = sum(x["s"] for x in laps); hrs = [(x["hr"], x["s"]) for x in laps if x["hr"]]
    d = {"station": station, "s": round(sec, 1), "m": round(m), "pace": _pace(sec, m), "elev": round(sum(x["elev"] for x in laps)),
         "hr": round(sum(h * w for h, w in hrs) / sum(w for _, w in hrs)) if hrs else None, "max": max((x["max"] or 0 for x in laps), default=None) or None,
         "cad": round(sum((x["cad"] or 0) * x["s"] for x in laps) / sec) if sec and any(x["cad"] for x in laps) else None,
         "t0": round(a, 1), "t1": round(b, 1), "start_utc": laps[0].get("start_utc"),
         "laps": [[round(x["s"], 1), round(x["m"]), x["hr"]] for x in laps], "trace": trace(hr, a, b)}
    if extra: d.update(extra)
    return key, d

def run_structure(L):
    """Garmin labels every lap of a structured workout: WARMUP / ACTIVE / RECOVERY / COOLDOWN (REST, INTERVAL on some devices).
    intervals: warm-up → rep1..repN (each ACTIVE lap, with the recovery that follows it) → cool-down.
    tempo: one long ACTIVE block. steady: no labels (or all the same) → distance parts."""
    kinds = [str(x.get("intensity") or "").upper() for x in L]
    active = [i for i, k in enumerate(kinds) if k in ("ACTIVE", "INTERVAL")]
    if not active: return "steady"
    return "intervals" if len(active) >= 2 else "tempo"

def export_garmin(s):
    act, aid, typ = s["raw"], s["id"], s["type"]
    g = garmin()
    if not g: raise RuntimeError("no Garmin login")
    hr = hr_series(aid)
    laps = g.get_activity_splits(int(aid)).get("lapDTOs", []) or []
    out, order, t, dist = {}, [], 0.0, 0.0
    structure = None
    if typ in ("run", "ride"):
        L = [{"m": l.get("distance") or 0, "s": l.get("duration") or 0, "hr": l.get("averageHR"), "max": l.get("maxHR"), "cad": l.get("averageRunCadence"),
              "elev": l.get("elevationGain") or 0, "intensity": l.get("intensityType"), "start_utc": l.get("startTimeGMT")} for l in laps if (l.get("duration") or 0) > 5]
        structure = run_structure(L)
        if structure in ("intervals", "tempo"):
            K = [str(x.get("intensity") or "").upper() for x in L]; i = 0; rep = 0
            # warm-up = everything before the first ACTIVE lap
            first = next(j for j, k in enumerate(K) if k in ("ACTIVE", "INTERVAL")); last = max(j for j, k in enumerate(K) if k in ("ACTIVE", "INTERVAL"))
            def add(key, station, grp, extra=None):
                nonlocal t
                sec = sum(x["s"] for x in grp); a, b = t, t + sec; t = b; k, d = _part(key, station, grp, a, b, hr, extra); out[k] = d; order.append(k)
            if first > 0: add("warmup", "Warm-up", L[:first])
            j = first
            while j <= last:
                if K[j] in ("ACTIVE", "INTERVAL"):
                    rep += 1; grp = [L[j]]; j += 1
                    rec = []
                    while j <= last and K[j] not in ("ACTIVE", "INTERVAL"): rec.append(L[j]); j += 1
                    rec_s = sum(x["s"] for x in rec); rec_hr = min((x["hr"] or 999 for x in rec), default=None)
                    add(f"rep{rep}", f"Rep {rep}", grp, {"rep": rep, "rec_s": round(rec_s, 1), "rec_m": round(sum(x["m"] for x in rec)), "rec_hr_min": None if rec_hr in (None, 999) else rec_hr})
                    t += rec_s   # the recovery time passes on the session clock
                else: j += 1
            for k in order:
                if k.startswith("rep"): out[k]["reps"] = rep
            if last + 1 < len(L): add("cooldown", "Cool-down", L[last + 1:])
            dist = sum(x["m"] for x in L)
        else:
            L = [x for x in L if x["m"] > 50]
            for i, grp in enumerate(_groups(L), 1):
                m = sum(x["m"] for x in grp); sec = sum(x["s"] for x in grp); a, b = t, t + sec; t = b
                key, d = _part(f"part{i}", f"KM {_km(dist)}–{_km(dist + m)}", grp, a, b, hr); out[key] = d; order.append(key); dist += m
    total = act.get("duration") or t
    out["_session"] = {"date": s["date"], "type": typ, "name": act.get("activityName"), "total_s": total, "moving_s": act.get("movingDuration"),
                       "avg_hr": act.get("averageHR"), "max_hr": act.get("maxHR"), "kcal": round(sum(l.get("calories") or 0 for l in laps)) or None,
                       "distance_m": act.get("distance") or None, "elev": act.get("elevationGain"), "full_trace": trace(hr, 0, total, 120),
                       "zones": zones(act), "start": s["start"], "start_utc": act.get("startTimeGMT"), "hr5": every(hr), "order": order, "id": aid,
                       "structure": structure, "reps": sum(1 for k in order if k.startswith("rep")) or None,
                       "target": (act.get("activityName") or "").split("@")[-1].strip() if "@" in (act.get("activityName") or "") else None}
    return out

def write(s, all_s):
    data = export_hyrox(s["raw"]) if s["type"] == "hyrox" else export_garmin(s)
    p = f"{SITE}/{rel_file(s, all_s)}"
    os.makedirs(OUT, exist_ok=True); tmp = p + ".tmp"
    json.dump(data, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, p)
    print("wrote", p, "parts:", data["_session"]["order"]); return data

def _load(p):
    try: return json.load(open(p))
    except Exception: return None

def needs_export(s, all_s):
    d = _load(f"{SITE}/{rel_file(s, all_s)}")
    if d is None: return True
    # exported before the Garmin activity (HR) arrived: retry for 3 days
    return not d.get("_session", {}).get("full_trace") and time.time() - time.mktime(time.strptime(s["date"], "%Y-%m-%d")) < 3 * 86400

def write_index(all_s):
    items = []
    for s in reversed(all_s):
        f = rel_file(s, all_s); d = _load(f"{SITE}/{f}")
        items.append({**{k: v for k, v in s.items() if k != "raw"}, "file": f, "exported": d is not None,
                      "kcal": s.get("kcal") or (d or {}).get("_session", {}).get("kcal"),
                      "hr": bool(d and d.get("_session", {}).get("full_trace"))})
    os.makedirs(OUT, exist_ok=True); tmp = f"{OUT}/index.json.tmp"
    json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sessions": items}, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, f"{OUT}/index.json")
    print("index:", len(items), "sessions")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("target", nargs="?", help="date YYYY-MM-DD or Garmin activity id")
    ap.add_argument("--type", help="hyrox | run | ride | strength (with a date)"); ap.add_argument("--sync", action="store_true"); ap.add_argument("--index", action="store_true"); a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True); lock = open(f"{OUT}/.lock", "w")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit("another export is running")
    all_s = all_sessions()
    if a.sync:
        for s in all_s:
            if needs_export(s, all_s):
                try: write(s, all_s)
                except Exception as e: print("skip", s["date"], s["type"], s["id"], e)
    elif a.target:
        hit = [s for s in all_s if s["id"] == a.target] or [s for s in all_s if s["date"] == a.target and (not a.type or s["type"] == a.type)]
        if not hit: raise SystemExit(f"no session for {a.target}{' ' + a.type if a.type else ''} (Garmin activities: last {DAYS} days)")
        for s in hit: write(s, all_s)
    elif not a.index: ap.error("give a date, an activity id, --sync or --index")
    write_index(all_s)

if __name__ == "__main__":
    main()
