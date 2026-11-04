"""Overlay page: writes build/overlay.html + data.js, renders stills or the full PNG sequence."""
from __future__ import annotations
import json, subprocess, shutil
from pathlib import Path
from ..config import PKG, IDENTITY, accent_color, is_dark, chrome, node, fonts_dir, FPS

HERE = PKG / "overlay"

def write_page(dir: Path, proj: dict, data: dict, tl: dict) -> Path:
    dir = Path(dir); b = dir / "build"
    ident = IDENTITY.get(proj.get("identity", "climbday"), IDENTITY["climbday"])
    html = (HERE / "overlay.html").read_text(encoding="utf-8"); accent = accent_color(proj.get("accent"), ident["orange"])
    if is_dark(accent):   # the usual dark shadow would hide dark text and marks: give those a light glow instead
        glow = "0 0 3px rgba(255,255,255,.95),0 0 12px rgba(255,255,255,.75)"; mark = "filter:drop-shadow(0 0 2px rgba(255,255,255,.95)) drop-shadow(0 0 6px rgba(255,255,255,.6))"
        html = html.replace("</style>", f"#big,#sub b,#cap span.on,#grid .v,#storm b,#chk .t,#chkf .v{{text-shadow:{glow}}}#dia rect[fill=\"{accent}\"],#dia path[stroke=\"{accent}\"],#dia circle[stroke=\"{accent}\"]{{{mark}}}#cap.chat .bub.me{{color:var(--bone)}}</style>", 1)
    html = (html.replace("__FONTS__", "file://" + str(fonts_dir())).replace("__BONE__", ident["bone"])
                .replace("__OR__", accent).replace("__WATERMARK__", ident["watermark"]))
    titles = {s["key"]: s["title"] for s in proj["scenes"] if s.get("title")}
    opts = {}; (b / "assets").mkdir(exist_ok=True)
    for s in proj["scenes"]:
        o = {"fx": s.get("fx") or [], "style": s.get("style"), "parts": s.get("parts"), "name": s.get("name"), "cap_y": s.get("cap_y"), "en": (s.get("caption_en") or "") if (proj.get("captions") or {}).get("en", True) else ""}
        if s.get("style") == "typewriter": o["tw"] = typewriter_text(s)
        for k in ("inset", "phone"):
            v = s.get(k)
            if v and v.get("file"):
                src = dir / v["file"]
                if not src.exists(): raise SystemExit(f"scene {s['key']}: {k} file {v['file']} not found")
                shutil.copy(src, b / "assets" / src.name); o[k] = {**v, "file": "assets/" + src.name}
        opts[s["key"]] = o
    (b / "data.js").write_text("window.DATA=" + json.dumps({"data": data, "timeline": tl, "titles": titles, "scenes": opts}, ensure_ascii=False) + ";", encoding="utf-8")
    page = b / "overlay.html"; page.write_text(html, encoding="utf-8")
    return page

TW_CPS = 16      # typewriter closing: characters per second (overlay + SFX keystrokes share it)
TW_START = 0.5   # seconds into the closing before the first key

def typewriter_text(sc: dict) -> str:
    """The line the typewriter closing types: the scene's English caption (it then leaves the caption block), else the identity line."""
    return (sc.get("caption_en") or "ALL NUMBERS FROM GARMIN + PULSE").strip()

def stills(dir: Path, times: list[float]) -> list[Path]:
    b = Path(dir) / "build"; out = b / "stills"
    if out.exists(): shutil.rmtree(out)
    subprocess.run([node(), str(HERE / "render.mjs"), chrome(), str(b / "overlay.html"), "stills", str(out), ",".join(str(t) for t in times)], check=True)
    return sorted(out.glob("*.jpg"))

def _h(obj) -> str:
    import hashlib; return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:12]

def _render_ranges(b: Path, out: Path, ranges: list[tuple[int, int]], workers: int) -> None:
    """Render [a, z) frame ranges with up to `workers` Chromes; long ranges are split so every worker stays busy."""
    jobs = []
    for a, z in ranges:
        step = max(60, -(-(z - a) // workers))
        for x in range(a, z, step): jobs.append((x, min(z, x + step)))
    jobs.sort(); procs = []
    while jobs or procs:
        while jobs and len(procs) < workers:
            a, z = jobs.pop(0)
            procs.append(subprocess.Popen([node(), str(HERE / "render.mjs"), chrome(), str(b / "overlay.html"), "frames", str(out), str(a), str(z), str(FPS)]))
        done = [p for p in procs if p.poll() is not None]
        for p in done:
            procs.remove(p)
            if p.returncode: raise SystemExit(f"frame rendering failed (exit {p.returncode})")
        if procs and not done: procs[0].wait()

def frames(dir: Path, total_s: float, workers: int | None = None, tl: dict | None = None, proj: dict | None = None, data: dict | None = None) -> Path:
    """The PNG sequence. INCREMENTAL: a manifest remembers a fingerprint per scene (timing, words, caption, fx, data…);
    only scenes whose fingerprint changed are re-rendered (plus 4 frames of margin for the cut flash). Anything global
    (data, identity, the overlay page itself, scene order, length) changed → full render."""
    import os
    b = Path(dir) / "build"; out = b / "frames"; man = b / "frames_manifest.json"
    n = int(round(total_s * FPS))
    workers = workers or int(os.environ.get("PULSE_RENDER_WORKERS", 0)) or max(1, min(3, (os.cpu_count() or 2) - 1))
    full = tl is None or proj is None or not out.exists() or not man.exists() or os.environ.get("PULSE_FULL_RENDER") == "1"
    opts = {s["key"]: {k: s.get(k) for k in ("fx", "style", "parts", "name", "cap_y", "inset", "phone", "caption_en", "title")} for s in (proj or {}).get("scenes", [])}
    glob = _h({"data": data, "identity": (proj or {}).get("identity"), "captions": (proj or {}).get("captions"), "page": (HERE / "overlay.html").read_text(encoding="utf-8"),
               "order": [s["key"] for s in (tl or {}).get("scenes", [])], "n": n, "tempo": (tl or {}).get("tempo")})
    per = {s["key"]: {"h": _h({"s": s, "o": opts.get(s["key"])}), "f0": int(round(s["start"] * FPS)), "f1": int(round(s["end"] * FPS))} for s in (tl or {}).get("scenes", [])}
    old = json.loads(man.read_text()) if man.exists() else {}
    if not full and old.get("glob") != glob: full = True
    if full:
        if out.exists(): shutil.rmtree(out)
        out.mkdir(parents=True); ranges = [(0, n)]
    else:
        ranges = []
        for k, v in per.items():
            o = old.get("scenes", {}).get(k)
            if not o or o["h"] != v["h"] or o["f0"] != v["f0"] or o["f1"] != v["f1"]:
                ranges.append((max(0, v["f0"] - 4), min(n, v["f1"] + 4)))
        for i in range(n):   # a frame lost on disk is re-rendered too
            if not (out / f"{i:05d}.png").exists() and not any(a <= i < z for a, z in ranges): ranges.append((i, i + 1))
        for f in out.glob("*.png"):   # length shrank
            if int(f.stem) >= n: f.unlink()
    merged = []
    for a, z in sorted(ranges):
        if merged and a <= merged[-1][1]: merged[-1] = (merged[-1][0], max(merged[-1][1], z))
        else: merged.append((a, z))
    todo = sum(z - a for a, z in merged)
    if todo: _render_ranges(b, out, merged, 1 if todo < 300 else workers)
    missing = [i for i in range(n) if not (out / f"{i:05d}.png").exists()]
    if missing: raise SystemExit(f"{len(missing)} frames missing (first {missing[0]})")
    man.write_text(json.dumps({"glob": glob, "scenes": per}), encoding="utf-8")
    print(f"frames done {n}" + (f" — {todo} rendered ({'full' if full else str(len(merged)) + ' changed scene range(s)'}), {n - todo} reused" if True else ""), flush=True)
    return out
