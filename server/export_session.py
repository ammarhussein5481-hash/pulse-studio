#!/usr/bin/env python3
"""Runs ON THE PULSE VPS (inside the Pulse Garmin container, which has the Garmin login and mounts the dashboard folder at /work).

Exports training sessions as the data.json Pulse Studio renders from, plus the index the laptop's session picker reads:
  python export_session.py 2026-11-01            -> /work/site/sessions/2026-11-01-hyrox.json (+ index.json)
  python export_session.py <garmin activity id>  -> that one session (several on one day: <date>-hyrox-<id>.json)
  python export_session.py --sync                -> export every session not exported yet (or exported before its HR arrived), rewrite index.json
  python export_session.py --index               -> only rewrite index.json (no Garmin login)
Cron (every 10 min): */10 * * * * docker exec <garmin container> python /work/pulse-studio-server/export_session.py --sync

HYROX: laps from hyrox_watch.json (Pulse HYROX watch app), 200 m splits from erg.json (ErgData), second-by-second HR
from the Garmin activity details (unofficial API, same login garmin_pull.py uses), HR zones from the activity summary.
"""
import sys, json, os, argparse, fcntl, time
sys.path.insert(0, "/work")
SITE = "/work/site"; OUT = f"{SITE}/sessions"

def trace(hr, a, b, n=40):
    pts = [v for s, v in hr if a <= s <= b]
    if not pts: return []
    step = max(1, len(pts) // n)
    return [round(sum(pts[i:i + step]) / len(pts[i:i + step])) for i in range(0, len(pts), step)][:n]

def hr_series(aid):
    import garmin_pull as gp
    g = gp.login_or_none()
    if not g: return []
    d = g.get_activity_details(int(aid), maxchart=5000, maxpoly=0)
    keys = [m["key"] for m in d.get("metricDescriptors", [])]
    ih = keys.index("directHeartRate"); it = keys.index("sumElapsedDuration") if "sumElapsedDuration" in keys else keys.index("sumDuration")
    return [[m["metrics"][it], m["metrics"][ih]] for m in d.get("activityDetailMetrics", []) if m["metrics"][ih] is not None]

def zones(act):
    return [round(act.get(f"hrTimeInZone_{i}", 0) or 0, 1) for i in range(1, 6)]

def watch_sessions():
    return sorted(json.load(open(f"{SITE}/hyrox_watch.json"))["sessions"].values(), key=lambda x: (x["date"], str(x.get("start") or "")))

def rel_file(s, all_s):
    same = [x for x in all_s if x["date"] == s["date"]]
    return f"sessions/{s['date']}-hyrox.json" if len(same) == 1 else f"sessions/{s['date']}-hyrox-{s['id']}.json"

def export_hyrox(s):
    date = s["date"]
    erg = json.load(open(f"{SITE}/erg.json"))
    items = erg if isinstance(erg, list) else (erg.get("items") or erg.get("results") or list(erg.values()))
    if isinstance(items, dict): items = list(items.values())
    E = {x["type"]: x for x in items if isinstance(x, dict) and str(x.get("start_utc", "")).startswith(date)}
    g = json.load(open(f"{SITE}/garmin.json")); acts = g.get("activities") or {}
    act = (acts.get(str(s["id"])) if isinstance(acts, dict) else next((a for a in acts if str(a.get("activityId")) == str(s["id"])), None)) or {}
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
                       "full_trace": trace(hr, 0, t, 120), "zones": zones(act), "start": s.get("start"),
                       "order": [l["key"] for l in s["laps"] if l["key"] != "rest"], "id": str(s["id"])}
    return out

def write(s, all_s):
    data = export_hyrox(s); p = f"{SITE}/{rel_file(s, all_s)}"
    os.makedirs(OUT, exist_ok=True); tmp = p + ".tmp"
    json.dump(data, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, p)
    print("wrote", p, "stations:", [k for k in data if not k.startswith("_")]); return data

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
        items.append({"id": str(s["id"]), "date": s["date"], "type": "hyrox", "start": s.get("start"), "total_s": s["total_s"],
                      "avg_hr": s.get("avg_hr"), "max_hr": s.get("max_hr"), "kcal": s.get("kcal"),
                      "stations": [l["key"] for l in s["laps"] if l["key"] != "rest"], "file": f, "exported": d is not None,
                      "hr": bool(d and d.get("_session", {}).get("full_trace"))})
    os.makedirs(OUT, exist_ok=True); tmp = f"{OUT}/index.json.tmp"
    json.dump({"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "sessions": items}, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, f"{OUT}/index.json")
    print("index:", len(items), "sessions")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("target", nargs="?", help="date YYYY-MM-DD or Garmin activity id")
    ap.add_argument("--type", default="hyrox"); ap.add_argument("--sync", action="store_true"); ap.add_argument("--index", action="store_true"); a = ap.parse_args()
    if a.type != "hyrox": raise SystemExit("only hyrox is implemented in this exporter yet (runs/rides: next)")
    os.makedirs(OUT, exist_ok=True); lock = open(f"{OUT}/.lock", "w")
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit("another export is running")
    all_s = watch_sessions()
    if a.sync:
        for s in all_s:
            if needs_export(s, all_s):
                try: write(s, all_s)
                except Exception as e: print("skip", s["date"], s["id"], e)
    elif a.target:
        hit = [s for s in all_s if str(s["id"]) == a.target] or [s for s in all_s if s["date"] == a.target]
        if not hit: raise SystemExit(f"no HYROX watch session for {a.target}")
        for s in hit: write(s, all_s)
    elif not a.index: ap.error("give a date, an activity id, --sync or --index")
    write_index(all_s)

if __name__ == "__main__":
    main()
