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

def summary(data: dict) -> str:
    s = data.get("_session", {})
    if s.get("none"): return f"no session data ({s.get('date')} {s.get('type')}): titles + captions only for {', '.join(s['order']) or 'no stations yet'}"
    lines = [f"session {s.get('date')} {s.get('type')} total {s.get('total_s')}s avgHR {s.get('avg_hr')} max {s.get('max_hr')} kcal {s.get('kcal')}"]
    for k in s.get("order", [k for k in data if not k.startswith("_")]):
        d = data.get(k)
        if not d: continue
        extra = f" erg {d['erg'][1]}/500m {d['erg'][2]}spm" if d.get("erg") else ""
        lines.append(f"  {k:12s} {d['station']:16s} {d['s']:7.1f}s HR {d.get('hr')}/{d.get('max')} steps {d.get('steps')} m {d.get('m')}{extra}")
    return "\n".join(lines)
