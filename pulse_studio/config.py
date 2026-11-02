"""Paths, identity and tool discovery for Pulse Studio."""
from __future__ import annotations
import os, re, shutil, glob, json, subprocess
from pathlib import Path

PKG = Path(__file__).resolve().parent
REPO = PKG.parent
HOME = Path(os.environ.get("PULSE_STUDIO_HOME", Path.home() / ".pulse-studio"))
HOME.mkdir(parents=True, exist_ok=True)

IDENTITY = {
    "climbday": {"bone": "#F4EFE6", "orange": "#FF5A1E", "watermark": "@AMMARHUSSEIN",
                 "font_head": "Anton", "font_label": "Archivo", "font_ar": "Noto Kufi Arabic"},
}

# accent colours a reel can use instead of the identity orange (project.accent = a name or "#RRGGBB"; empty = orange)
ACCENTS = {"orange": "#FF5A1E", "green": "#22C55E", "blue": "#2F7BFF", "cyan": "#22D3EE", "yellow": "#FACC15", "lemon": "#E8FF3A",
           "pink": "#FF6FB5", "magenta": "#FF2BD6", "red": "#FF3B30", "purple": "#A855F7", "black": "#000000"}

def accent_color(value, default: str) -> str:
    """project.accent → "#RRGGBB"."""
    if not value: return default
    v = str(value).strip(); hex_ = ACCENTS.get(v.lower()) or v
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_): raise SystemExit(f"unknown accent colour {value!r}: use #RRGGBB or one of {', '.join(ACCENTS)}")
    return hex_

def is_dark(hex_: str) -> bool:
    r, g, b = (int(hex_[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b < 60

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
