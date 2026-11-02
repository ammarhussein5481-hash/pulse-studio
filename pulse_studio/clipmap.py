"""Which part of the workout was the camera filming? Clip shoot time (creation_time) against the parts' clock positions.

Cameras write local time, often without a zone; Garmin gives UTC. The offset is found automatically: the shift (in
30-minute steps, ±14 h) that puts the most clips inside the session wins — zero on a tie. `session.clip_offset_s` in
project.json overrides it when the guess is wrong.
"""
from __future__ import annotations
import datetime as dt

def _parse(ts: str | None):
    if not ts: return None
    t = str(ts).replace("Z", "").replace(" ", "T")[:19]
    try: return dt.datetime.fromisoformat(t)
    except ValueError: return None

def session_window(data: dict):
    s = data.get("_session", {}); st = _parse(s.get("start_utc") or s.get("start"))
    if not st: return None
    parts = [data[k] for k in s.get("order", []) if isinstance(data.get(k), dict) and data[k].get("t1") is not None]
    end = max((p["t1"] for p in parts), default=float(s.get("total_s") or 0))
    return st, st + dt.timedelta(seconds=end)

def map_clips(data: dict, clips: list[dict], offset_s: float | None = None) -> dict:
    """{clip file: {part, t_in_session, offset}} for clips whose shoot time falls inside the session (after the offset)."""
    s = data.get("_session", {}); win = session_window(data)
    if not win: return {}
    st, en = win; order = [k for k in s.get("order", []) if isinstance(data.get(k), dict)]
    times = {c["file"]: _parse(c.get("created")) for c in clips}; times = {k: v for k, v in times.items() if v}
    if not times: return {}
    def inside(off):
        n = 0
        for v in times.values():
            t = v + dt.timedelta(seconds=off)
            if st - dt.timedelta(minutes=10) <= t <= en + dt.timedelta(minutes=10): n += 1
        return n
    if offset_s is None:
        cands = [0] + [x * 1800 for x in range(-28, 29) if x]
        offset_s = max(cands, key=lambda o: (inside(o), -abs(o)))
    out = {}
    for f, v in times.items():
        t = (v + dt.timedelta(seconds=offset_s) - st).total_seconds()
        if t < -600 or t > (en - st).total_seconds() + 600: continue
        part = None
        for k in order:
            d = data[k]
            if d.get("t0") is not None and d["t0"] - 5 <= t <= d["t1"] + 5: part = k; break
        if part is None:   # between parts (a recovery, a pause): the part that just ended, or the next one at the start
            before = [k for k in order if data[k].get("t1") is not None and data[k]["t1"] <= t]
            part = before[-1] if before else (order[0] if order else None)
        out[f] = {"part": part, "t": round(t, 1), "offset": offset_s}
    return out

def describe(m: dict) -> str:
    if not m: return "  no clip could be placed on the session clock (no shoot times, or no session start)"
    lines = [f"  clip clock offset {m[next(iter(m))]['offset'] / 3600:+.1f} h"]
    for f, v in sorted(m.items(), key=lambda x: x[1]["t"]):
        mm = int(v["t"] // 60); lines.append(f"  {f:16s} at {mm:3d}:{int(v['t'] % 60):02d} → {v['part']}")
    return "\n".join(lines)
