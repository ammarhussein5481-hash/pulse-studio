"""First-draft suggestions: which clip for which scene (shoot order) and where to cut in (motion profile)."""
from __future__ import annotations
import json
from pathlib import Path

SPECIAL = ("intro", "warmup", "closing")

def in_point(clip: dict, need_s: float = 6.0) -> float:
    """Tripod shots: the exercise is the longest LOW-motion run (camera placed, then still); start 1 s into it.
    Handheld / vertical phone clips: motion is high throughout, take 1.5 s (3 s on long clips)."""
    m = clip.get("motion") or []; dur = float(clip.get("duration") or 0)
    if not m or clip.get("vertical"):
        return 3.0 if dur > 60 else 1.5
    srt = sorted(m); med = srt[len(srt) // 2]; thr = max(2, med * 1.25)
    best, cur, cs = (0, 0), 0, 0
    for i, v in enumerate(m + [10 ** 9]):
        if v <= thr: cur += 1 if cur else 0; cs = cs if cur > 1 else i; cur = max(cur, 1)
        else:
            if cur > best[1]: best = (cs, cur)
            cur = 0
    if cur > best[1]: best = (cs, cur)
    s0, n = best
    if n < need_s + 1: return 1.5 if dur > need_s + 2 else 0.0
    t = s0 + 1.0
    return float(min(t, max(0.0, dur - need_s - 0.5)))

def suggest(dir: Path, proj: dict, overwrite_in: bool = False) -> list[str]:
    """Fills empty clips in shoot order (skipping clips already used), and in-points that are still 0 (or all with overwrite_in)."""
    b = Path(dir) / "build"; clips = json.loads((b / "clips.json").read_text(encoding="utf-8")) if (b / "clips.json").exists() else []
    if not clips: raise SystemExit("no clips.json — run: pulse-reel ingest <dir>")
    byname = {c["file"]: c for c in clips}; used = {s.get("clip") for s in proj["scenes"] if s.get("clip")}
    free = [c for c in clips if c["file"] not in used]; notes = []
    # with session data on a clock, the clip filmed during that part wins over shoot order
    m = {}
    dj = b / "data.json"
    if dj.exists():
        try:
            from . import clipmap
            m = clipmap.map_clips(json.loads(dj.read_text(encoding="utf-8")), clips, proj["session"].get("clip_offset_s"))
        except Exception: m = {}
    for s in proj["scenes"]:
        if (not s.get("clip") or s["clip"] not in byname) and m:
            cands = sorted((f for f, v in m.items() if v["part"] == s["key"] and f not in used), key=lambda f: m[f]["t"])
            if cands:
                s["clip"] = cands[0]; used.add(cands[0]); free = [c for c in free if c["file"] != cands[0]]; s["in"] = 0
                notes.append(f"{s['key']}: clip {cands[0]} (filmed at {int(m[cands[0]]['t'] // 60)}:{int(m[cands[0]]['t'] % 60):02d} on the session clock)")
        if not s.get("clip") or s["clip"] not in byname:
            if not free: notes.append(f"{s['key']}: no clip left"); continue
            # intro/closing prefer vertical (phone) clips when there are any; stations take the next tripod clip
            pick = next((c for c in free if c.get("vertical")), None) if s["key"] in SPECIAL else next((c for c in free if not c.get("vertical")), None)
            pick = pick or free[0]; free.remove(pick); s["clip"] = pick["file"]; s["in"] = 0; notes.append(f"{s['key']}: clip {pick['file']}")
        c = byname.get(s.get("clip"))
        if c and (overwrite_in or not s.get("in")):
            s["in"] = in_point(c); notes.append(f"{s['key']}: in {s['in']}s ({'tripod' if not c.get('vertical') else 'handheld'})")
    return notes
