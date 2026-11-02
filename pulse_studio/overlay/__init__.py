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
        o = {"fx": s.get("fx") or [], "style": s.get("style"), "parts": s.get("parts"), "name": s.get("name"), "en": (s.get("caption_en") or "") if (proj.get("captions") or {}).get("en", True) else ""}
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

def stills(dir: Path, times: list[float]) -> list[Path]:
    b = Path(dir) / "build"; out = b / "stills"
    if out.exists(): shutil.rmtree(out)
    subprocess.run([node(), str(HERE / "render.mjs"), chrome(), str(b / "overlay.html"), "stills", str(out), ",".join(str(t) for t in times)], check=True)
    return sorted(out.glob("*.jpg"))

def frames(dir: Path, total_s: float) -> Path:
    b = Path(dir) / "build"; out = b / "frames"
    if out.exists(): shutil.rmtree(out)
    n = int(round(total_s * FPS))
    subprocess.run([node(), str(HERE / "render.mjs"), chrome(), str(b / "overlay.html"), "frames", str(out), "0", str(n), str(FPS)], check=True)
    return out
