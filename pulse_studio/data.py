"""Session data: pulled from Pulse (server/export_session.py output), a local data.json, or none (titles + captions only)."""
from __future__ import annotations
import json
from pathlib import Path
from . import pulse

SPECIAL = {"intro", "warmup", "closing"}

def empty(proj: dict) -> dict:
    """No session data: stations are the scene keys, no numbers; the overlay shows titles and captions only."""
    s = proj["session"]
    return {"_session": {"date": s.get("date"), "type": s.get("type", "hyrox"), "none": True,
                         "order": [sc["key"] for sc in proj["scenes"] if sc["key"] not in SPECIAL]}}

def fetch(dir: Path, proj: dict, force: bool = False) -> dict:
    dir = Path(dir); out = dir / "build" / "data.json"
    if out.exists() and not force:
        return json.loads(out.read_text(encoding="utf-8"))
    sess = proj["session"]
    if sess.get("source") == "none":
        return empty(proj)  # derived from the scenes every time, never cached
    if sess.get("source") == "file":
        src = dir / sess.get("file", "data.json")
        data = json.loads(Path(src).read_text(encoding="utf-8"))
    else:
        data = pulse.get_json(sess.get("file") or f"sessions/{sess['date']}-{sess.get('type', 'hyrox')}.json")
    out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data

def _utc(s):
    from datetime import datetime, timezone
    s = str(s or "").replace(" ", "T").replace("Z", "+00:00")
    if not s: return None
    d = datetime.fromisoformat(s)
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()

def enrich(dir: Path, proj: dict, data: dict, tl: dict) -> dict:
    """Scenes with no data of their own (strength exercises; any extra scene) get the HR from when their clip was shot:
    clip creation_time + in-point, matched against _session.hr5 (HR every 5 s from the activity start)."""
    from .config import probe
    s = data.get("_session", {}); hr5, t0 = s.get("hr5"), _utc(s.get("start_utc"))
    keys = [sc["key"] for sc in proj["scenes"] if sc["key"] not in SPECIAL]
    if not s.get("order") and keys: s["order"] = keys          # strength: the exercises are whatever the scenes are
    if not hr5 or t0 is None: return data
    dur = {x["key"]: x["end"] - x["start"] for x in tl.get("scenes", [])}
    for sc in proj["scenes"]:
        k = sc["key"]
        if k in SPECIAL or k in data or not sc.get("clip"): continue
        try: c = _utc(probe(Path(dir) / "raw" / sc["clip"]).get("created"))
        except Exception: continue
        if c is None: continue
        a = int((c + float(sc.get("in", 0)) - t0) // 5); b = a + max(2, int(dur.get(k, 6) // 5) + 1)
        win = [v for v in hr5[max(0, a - 6):max(0, b + 6)] if v]   # ±30 s around the shot: a set and its recovery
        if len(win) < 2: continue
        data[k] = {"station": k.replace("_", " ").title(), "hr": round(sum(win) / len(win)), "max": max(win), "trace": win, "from_clip": True}
    return data

def summary(data: dict) -> str:
    s = data.get("_session", {})
    if s.get("type") in ("run", "ride", "strength"):
        km = f" {s['distance_m'] / 1000:.1f} km" if s.get("distance_m") else ""
        lines = [f"session {s.get('date')} {s.get('type')}{km} total {s.get('total_s', 0):.0f}s avgHR {s.get('avg_hr')} max {s.get('max_hr')} kcal {s.get('kcal')}"]
        for k in s.get("order", []):
            d = data.get(k)
            if d: lines.append(f"  {k:8s} {d['station']:14s} {d['s']:7.1f}s {d['m']} m HR {d.get('hr')}/{d.get('max')} +{d.get('elev')} m  laps {len(d.get('laps', []))}")
        if s.get("type") == "strength": lines.append("  exercises = the scene keys; each scene's HR comes from its clip's shoot time")
        return "\n".join(lines)
    if s.get("none"): return f"no session data ({s.get('date')} {s.get('type')}): titles + captions only for {', '.join(s['order']) or 'no stations yet'}"
    lines = [f"session {s.get('date')} {s.get('type')} total {s.get('total_s')}s avgHR {s.get('avg_hr')} max {s.get('max_hr')} kcal {s.get('kcal')}"]
    for k in s.get("order", [k for k in data if not k.startswith("_")]):
        d = data.get(k)
        if not d: continue
        extra = f" erg {d['erg'][1]}/500m {d['erg'][2]}spm" if d.get("erg") else ""
        lines.append(f"  {k:12s} {d['station']:16s} {d['s']:7.1f}s HR {d.get('hr')}/{d.get('max')} steps {d.get('steps')} m {d.get('m')}{extra}")
    return "\n".join(lines)
