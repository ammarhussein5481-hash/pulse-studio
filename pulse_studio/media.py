"""Base video: cut each scene from its clip, crop to 9:16, concat, grain + vignette; per-scene ambience track."""
from __future__ import annotations
import subprocess
from pathlib import Path
from .config import ffmpeg, probe, W, H, FPS

def _vf(sc: dict, info: dict) -> str:
    crop = sc.get("crop", "auto")
    vertical = (info["width"] or 0) < (info["height"] or 1)
    if crop == "full" or (crop == "auto" and vertical):
        return f"scale={W}:{H}"
    if crop == "auto":
        return f"crop=ih*9/16:ih,scale={W}:{H}"
    return f"crop={crop},scale={W}:{H}"   # explicit "w:h:x:y" on the source (e.g. 2× punch-in)

def hwaccel_args() -> list[str]:
    """Intel/AMD VAAPI decode when available (Ubuntu laptop) — big win on 4K sources. Falls back silently."""
    import os
    dev = "/dev/dri/renderD128"
    if os.path.exists(dev) and os.environ.get("PULSE_NO_VAAPI") != "1":
        return ["-hwaccel", "vaapi", "-hwaccel_device", dev, "-hwaccel_output_format", "vaapi"]
    return []

def build(dir: Path, proj: dict, tl: dict, only: set[str] | None = None) -> tuple[Path, Path]:
    dir = Path(dir); b = dir / "build"; raw = dir / "raw"
    byk = {s["key"]: s for s in proj["scenes"]}
    vlist, alist = [], []
    for i, s in enumerate(tl["scenes"], 1):
        sc = byk[s["key"]]; src = raw / sc["clip"]; info = probe(src)
        d = round(s["end"] - s["start"], 3); ss = float(sc.get("in", 0))
        if ss + d > info["duration"] + 0.05:
            print(f"  ! {s['key']}: clip {sc['clip']} is {info['duration']:.1f}s, needs in={ss}+{d:.1f}s — will freeze last frame")
        tv, ta = b / f"t{i}.mp4", b / f"t{i}.m4a"
        if only is None or s["key"] in only or not tv.exists():
            vf = _vf(sc, info) + f",fps={FPS},setsar=1,tpad=stop_mode=clone:stop_duration=2"
            hw = hwaccel_args()
            vf_hw = ("hwdownload,format=nv12," + vf) if hw else vf
            cmd = [ffmpeg(), "-nostdin", "-y", "-v", "error", *hw, "-ss", str(ss), "-i", str(src), "-t", str(d), "-an", "-vf", vf_hw,
                   "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", str(tv)]
            r = subprocess.run(cmd)
            if r.returncode != 0:
                if not hw:
                    raise SystemExit(f"ffmpeg failed on {sc['clip']}")
                # VAAPI refused this file (codec/profile) → plain software decode
                subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-ss", str(ss), "-i", str(src), "-t", str(d), "-an", "-vf", vf,
                                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", str(tv)], check=True)
            amp = float(sc.get("amb_db", -9))
            subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-ss", str(ss), "-i", str(src), "-t", str(d), "-vn", "-ac", "2", "-ar", "48000",
                            "-af", f"apad=whole_dur={d},volume={amp}dB", "-c:a", "aac", "-b:a", "160k", str(ta)], check=True)
            print(f"  scene {i} {s['key']} done")
        vlist.append(tv); alist.append(ta)
    (b / "vlist.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in vlist))
    (b / "alist.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in alist))
    base_v, base_a = b / "base_v.mp4", b / "base_a.m4a"
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(b / "vlist.txt"), "-vf",
                    "noise=alls=7:allf=t,vignette=PI/5,format=yuv420p", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS), str(base_v)], check=True)
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(b / "alist.txt"), "-c:a", "aac", "-b:a", "160k", str(base_a)], check=True)
    return base_v, base_a
