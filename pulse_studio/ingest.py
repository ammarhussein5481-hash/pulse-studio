"""Clip inventory: order by shoot time, motion profile, contact sheets — the material Claude and Ammar pick scenes from."""
from __future__ import annotations
import json, re, subprocess
from pathlib import Path
from .config import ffmpeg, probe

VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv"}

def inventory(dir: Path, sheets: bool = True) -> list[dict]:
    raw = Path(dir) / "raw"; build = Path(dir) / "build"; build.mkdir(exist_ok=True)
    clips = []
    for f in sorted(raw.iterdir()):
        if f.suffix.lower() not in VIDEO_EXT:
            continue
        p = probe(f)
        clips.append({"file": f.name, "created": p["created"], "duration": round(p["duration"], 2),
                      "width": p["width"], "height": p["height"], "vertical": (p["width"] or 0) < (p["height"] or 1)})
    clips.sort(key=lambda c: (c["created"] or "", c["file"]))
    for c in clips:
        if sheets:
            c["sheet"] = contact_sheet(raw / c["file"], build / f"sheet_{Path(c['file']).stem}.jpg", c["duration"])
        c["motion"] = motion_profile(raw / c["file"])
    (build / "clips.json").write_text(json.dumps(clips, indent=1), encoding="utf-8")
    return clips

def contact_sheet(src: Path, out: Path, dur: float, tiles: int = 8) -> str:
    step = max(1.0, dur / tiles)
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-i", str(src), "-vf",
                    f"fps=1/{step:.3f},scale=200:-1,tile={tiles}x1", "-frames:v", "1", "-q:v", "8", str(out)], check=True)
    return out.name

def motion_profile(src: Path) -> list[int]:
    """Per-second mean frame difference at low res. Handheld camera placement = high; static tripod exercise = low."""
    out = subprocess.run([ffmpeg(), "-nostdin", "-v", "error", "-nostats", "-i", str(src), "-an", "-vf",
                          "fps=4,scale=96:-2,format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
                          "-f", "null", "-"], capture_output=True, text=True).stdout
    vals = [float(m) for m in re.findall(r"YAVG=([0-9.]+)", out)]
    return [round(sum(vals[i:i + 4]) / max(1, len(vals[i:i + 4]))) for i in range(0, len(vals), 4)]

def describe(clips: list[dict]) -> str:
    lines = []
    for c in clips:
        t = (c["created"] or "")[11:19]
        v = "V" if c["vertical"] else "H"
        m = " ".join(str(x) for x in c["motion"][:40])
        lines.append(f"{t} {c['file']:14s} {c['duration']:6.1f}s {v} motion: {m}")
    return "\n".join(lines)
