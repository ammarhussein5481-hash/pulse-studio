"""pulse-reel — build a 60 s 9:16 story from a training session: clips + voice-over + Pulse data.

  pulse-reel new <dir> --date 2026-11-01 --type hyrox      create project.json + folders (put clips in raw/, voice in vo/)
  pulse-reel ingest <dir>                                   list clips by shoot time, motion profile, contact sheets (build/sheet_*.jpg)
  pulse-reel data <dir> [--force]                           fetch session data from Pulse (needs PULSE_TOKEN) or local file
  pulse-reel stt <dir> [--force]                            transcribe vo files with word timestamps → build/stt_*.json
  pulse-reel timeline <dir>                                 scenes → timeline.json (prints timing and tempo)
  pulse-reel stills <dir> [t1,t2,...]                       overlay QA stills → build/stills/
  pulse-reel build <dir> [--only key,key] [--no-frames]     base video, overlay frames, sfx, music, composite → out/<name>-vN.mp4
  pulse-reel audio <dir>                                    re-mix audio only (music/sfx/amb levels changed) → new out version
  pulse-reel publish <dir> [--to user@host:/path/]          scp the latest out file somewhere (default: PULSE_SHARE)
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, sys
from pathlib import Path
from . import project, ingest, data as datamod, stt as sttmod, timeline as tlmod, media, overlay, sfx, music, mix

def _latest_version(outdir: Path, name: str) -> int:
    vs = [int(p.stem.rsplit("-v", 1)[1]) for p in outdir.glob(f"{name}-v*.mp4") if p.stem.rsplit("-v", 1)[1].isdigit()]
    return max(vs) if vs else 0

def cmd_new(a):
    d = project.new(a.dir, a.name or Path(a.dir).name, a.date, a.type)
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
    d = datamod.fetch(a.dir, proj); return overlay.write_page(a.dir, proj, d, tl)

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
    if proj["audio"].get("sfx", True): sfx.generate(tl, b / "sfx.wav", tl["budget"])
    if proj["audio"].get("music", True): music.generate(tl["scenes"][-1]["start"], b / "music.wav")
    v = _latest_version(outdir, proj["name"]) + 1; out = outdir / f"{proj['name']}-v{v}.mp4"
    print(f"[mix] → {out.name}"); mix.composite(a.dir, proj, tl, out)
    info = mix.verify(out); mix.contact_sheet(out, outdir / f"{proj['name']}-v{v}.jpg")
    print(f"done: {out}  {info['duration']:.1f}s {info['mb']} MB {info['size']}  (sheet: {out.with_suffix('.jpg').name})")

def cmd_audio(a):
    proj, tl = _timeline(a); b = Path(a.dir) / "build"; outdir = Path(a.dir) / "out"
    if not (b / "frames").exists(): raise SystemExit("no frames yet — run: pulse-reel build <dir>")
    mix.vo_track(a.dir, tl, b / "vo_full.wav")
    if proj["audio"].get("sfx", True): sfx.generate(tl, b / "sfx.wav", tl["budget"])
    if proj["audio"].get("music", True) and not (b / "music.wav").exists(): music.generate(tl["scenes"][-1]["start"], b / "music.wav")
    v = _latest_version(outdir, proj["name"]) + 1; out = outdir / f"{proj['name']}-v{v}.mp4"
    mix.composite(a.dir, proj, tl, out); print(f"done: {out} {mix.verify(out)}")

def cmd_publish(a):
    proj = project.load(a.dir); outdir = Path(a.dir) / "out"; v = _latest_version(outdir, proj["name"])
    if not v: raise SystemExit("nothing built yet")
    src = outdir / f"{proj['name']}-v{v}.mp4"; dest = a.to or os.environ.get("PULSE_SHARE")
    if not dest: raise SystemExit("give --to user@host:/path/ or set PULSE_SHARE")
    import secrets; name = f"{proj['name']}-v{v}-{secrets.token_hex(4)}.mp4"
    subprocess.run(["scp", str(src), dest.rstrip("/") + "/" + name], check=True); print("published", name)

def main(argv=None):
    ap = argparse.ArgumentParser(prog="pulse-reel", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new"); p.add_argument("dir"); p.add_argument("--date", required=True); p.add_argument("--type", default="hyrox"); p.add_argument("--name"); p.set_defaults(f=cmd_new)
    p = sp.add_parser("ingest"); p.add_argument("dir"); p.add_argument("--no-sheets", action="store_true"); p.set_defaults(f=cmd_ingest)
    p = sp.add_parser("data"); p.add_argument("dir"); p.add_argument("--force", action="store_true"); p.set_defaults(f=cmd_data)
    p = sp.add_parser("stt"); p.add_argument("dir"); p.add_argument("--force", action="store_true"); p.set_defaults(f=cmd_stt)
    p = sp.add_parser("timeline"); p.add_argument("dir"); p.set_defaults(f=cmd_timeline)
    p = sp.add_parser("stills"); p.add_argument("dir"); p.add_argument("times", nargs="?"); p.set_defaults(f=cmd_stills)
    p = sp.add_parser("build"); p.add_argument("dir"); p.add_argument("--only"); p.add_argument("--no-frames", action="store_true"); p.set_defaults(f=cmd_build)
    p = sp.add_parser("audio"); p.add_argument("dir"); p.set_defaults(f=cmd_audio)
    p = sp.add_parser("publish"); p.add_argument("dir"); p.add_argument("--to"); p.set_defaults(f=cmd_publish)
    a = ap.parse_args(argv); a.f(a)

if __name__ == "__main__":
    main()
