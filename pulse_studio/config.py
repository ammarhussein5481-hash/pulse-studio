"""Paths, identity and tool discovery for Pulse Studio."""
from __future__ import annotations
import os, shutil, glob, json, subprocess
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = PKG.parent
HOME = Path(os.environ.get("PULSE_STUDIO_HOME", Path.home() / ".pulse-studio"))
HOME.mkdir(parents=True, exist_ok=True)

IDENTITY = {
    "climbday": {"bone": "#F4EFE6", "orange": "#FF5A1E", "watermark": "@AMMARHUSSEIN",
                 "font_head": "Anton", "font_label": "Archivo", "font_ar": "Noto Kufi Arabic"},
}

# output format (climbday spec)
W, H, FPS = 1080, 1920, 30
BITRATE = "4300k"

def ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if not p:
        raise SystemExit("ffmpeg not found — run ./setup.sh")
    return p

def ffprobe() -> str:
    return shutil.which("ffprobe") or "ffprobe"

def node() -> str:
    p = shutil.which("node")
    if not p:
        raise SystemExit("node not found — install Node 20+ and run ./setup.sh")
    return p

def chrome() -> str:
    """chrome-headless-shell installed by setup.sh (via @puppeteer/browsers) or given in PULSE_CHROME."""
    env = os.environ.get("PULSE_CHROME")
    if env and Path(env).exists():
        return env
    hits = sorted(glob.glob(str(HOME / "browsers" / "chrome-headless-shell" / "*" / "chrome-headless-shell-linux64" / "chrome-headless-shell")))
    hits += sorted(glob.glob(str(HOME / "browsers" / "chrome-headless-shell" / "*" / "chrome-headless-shell-mac-*" / "chrome-headless-shell")))
    if hits:
        return hits[-1]
    raise SystemExit("chrome-headless-shell not found — run ./setup.sh")

def fonts_dir() -> Path:
    """Fonts come from @fontsource npm packages installed by setup.sh into ~/.pulse-studio/node_modules."""
    return HOME / "node_modules" / "@fontsource"

def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    kw.setdefault("check", True)
    return subprocess.run(cmd, **kw)

def probe(path: str | Path) -> dict:
    out = subprocess.run([ffprobe(), "-v", "error", "-show_entries",
                          "format=duration:format_tags=creation_time:stream=codec_type,width,height,r_frame_rate:stream_side_data=rotation",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
    fmt = j.get("format", {})
    rot = int(next((d.get("rotation", 0) for d in v.get("side_data_list", []) if "rotation" in d), 0) or 0) % 360
    w, h = v.get("width"), v.get("height")
    if rot in (90, 270): w, h = h, w   # phone/camera portrait clips are stored landscape + a display rotation
    return {"duration": float(fmt.get("duration", 0) or 0), "created": (fmt.get("tags") or {}).get("creation_time"),
            "width": w, "height": h, "rotation": rot, "fps": v.get("r_frame_rate")}
