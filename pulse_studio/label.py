"""What does each clip SHOW? A vision pass over the contact sheets (Claude Code headless, the same CLI the Assistant panel uses)
→ clips.json gets `label`, `label_conf`, `label_note`. The script step combines it with the shoot time: the clock says
"rep 3", the picture says "fast run" → consistent; "recovery walk" on a rep → the scene is flagged, not the clip.

Labels (one per clip):
  warmup · easy_run · fast_run · recovery_walk · stretch · strength · talking (Ammar speaking to the camera) · scenery (no athlete)
  hyrox:skierg · hyrox:row · hyrox:farmers · hyrox:lunges · hyrox:wall_balls · hyrox:burpee_bj · hyrox:sled_push · hyrox:sled_pull · hyrox:run
  ride · other
"""
from __future__ import annotations
import json, os, re, shutil, subprocess
from pathlib import Path

LABELS = ["warmup", "easy_run", "fast_run", "recovery_walk", "stretch", "strength", "talking", "scenery", "ride", "other",
          "hyrox:skierg", "hyrox:row", "hyrox:farmers", "hyrox:lunges", "hyrox:wall_balls", "hyrox:burpee_bj", "hyrox:sled_push", "hyrox:sled_pull", "hyrox:run"]
# which workout parts a label is consistent with
FITS = {"warmup": {"warmup"}, "easy_run": {"warmup", "cooldown", "part"}, "fast_run": {"rep", "part"}, "recovery_walk": {"rec"},
        "stretch": {"warmup", "cooldown"}, "ride": {"part", "rep"}}   # talking / scenery fit anywhere (they never contradict a part)

PROMPT = """You label training-video clips for a reel editor. For EACH contact sheet below (8 frames of one clip, left→right in time), say what the athlete is doing in most of the frames.
Reply with ONLY a JSON array, one object per sheet, in the same order: {{"file": "<file>", "label": "<one of: {labels}>", "conf": 0.0-1.0, "note": "<max 8 words: what you see, e.g. 'treadmill, fast stride' or 'walking, hands on hips'>"}}
Rules: fast_run = clearly running hard (stride, arms, effort); easy_run = jogging; recovery_walk = walking/standing between efforts; warmup = drills, skips, mobility; talking = the athlete faces the camera speaking; scenery = no athlete visible most of the time. HYROX station labels only when the equipment is visible. Do not explain.

Sheets ({n}):
{items}"""

def _claude() -> str | None:
    return os.environ.get("PULSE_CLAUDE_BIN") or shutil.which("claude")

def label_clips(dir: Path, clips: list[dict], force: bool = False) -> list[dict]:
    dir = Path(dir); b = dir / "build"; cl = _claude()
    todo = [c for c in clips if c.get("sheet") and (force or not c.get("label"))]
    if not todo: return clips
    if not cl: raise SystemExit("claude CLI not found — install Claude Code (the Assistant panel needs it too) or set PULSE_CLAUDE_BIN")
    items = "\n".join(f"- {c['file']}: {b / c['sheet']}" for c in todo)
    prompt = PROMPT.format(labels=", ".join(LABELS), n=len(todo), items=items) + "\n\nRead each sheet file with the Read tool, then answer."
    cmd = [cl, "-p", prompt, "--output-format", "text", "--allowedTools", "Read", "--add-dir", str(b), "--model", os.environ.get("PULSE_LABEL_MODEL", "claude-sonnet-5-5")]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode: raise SystemExit("claude failed: " + (r.stderr or r.stdout)[-400:])
    m = re.search(r"\[.*\]", r.stdout, re.S)
    if not m: raise SystemExit("no JSON in the answer:\n" + r.stdout[-400:])
    ans = {a.get("file"): a for a in json.loads(m.group(0)) if isinstance(a, dict)}
    for c in todo:
        a = ans.get(c["file"]) or {}
        c["label"] = a.get("label") if a.get("label") in LABELS else ("other" if a else None)
        c["label_conf"] = a.get("conf"); c["label_note"] = a.get("note")
    (b / "clips.json").write_text(json.dumps(clips, indent=1), encoding="utf-8")
    return clips

def consistent(label: str | None, part_key: str | None) -> bool | None:
    """True/False when the label says something about the part, None when it doesn't apply (no label, 'other', scenery on a rep…)."""
    if not label or not part_key or label == "other": return None
    if label.startswith("hyrox:"): return label.split(":", 1)[1] == part_key
    kind = "rep" if re.match(r"rep\d+$", part_key) else "part" if re.match(r"part\d+$", part_key) else part_key
    fits = FITS.get(label)
    if not fits: return None
    return kind in fits

def describe(clips: list[dict]) -> str:
    return "\n".join(f"  {c['file']:16s} {c.get('label') or '—':16s} {c.get('label_conf') if c.get('label_conf') is not None else '':>4}  {c.get('label_note') or ''}" for c in clips)
