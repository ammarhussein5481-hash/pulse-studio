#!/usr/bin/env python3
"""Runs ON THE PULSE VPS (inside the Pulse Garmin container, which has the Garmin login and mounts the dashboard folder at /work).

Exports one training session as the data.json Pulse Studio renders from:
  python export_session.py 2026-11-01            -> /work/site/sessions/2026-11-01.json
  python export_session.py 2026-11-01 --type run -> uses the Garmin activity of that type instead of the HYROX watch app

HYROX: laps from hyrox_watch.json (Pulse HYROX watch app), 200 m splits from erg.json (ErgData), second-by-second HR
from the Garmin activity details (unofficial API, same login garmin_pull.py uses), HR zones from the activity summary.
"""
import sys, json, os, argparse
sys.path.insert(0, "/work")
SITE = "/work/site"

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

def export_hyrox(date):
    hw = json.load(open(f"{SITE}/hyrox_watch.json"))["sessions"]
    sess = [s for s in hw.values() if s["date"] == date]
    if not sess: raise SystemExit(f"no HYROX watch session on {date}")
    s = max(sess, key=lambda x: x["total_s"])
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
                       "order": [l["key"] for l in s["laps"] if l["key"] != "rest"]}
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("date"); ap.add_argument("--type", default="hyrox"); a = ap.parse_args()
    if a.type != "hyrox": raise SystemExit("only hyrox is implemented in this exporter yet (runs/rides: next)")
    data = export_hyrox(a.date)
    os.makedirs(f"{SITE}/sessions", exist_ok=True)
    p = f"{SITE}/sessions/{a.date}-{a.type}.json"
    json.dump(data, open(p, "w"), ensure_ascii=False); print("wrote", p, "stations:", [k for k in data if not k.startswith("_")])

if __name__ == "__main__":
    main()
