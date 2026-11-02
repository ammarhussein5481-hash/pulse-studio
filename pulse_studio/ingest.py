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
        c.update(process_clip(raw / c["file"], build, c["duration"], sheets=sheets))
        print(f"  {c['file']} ok", flush=True)
    (build / "clips.json").write_text(json.dumps(clips, indent=1), encoding="utf-8")
    return clips

def process_clip(src: Path, build: Path, dur: float, sheets: bool = True, tiles: int = 8) -> dict:
    """ONE decode of the (4K) source → contact sheet + 480p proxy (for scrubbing in the web app) + motion profile.
    Three outputs from one pass: on a 4K clip this is 3× faster than running them separately."""
    stem = src.stem; sheet = build / f"sheet_{stem}.jpg"; proxy = build / f"proxy_{stem}.mp4"; mot = build / f"motion_{stem}.txt"
    step = max(1.0, dur / tiles)
    fc = ("[0:v]split=3[s][p][m];"
          f"[s]fps=1/{step:.3f},scale=200:-1,tile={tiles}x1[sheet];"
          "[p]scale=-2:480,fps=30[proxy];"
          f"[m]fps=4,scale=96:-2,format=gray,tblend=all_mode=difference,signalstats,metadata=print:key=lavfi.signalstats.YAVG:file='{mot}'[mot]")
    cmd = [ffmpeg(), "-nostdin", "-y", "-v", "error", "-nostats", "-i", str(src), "-filter_complex", fc,
           "-map", "[sheet]", "-frames:v", "1", "-q:v", "8", str(sheet),
           "-map", "[proxy]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "64k", "-ac", "1", "-movflags", "+faststart", str(proxy),
           "-map", "[mot]", "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:   # e.g. a clip without audio stream edge cases → fall back to the separate passes
        out = {"sheet": contact_sheet(src, sheet, dur) if sheets else None, "motion": motion_profile(src)}
        subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-i", str(src), "-vf", "scale=-2:480,fps=30", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(proxy)])
        out["proxy"] = proxy.name if proxy.exists() else None; return out
    vals = [float(m) for m in re.findall(r"YAVG=([0-9.]+)", mot.read_text())] if mot.exists() else []
    mot.unlink(missing_ok=True)
    return {"sheet": sheet.name, "proxy": proxy.name, "motion": [round(sum(vals[i:i + 4]) / max(1, len(vals[i:i + 4]))) for i in range(0, len(vals), 4)]}

def thumb(build: Path, clip: str, t: float, w: int = 240) -> Path:
    """Frame of a clip at t seconds (from the proxy when it exists), cached in build/thumbs/."""
    tdir = build / "thumbs"; tdir.mkdir(exist_ok=True); stem = Path(clip).stem
    out = tdir / f"{stem}_{t:.1f}.jpg"
    if out.exists(): return out
    src = build / f"proxy_{stem}.mp4"
    if not src.exists(): src = build.parent / "raw" / clip
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-ss", str(t), "-i", str(src), "-frames:v", "1", "-vf", f"scale={w}:-2", "-q:v", "6", str(out)], check=True)
    return out

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
