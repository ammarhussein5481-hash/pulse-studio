"""pulse-reel — build a 9:16 story (60 s by default, --budget to change) from a training session: clips + voice-over + Pulse data.

  pulse-reel sessions [--refresh] [--json] [--root sessions] Pulse sessions (today / yesterday / earlier) from the VPS index
  pulse-reel new <dir> --from-pulse <id>                   project for that Pulse session (or --date D --type T [--no-data])
  pulse-reel ingest <dir>                                   list clips by shoot time, motion profile, contact sheets (build/sheet_*.jpg)
  pulse-reel data <dir> [--force]                           fetch session data from Pulse (needs PULSE_URL/PULSE_TOKEN), a local file, or none
  pulse-reel stt <dir> [--force]                            transcribe vo files with word timestamps → build/stt_*.json
  pulse-reel timeline <dir>                                 scenes → timeline.json (prints timing and tempo)
  pulse-reel stills <dir> [t1,t2,...]                       overlay QA stills → build/stills/
  pulse-reel build <dir> [--only key,key] [--no-frames]     base video, overlay frames, sfx, music, composite → out/<name>-vN.mp4
  pulse-reel audio <dir>                                    re-mix audio only (music/sfx/amb levels changed) → new out version
  pulse-reel publish <dir> [--to user@host:/path/]          scp the latest out file somewhere (default: PULSE_SHARE)
  pulse-reel preview <dir> <key> [--len 3]                 3 s of one scene with overlay + voice → build/preview/<key>.mp4
  pulse-reel import <dir> <sdcard-folder> [--date|--all]    copy that day's videos → raw/, audio → vo/
  pulse-reel suggest <dir> [--all]                          first draft: clips in shoot order, in-points from the motion profile
  pulse-reel preset save|apply|list|delete <name> --dir <d> fx / audio / length as a reusable template (~/.pulse-studio/presets)
  pulse-reel ui [--port 8787] [--root sessions]             local web app (opens in the browser) over the same steps
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path
from . import project, pulse, ingest, data as datamod, stt as sttmod, timeline as tlmod, media, overlay, sfx, music, mix, suggest as sugg
from .config import FPS, HOME, probe, node, chrome, ffmpeg

def _latest_version(outdir: Path, name: str) -> int:
    vs = [int(p.stem.rsplit("-v", 1)[1]) for p in outdir.glob(f"{name}-v*.mp4") if p.stem.rsplit("-v", 1)[1].isdigit()]
    return max(vs) if vs else 0

def cmd_sessions(a):
    idx = pulse.sessions(Path(a.root), refresh=a.refresh)
    print(json.dumps(idx, ensure_ascii=False) if a.json else pulse.describe(idx))

def cmd_new(a):
    if (Path(a.dir) / "project.json").exists(): raise SystemExit(f"{a.dir} already has a project.json")
    if a.from_pulse: project.new_from_pulse(a.dir, a.name or Path(a.dir).name, pulse.find(a.from_pulse))
    elif a.date: project.new(a.dir, a.name or Path(a.dir).name, a.date, a.type)
    else: raise SystemExit("give --from-pulse <id> (see: pulse-reel sessions) or --date YYYY-MM-DD")
    pj = project.load(a.dir)
    if a.budget: pj["vo"]["budget_s"] = a.budget
    if a.no_data: pj["session"]["source"] = "none"
    project.save(a.dir, pj)
    print(f"created {a.dir}/project.json — add clips to raw/, voice-over to vo/, then: pulse-reel ingest {a.dir}")

def cmd_ingest(a):
    clips = ingest.inventory(a.dir, sheets=not a.no_sheets); print(ingest.describe(clips)); print(f"\n{len(clips)} clips · sheets in {a.dir}/build/sheet_*.jpg")

def cmd_data(a):
    proj = project.load(a.dir); d = datamod.fetch(a.dir, proj, force=a.force); print(datamod.summary(d))

def cmd_stt(a):
    proj = project.load(a.dir); res = sttmod.transcribe_project(a.dir, proj, force=a.force)
    for name, segs in res.items():
        print(f"\n[{name}]"); print(sttmod.print_words(segs))

def _timeline(a):
    proj = project.load(a.dir); b = Path(a.dir) / "build"
    stt = {}
    for f in b.glob("stt_*.json"): stt[f.stem[4:]] = json.loads(f.read_text(encoding="utf-8"))
    if not stt: raise SystemExit("no transcripts — run: pulse-reel stt <dir>")
    tl = tlmod.build(a.dir, proj, stt); return proj, tl

def cmd_timeline(a):
    _, tl = _timeline(a); print(tlmod.describe(tl))

def _page(a, proj, tl):
    d = datamod.enrich(a.dir, proj, datamod.fetch(a.dir, proj), tl); return overlay.write_page(a.dir, proj, d, tl)

def cmd_stills(a):
    proj, tl = _timeline(a); _page(a, proj, tl)
    times = [float(x) for x in a.times.split(",")] if a.times else [round((s["start"] + s["end"]) / 2, 1) for s in tl["scenes"]]
    for p in overlay.stills(a.dir, times): print(p)

def cmd_build(a):
    proj, tl = _timeline(a); print(tlmod.describe(tl)); b = Path(a.dir) / "build"; outdir = Path(a.dir) / "out"; outdir.mkdir(exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    print("[base] cutting scenes …"); media.build(a.dir, proj, tl, only=only)
    _page(a, proj, tl)
    if not a.no_frames:
        print("[overlay] rendering frames …"); overlay.frames(a.dir, tl["budget"])
    print("[audio] vo / sfx / music …")
    mix.vo_track(a.dir, tl, b / "vo_full.wav")
    if proj["audio"].get("sfx", True): sfx.generate(tl, b / "sfx.wav", tl["budget"], proj=proj)
    if proj["audio"].get("music", True): music.prepare(proj, tl, b / "music.wav")
    v = _latest_version(outdir, proj["name"]) + 1; out = outdir / f"{proj['name']}-v{v}.mp4"
    print(f"[mix] → {out.name}"); mix.composite(a.dir, proj, tl, out)
    info = mix.verify(out); mix.contact_sheet(out, outdir / f"{proj['name']}-v{v}.jpg")
    print(f"done: {out}  {info['duration']:.1f}s {info['mb']} MB {info['size']}  (sheet: {out.with_suffix('.jpg').name})")

def cmd_audio(a):
    proj, tl = _timeline(a); b = Path(a.dir) / "build"; outdir = Path(a.dir) / "out"
    if not (b / "frames").exists(): raise SystemExit("no frames yet — run: pulse-reel build <dir>")
    mix.vo_track(a.dir, tl, b / "vo_full.wav")
    if proj["audio"].get("sfx", True): sfx.generate(tl, b / "sfx.wav", tl["budget"], proj=proj)
    if proj["audio"].get("music", True): music.prepare(proj, tl, b / "music.wav")
    v = _latest_version(outdir, proj["name"]) + 1; out = outdir / f"{proj['name']}-v{v}.mp4"
    mix.composite(a.dir, proj, tl, out); print(f"done: {out} {mix.verify(out)}")

def cmd_preview(a):
    """3 s of ONE scene with its overlay + voice, in ~20-40 s instead of a full build → build/preview/<key>.mp4"""
    proj, tl = _timeline(a); d = Path(a.dir); b = d / "build"; pv = b / "preview"; pv.mkdir(exist_ok=True)
    s = next((x for x in tl["scenes"] if x["key"] == a.key), None); sc = next((x for x in proj["scenes"] if x["key"] == a.key), None)
    if not s or not sc: raise SystemExit(f"no scene {a.key}")
    L = min(float(a.len), s["end"] - s["start"]); src = d / "raw" / sc["clip"]; info = probe(src)
    media.cut_scene(src, sc, info, float(sc.get("in", 0)), round(L, 3), pv / "v.mp4", pv / "a.m4a")
    _page(a, proj, tl); f0 = int(round(s["start"] * FPS)); f1 = f0 + int(round(L * FPS))
    fr = pv / "frames"; shutil.rmtree(fr, ignore_errors=True)
    subprocess.run([node(), str(Path(overlay.__file__).parent / "render.mjs"), chrome(), str(b / "overlay.html"), "frames", str(fr), str(f0), str(f1), str(FPS)], check=True)
    mix.vo_track(a.dir, tl, b / "vo_full.wav")
    out = pv / f"{a.key}.mp4"; amb = float(proj["audio"].get("amb_db", -4))
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-i", str(pv / "v.mp4"), "-start_number", str(f0), "-framerate", str(FPS), "-i", str(fr / "%05d.png"),
                    "-i", str(pv / "a.m4a"), "-ss", str(s["start"]), "-t", str(L), "-i", str(b / "vo_full.wav"),
                    "-filter_complex", f"[0:v][1:v]overlay=0:0:format=auto[v];[2:a]volume={amb}dB[amb];[amb][3:a]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "[v]", "-map", "[a]", "-t", str(L), "-c:v", "libx264", "-preset", "fast", "-crf", "21", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(out)], check=True)
    print(f"preview: {out}  ({L:.1f}s of {a.key})")

VIDEO_EXT = {".mov", ".mp4", ".m4v", ".mkv"}; AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac"}
def cmd_import(a):
    """Copy a day's files from an SD card / phone folder into raw/ (video) and vo/ (audio)."""
    import datetime
    proj = project.load(a.dir); d = Path(a.dir); src = Path(a.src)
    if not src.exists(): raise SystemExit(f"{src} not found")
    want = None if a.all else (a.date or proj["session"].get("date"))
    n = 0
    for f in sorted(src.rglob("*")):
        if not f.is_file() or f.name.startswith("."): continue
        ext = f.suffix.lower(); sub = "raw" if ext in VIDEO_EXT else "vo" if ext in AUDIO_EXT else None
        if not sub: continue
        day = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
        if want and day != want: continue
        dest = d / sub / f.name
        if dest.exists() and dest.stat().st_size == f.stat().st_size: print(f"  = {f.name} (already there)"); continue
        print(f"  + {f.name} → {sub}/  ({f.stat().st_size / 1e6:.0f} MB)", flush=True); shutil.copy2(f, dest); n += 1
    print(f"imported {n} file(s){' from ' + want if want else ''}" + ("\nnext: pulse-reel ingest " + str(d) if n else ""))

def cmd_suggest(a):
    proj = project.load(a.dir); notes = sugg.suggest(a.dir, proj, overwrite_in=a.all); project.save(a.dir, proj)
    print("\n".join("  " + x for x in notes) or "  nothing to suggest"); print("edit project.json / the web app to adjust, then: pulse-reel timeline")

PRESET_KEYS = ("fx", "style", "inset", "phone", "amb_db", "crop")
def cmd_preset(a):
    pd = HOME / "presets"; pd.mkdir(parents=True, exist_ok=True)
    if a.action == "list":
        for f in sorted(pd.glob("*.json")): print(" ", f.stem); return
    if a.action == "delete": (pd / f"{a.name}.json").unlink(missing_ok=True); print("deleted", a.name); return
    proj = project.load(a.dir); f = pd / f"{a.name}.json"
    if a.action == "save":
        pr = {"budget_s": proj["vo"].get("budget_s", 60), "audio": proj["audio"], "identity": proj.get("identity"),
              "scenes": {s["key"]: {k: s[k] for k in PRESET_KEYS if s.get(k) not in (None, [], "auto")} for s in proj["scenes"]}}
        f.write_text(json.dumps(pr, ensure_ascii=False, indent=1), encoding="utf-8"); print("saved preset", a.name, "→", f); return
    if a.action == "apply":
        if not f.exists(): raise SystemExit(f"no preset {a.name} (pulse-reel preset list)")
        pr = json.loads(f.read_text(encoding="utf-8")); proj["vo"]["budget_s"] = pr.get("budget_s", proj["vo"].get("budget_s", 60))
        proj["audio"].update(pr.get("audio", {})); proj["identity"] = pr.get("identity") or proj.get("identity")
        for s in proj["scenes"]:
            for k, v in pr.get("scenes", {}).get(s["key"], {}).items(): s[k] = v
        project.save(a.dir, proj); print("applied preset", a.name)

def cmd_publish(a):
    proj = project.load(a.dir); outdir = Path(a.dir) / "out"; v = _latest_version(outdir, proj["name"])
    if not v: raise SystemExit("nothing built yet")
    src = outdir / f"{proj['name']}-v{v}.mp4"; dest = a.to or os.environ.get("PULSE_SHARE")
    if not dest: raise SystemExit("give --to user@host:/path/ or set PULSE_SHARE")
    import secrets; name = f"{proj['name']}-v{v}-{secrets.token_hex(4)}.mp4"
    subprocess.run(["scp", str(src), dest.rstrip("/") + "/" + name], check=True); print("published", name)

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["ui"]:
        from .ui.server import main as ui_main; return ui_main(argv[1:])
    ap = argparse.ArgumentParser(prog="pulse-reel", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("sessions"); p.add_argument("--refresh", action="store_true"); p.add_argument("--json", action="store_true"); p.add_argument("--root", default=os.environ.get("PULSE_SESSIONS", "sessions")); p.set_defaults(f=cmd_sessions)
    p = sp.add_parser("new"); p.add_argument("dir"); p.add_argument("--from-pulse", metavar="ID"); p.add_argument("--date"); p.add_argument("--type", default="hyrox"); p.add_argument("--no-data", action="store_true", help="no Pulse numbers: titles + captions only"); p.add_argument("--name"); p.add_argument("--budget", type=float, help="target length in seconds (default 60)"); p.set_defaults(f=cmd_new)
    p = sp.add_parser("ingest"); p.add_argument("dir"); p.add_argument("--no-sheets", action="store_true"); p.set_defaults(f=cmd_ingest)
    p = sp.add_parser("data"); p.add_argument("dir"); p.add_argument("--force", action="store_true"); p.set_defaults(f=cmd_data)
    p = sp.add_parser("stt"); p.add_argument("dir"); p.add_argument("--force", action="store_true"); p.set_defaults(f=cmd_stt)
    p = sp.add_parser("timeline"); p.add_argument("dir"); p.set_defaults(f=cmd_timeline)
    p = sp.add_parser("stills"); p.add_argument("dir"); p.add_argument("times", nargs="?"); p.set_defaults(f=cmd_stills)
    p = sp.add_parser("build"); p.add_argument("dir"); p.add_argument("--only"); p.add_argument("--no-frames", action="store_true"); p.set_defaults(f=cmd_build)
    p = sp.add_parser("audio"); p.add_argument("dir"); p.set_defaults(f=cmd_audio)
    p = sp.add_parser("publish"); p.add_argument("dir"); p.add_argument("--to"); p.set_defaults(f=cmd_publish)
    p = sp.add_parser("preview"); p.add_argument("dir"); p.add_argument("key"); p.add_argument("--len", default="3"); p.set_defaults(f=cmd_preview)
    p = sp.add_parser("import"); p.add_argument("dir"); p.add_argument("src"); p.add_argument("--date"); p.add_argument("--all", action="store_true"); p.set_defaults(f=cmd_import)
    p = sp.add_parser("suggest"); p.add_argument("dir"); p.add_argument("--all", action="store_true", help="also overwrite in-points already set"); p.set_defaults(f=cmd_suggest)
    p = sp.add_parser("preset"); p.add_argument("action", choices=["save", "apply", "list", "delete"]); p.add_argument("name", nargs="?"); p.add_argument("--dir", default="."); p.set_defaults(f=cmd_preset)
    a = ap.parse_args(argv); a.f(a)

if __name__ == "__main__":
    main()
