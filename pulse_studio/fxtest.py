"""`pulse-reel fxtest` — prove every media effect moves on THIS machine (software and VAAPI paths alike).

Renders a grid test clip (and a grid photo) through the real cut functions once per fx, then tiles frames 0 / 5 / 20 / 45 of
each result into one sheet and measures whether frame 0 differs from frame 45 (SSIM). A moving fx scores well below 1.0;
"none" (no fx) must score ≈ 1.0. The sheet is the human check, the table is the machine check.
"""
from __future__ import annotations
import re, subprocess, tempfile
from pathlib import Path
from .config import ffmpeg, probe, FPS
from . import media

ROWS = [("none", []), ("zoomcut", ["zoomcut"]), ("pullback", ["pullback"]), ("pullback+focus", ["pullback"]), ("glitch", ["glitch"]), ("glass", ["glass"])]
FRAMES = (0, 5, 20, 45)

def _ssim(a: Path, b: Path) -> float:
    r = subprocess.run([ffmpeg(), "-v", "info", "-i", str(a), "-i", str(b), "-lavfi", "ssim", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"All:([0-9.]+)", r.stderr); return float(m.group(1)) if m else 1.0

def run(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True); t = Path(tempfile.mkdtemp(prefix="fxtest-"))
    grid = "color=c=0x606060:s=1920x1080:r=30,drawgrid=width=120:height=120:thickness=6:color=white,drawbox=x=900:y=480:w=120:h=120:color=red:t=fill"
    src = t / "grid.mp4"; photo = t / "grid.jpg"
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", grid, "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", grid, "-frames:v", "1", str(photo)], check=True)
    info = probe(src); rows, report = [], []
    cases = ROWS + [("photo", []), ("photo+pullback", ["pullback"]), ("photo+glitch", ["glitch"])]
    for name, fx in cases:
        sc = {"clip": src.name, "fx": fx, "crop": "auto", "amb_db": -9, "focus": [0.75, 0.25] if name == "pullback+focus" else None}
        v, a = t / f"{name}.mp4", t / f"{name}.m4a"
        if name.startswith("photo"): media.cut_photo(photo, sc, 2.0, v, a)
        else: media.cut_scene(src, sc, info, 0.5, 2.0, v, a)
        pngs = []
        for f in FRAMES:
            p = t / f"{name}_{f}.png"
            subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-i", str(v), "-vf", f"select=eq(n\\,{f})", "-frames:v", "1", str(p)], check=True); pngs.append(p)
        s = _ssim(pngs[0], pngs[-1]); moves = s < 0.9
        expect = name not in ("none", "glass")   # glass is a static blur; its proof is the frame itself, not motion
        ok = moves == expect if name != "glass" else _ssim(pngs[0], t / "none_0.png") < 0.999
        report.append((name, s, ok))
        row = t / f"row_{name}.png"
        subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", *sum([["-i", str(p)] for p in pngs], []), "-filter_complex",
                        "".join(f"[{k}:v]scale=240:-1[s{k}];" for k in range(4)) + "[s0][s1][s2][s3]hstack=4,drawtext=text='%s  frames 0 5 20 45':x=8:y=8:fontsize=26:fontcolor=yellow:box=1:boxcolor=black@0.6" % name.replace(":", "\\:"),
                        str(row)], check=True); rows.append(row)
    sheet = out_dir / "fxtest.jpg"
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", *sum([["-i", str(r)] for r in rows], []), "-filter_complex",
                    "".join(f"[{k}:v]" for k in range(len(rows))) + f"vstack={len(rows)}", "-q:v", "3", str(sheet)], check=True)
    print(f"  {'fx':16s} {'ssim 0→45':>10s}  verdict")
    for name, s, ok in report:
        print(f"  {name:16s} {s:10.3f}  {'OK' if ok else 'FAIL'}{'' if ok else '  ← no motion: the fx did not apply on this machine'}")
    print(f"sheet: {sheet}")
    if not all(ok for _, _, ok in report): raise SystemExit("fxtest: some effects did not apply — send the table + sheet to the Assistant")
    return sheet
