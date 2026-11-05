#!/usr/bin/env python3
"""Base cut: real-speed clips, photos with sub-pixel Ken Burns (see kenburns()), ~81 s, yellow-jersey photo as closing. Writes timeline2.json + base2.mp4"""
import json, subprocess, os, sys
SRC = os.environ.get("MEDIA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "media"))
OUT = os.path.join(os.path.dirname(__file__), "seg2"); os.makedirs(OUT, exist_ok=True)
FPS = 30
# (id, file, kind, in, dur(out), motion/speed)
SCENES = [
  ("hookA", "IMG_0844.MOV",     "l",  20.0, 1.8, 1.0),
  ("hookB", "IMG_0909.JPG.jpeg","pl", 0,    1.6, "zin"),
  ("hookC", "IMG_0787.MP4",     "v",  4.0,  1.6, 1.0),
  ("hookD", "IMG_0802.JPG.jpeg","pv", 0,    3.5, "zout"),
  ("d1a",   "IMG_0764.jpg",     "pv", 0,    3.5, "zin"),
  ("d1b",   "IMG_0823.jpg",     "pv", 0,    3.5, "zout"),
  ("d2a",   "IMG_0909.JPG.jpeg","pl", 0,    5.5, "panR"),
  ("d2b",   "IMG_0853.JPG.jpeg","pl", 0,    4.0, "panL"),
  ("d2c",   "IMG_0787.MP4",     "v",  6.5,  4.0, 1.0),
  ("d3a",   "IMG_0813.MOV",     "l",  2.0,  5.0, 1.0),
  ("d3b",   "IMG_0815.MP4",     "v",  3.0,  5.0, 1.0),
  ("d4a",   "IMG_0844.MOV",     "l",  4.0,  8.0, 1.0),
  ("d4b",   "IMG_0851.JPG.jpeg","pl", 0,    4.0, "panR"),
  ("d4c",   "IMG_0854.JPG.jpeg","pl", 0,    2.8, "zin"),
  ("d4d",   "IMG_0855.JPG.jpeg","pl", 0,    2.8, "zin"),
  ("d5a",   "IMG_0868.MP4",     "v",  2.0,  5.0, 1.0),
  ("d5b",   "IMG_0873.JPG.jpeg","pv", 0,    4.5, "zin"),
  ("d6",    "IMG_0844.MOV",     "l",  26.0, 5.0, 1.0),
  ("close", "IMG_0880.JPG.jpeg","pv", 0,   10.0, "zin"),
]
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print(r.stderr[-2000:]); sys.exit(1)

def kenburns(sid, src, kind, mo, n, dur, out):
    """Photo scene with sub-pixel Ken Burns (ffmpeg's zoompan rounds to whole pixels → shimmer, and squashed landscape photos).
    Canvas: portrait photos cover-cropped to 1296x2304, landscape ones scaled to 2304 tall; a 9:16 window moves over it.
    Saves the canvas + one affine matrix per frame (seg2/<sid>.kb.json) so masks.py moves the rider mask with the exact same motion."""
    import numpy as np, cv2
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB"); w, h = im.size
    if kind == "pv":
        s = max(1296 / w, 2304 / h); im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
        x0 = (im.width - 1296) // 2; y0 = (im.height - 2304) // 2; im = im.crop((x0, y0, x0 + 1296, y0 + 2304))
    else:
        im = im.resize((round(w * 2304 / h), 2304), Image.LANCZOS)
    canvas = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR); CH, CW = canvas.shape[:2]
    cpath = os.path.join(OUT, sid + ".canvas.png"); cv2.imwrite(cpath, canvas)
    ease = lambda p: p * p * (3 - 2 * p)   # smoothstep: no jolt at the start/end of the move
    mats = []
    for k in range(n):
        p = k / max(1, n - 1)
        if mo in ("zin", "zout"):
            z = 1 + 0.12 * (ease(p) if mo == "zin" else 1 - ease(p)); wh = 2304 / z; ww = wh * 9 / 16
            x0 = (CW - ww) / 2; y0 = (CH - wh) / 2
        else:
            ww, wh = 1296.0, 2304.0; q = ease(p) if mo == "panR" else 1 - ease(p); x0 = (CW - ww) * q; y0 = 0.0
        sc = 1080 / ww; mats.append([[sc, 0, -x0 * sc], [0, sc, -y0 * sc]])
    json.dump({"canvas": cpath, "w": 1080, "h": 1920, "M": mats}, open(os.path.join(OUT, sid + ".kb.json"), "w"))
    enc = subprocess.Popen(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", "1080x1920", "-r", str(FPS), "-i", "-",
                            "-f", "lavfi", "-t", str(dur), "-i", "anullsrc=r=48000:cl=stereo", "-frames:v", str(n),
                            "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", out], stdin=subprocess.PIPE)
    for M in mats:
        enc.stdin.write(cv2.warpAffine(canvas, np.array(M, np.float64), (1080, 1920), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT).tobytes())
    enc.stdin.close()
    if enc.wait(): sys.exit(1)
tl = []; t = 0.0
for sid, f, kind, inp, dur, mo in SCENES:
    src = os.path.join(SRC, f); out = os.path.join(OUT, sid + ".mp4"); n = int(round(dur * FPS))
    if kind in ("v", "l"):
        sp = float(mo); srcdur = dur * sp
        vf = ("crop=ih*9/16:ih," if kind == "l" else "") + f"setpts=PTS/{sp},scale=1080:1920:flags=lanczos,fps=30,setsar=1"
        af = f"atempo={sp}," if sp != 1 else ""
        cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-ss", str(inp), "-t", str(srcdur + 0.2), "-i", src,
               "-vf", vf, "-af", af + "volume=-10dB,aresample=48000", "-ac", "2", "-ar", "48000", "-t", str(dur),
               "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", out]
    else:
        print(sid, f, dur, flush=True); kenburns(sid, src, kind, mo, n, dur, out)
        tl.append({"id": sid, "src": f, "start": round(t, 3), "end": round(t + dur, 3), "dur": dur}); t += dur
        continue
    print(sid, f, dur, flush=True); run(cmd)
    tl.append({"id": sid, "src": f, "start": round(t, 3), "end": round(t + dur, 3), "dur": dur}); t += dur
with open(os.path.join(OUT, "list.txt"), "w") as fh:
    for s in tl: fh.write(f"file '{os.path.join(OUT, s['id'])}.mp4'\n")
run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(OUT, "list.txt"), "-c", "copy", os.path.join(os.path.dirname(__file__), "base2.mp4")])
json.dump({"fps": FPS, "total": round(t, 3), "scenes": tl}, open(os.path.join(os.path.dirname(__file__), "timeline2.json"), "w"), indent=1)
print("total", t)
