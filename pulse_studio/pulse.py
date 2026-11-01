"""Pulse dashboard access: authenticated GET, and the session index the VPS exporter writes (server/export_session.py --sync)."""
from __future__ import annotations
import json, os, time, urllib.error, urllib.request
from datetime import date, timedelta
from pathlib import Path
from .config import HOME

CACHE = HOME / "pulse-index.json"

def get_json(rel: str):
    base = os.environ.get("PULSE_URL", "").rstrip("/")
    if not base: raise SystemExit("set PULSE_URL (your Pulse dashboard, e.g. https://pulse.example.com) or use session.source = \"file\" / \"none\"")
    token = os.environ.get("PULSE_TOKEN", "")
    req = urllib.request.Request(f"{base}/{rel.lstrip('/')}", headers={"Cookie": f"wd_auth={token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404: raise SystemExit(f"not on Pulse yet: {rel} — the VPS exporter (--sync, every 10 min) hasn't written it")
        raise

def index(refresh: bool = False, max_age: int = 300) -> dict:
    """Session index, cached for max_age seconds (offline: the last cached copy)."""
    if not refresh and CACHE.exists() and time.time() - CACHE.stat().st_mtime < max_age:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    try:
        idx = get_json("sessions/index.json")
    except (urllib.error.URLError, OSError, SystemExit) as e:
        if CACHE.exists():
            idx = json.loads(CACHE.read_text(encoding="utf-8")); idx["stale"] = str(e); return idx
        raise
    CACHE.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8"); return idx

def local_projects(root: Path) -> dict[str, str]:
    """Pulse session id (or date-type for older projects) → project folder name."""
    out = {}
    for d in sorted(Path(root).glob("*/project.json")):
        try: s = json.loads(d.read_text(encoding="utf-8")).get("session", {})
        except ValueError: continue
        out.setdefault(str(s.get("id") or f"{s.get('date')}-{s.get('type')}"), d.parent.name)
    return out

def sessions(root: Path, refresh: bool = False) -> dict:
    idx = index(refresh); local = local_projects(root)
    today = date.today(); names = {today.isoformat(): "Today", (today - timedelta(days=1)).isoformat(): "Yesterday"}
    for s in idx.get("sessions", []):
        s["group"] = names.get(s["date"], "Earlier")
        s["project"] = local.get(s["id"]) or local.get(f"{s['date']}-{s['type']}")
    return idx

def find(sid: str, refresh: bool = False) -> dict:
    for s in index(refresh).get("sessions", []):
        if s["id"] == sid: return s
    if not refresh: return find(sid, True)
    raise SystemExit(f"no Pulse session {sid} in the index")

def describe(idx: dict) -> str:
    lines = [f"Pulse sessions (index {idx.get('generated', '?')}{' — offline, cached' if idx.get('stale') else ''})"]
    for s in idx.get("sessions", []):
        t = s.get("total_s") or 0; start = str(s.get("start") or "")[11:16]
        state = f"project {s['project']}" if s.get("project") else ("ready" if s.get("exported") else "not exported yet")
        what = f"{s['distance_m'] / 1000:.1f} km" if s.get("distance_m") else (f"{len(s.get('stations', []))} stations" if s["type"] == "hyrox" else "")
        lines.append(f"  {s['group']:9s} {s['date']} {start:5s} {s['type']:8s} {int(t // 60)}:{int(t % 60):02d}  {what:12s} id {s['id']}  {state}")
    return "\n".join(lines)
