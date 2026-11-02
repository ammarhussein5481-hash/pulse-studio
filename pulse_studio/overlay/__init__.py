"""Overlay page: writes build/overlay.html + data.js, renders stills or the full PNG sequence."""
from __future__ import annotations
import json, subprocess, shutil
from pathlib import Path
from ..config import PKG, IDENTITY, chrome, node, fonts_dir, FPS

HERE = PKG / "overlay"

def write_page(dir: Path, proj: dict, data: dict, tl: dict) -> Path:
    dir = Path(dir); b = dir / "build"
    ident = IDENTITY.get(proj.get("identity", "climbday"), IDENTITY["climbday"])
    html = (HERE / "overlay.html").read_text(encoding="utf-8")
    html = (html.replace("__FONTS__", "file://" + str(fonts_dir())).replace("__BONE__", ident["bone"])
                .replace("__OR__", ident["orange"]).replace("__WATERMARK__", ident["watermark"]))
    titles = {s["key"]: s["title"] for s in proj["scenes"] if s.get("title")}
    opts = {}; (b / "assets").mkdir(exist_ok=True)
    for s in proj["scenes"]:
        o = {"fx": s.get("fx") or [], "style": s.get("style"), "en": (s.get("caption_en") or "") if (proj.get("captions") or {}).get("en", True) else ""}
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
