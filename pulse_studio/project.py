"""project.json — the editable heart of a reel. Everything else is derived from it."""
from __future__ import annotations
import json
from pathlib import Path

TEMPLATE = {
    "name": "session",
    "identity": "climbday",
    "session": {"date": "", "type": "hyrox", "source": "pulse"},  # source: pulse | file | none (no numbers); pulse sessions also carry id + file
    "vo": {"main": "vo/main.m4a", "extra": {}, "language": "ar", "dialect_hint": "", "tempo_max": 1.15, "budget_s": 60},
    "captions": {"en": True},   # English second line under the Arabic caption
    "audio": {"music": True, "music_file": "generated", "music_in": "auto", "music_db": -5, "sfx": True, "sfx_db": -7, "amb_db": -4, "duck_threshold": 0.02, "duck_ratio": 6},
    "scenes": [],
}

SCENE_TEMPLATE = {
    "key": "skierg",          # scene id: a phase (warmup / workout / cooldown), a station, or intro / closing — rename freely
    "name": None,             # on-screen name override (the big NAME line); default from the data / key
    "parts": None,            # data parts this scene summarises, e.g. ["rep1", ..., "rep7"] for a "workout" scene; default [key]
    "shots": None,            # several videos / photos played in sequence: [{"file": "C0002.MOV", "in": 3.0, "crop": "auto", "w": 1}, {"file": "IMG_1.jpg"}] — else clip/in/crop below
    "clip": "PC000383.mov",   # file under raw/ (single-shot scene)
    "in": 2.0,                # seconds into the clip
    "crop": "auto",           # auto | full (no crop, vertical source) | "w:h:x:y" explicit crop on the source
    "amb_db": -9,             # original clip audio gain (-90 = mute)
    "vo": {"file": "main", "from": 5.44, "to": 10.26},  # word window in the VO (seconds, as transcribed); or {"file":"warmup"} for a whole extra file
    "caption": "",            # corrected Arabic caption (words are mapped to the transcript timings)
    "script_ok": False,       # he read the line and verified it (web app checkbox)
    "script": "",             # the line he was asked to record (from `pulse-reel script`); caption starts as a copy of it
    "caption_en": "",         # English line under the Arabic caption, shown when captions.en is true
    "title": None,            # override: [kicker, name, big, sub]
    "fx": [],                 # effects: "zoomcut" (snap zoom-in on the cut), "storm" (headline storm before the title), "glass" (liquid-glass panel behind the title), "chat" (caption as chat bubbles)
    "inset": None,            # b-roll overlay: {"file": "assets/erg.png", "at": 1.0, "w": 300, "pos": [740, 980], "label": "ERGDATA"}
    "phone": None,            # phone mockup: {"file": "assets/pulse.png", "at": 0.8}
    "style": None,            # closing only: "checklist" — stations tick off one by one with their times
}

def load(dir: Path) -> dict:
    p = Path(dir) / "project.json"
    if not p.exists():
        raise SystemExit(f"no project.json in {dir} — run: pulse-reel new <dir>")
    d = json.loads(p.read_text(encoding="utf-8"))
    for k, v in TEMPLATE.items():
        if k not in d:
            d[k] = json.loads(json.dumps(v))
    for s in d["scenes"]:
        for k, v in SCENE_TEMPLATE.items():
            s.setdefault(k, v if not isinstance(v, dict) else dict(v))
    return d

def save(dir: Path, d: dict) -> None:
    (Path(dir) / "project.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

def new(dir: Path, name: str, date: str, kind: str) -> dict:
    dir = Path(dir); dir.mkdir(parents=True, exist_ok=True)
    for sub in ("raw", "vo", "build", "out"):
        (dir / sub).mkdir(exist_ok=True)
    d = json.loads(json.dumps(TEMPLATE)); d["name"] = name; d["session"] = {"date": date, "type": kind, "source": "pulse"}
    save(dir, d); return d

def new_from_pulse(dir: Path, name: str, s: dict) -> dict:
    """Project for one Pulse session (an entry of the VPS index.json)."""
    d = new(dir, name, s["date"], s["type"])
    d["session"].update(id=s["id"], file=s["file"], start=s.get("start"), total_s=s.get("total_s")); save(dir, d); return d
