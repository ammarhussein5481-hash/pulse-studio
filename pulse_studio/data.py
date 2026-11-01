"""Session data: pulled from Pulse (server/export_session.py output) or a local data.json."""
from __future__ import annotations
import json, os, urllib.request
from pathlib import Path

def fetch(dir: Path, proj: dict, force: bool = False) -> dict:
    dir = Path(dir); out = dir / "build" / "data.json"
    if out.exists() and not force:
        return json.loads(out.read_text(encoding="utf-8"))
    sess = proj["session"]
    if sess.get("source") == "file":
        src = dir / sess.get("file", "data.json")
        data = json.loads(Path(src).read_text(encoding="utf-8"))
    else:
        base = os.environ.get("PULSE_URL", "").rstrip("/")
        if not base: raise SystemExit("set PULSE_URL (your Pulse dashboard, e.g. https://pulse.example.com) or use session.source = \"file\"")
        token = os.environ.get("PULSE_TOKEN", "")
        url = f"{base}/sessions/{sess['date']}-{sess.get('type', 'hyrox')}.json"
        req = urllib.request.Request(url, headers={"Cookie": f"wd_auth={token}"} if token else {})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
    out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data

def summary(data: dict) -> str:
    s = data.get("_session", {}); lines = [f"session {s.get('date')} {s.get('type')} total {s.get('total_s')}s avgHR {s.get('avg_hr')} max {s.get('max_hr')} kcal {s.get('kcal')}"]
    for k in s.get("order", [k for k in data if not k.startswith("_")]):
        d = data.get(k)
        if not d: continue
        extra = f" erg {d['erg'][1]}/500m {d['erg'][2]}spm" if d.get("erg") else ""
        lines.append(f"  {k:12s} {d['station']:16s} {d['s']:7.1f}s HR {d.get('hr')}/{d.get('max')} steps {d.get('steps')} m {d.get('m')}{extra}")
    return "\n".join(lines)
