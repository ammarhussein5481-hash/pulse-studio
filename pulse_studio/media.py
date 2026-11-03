"""Base video: cut each scene from its clip, crop to 9:16, concat, grain + vignette; per-scene ambience track."""
from __future__ import annotations
import subprocess
from pathlib import Path
from .config import ffmpeg, probe, W, H, FPS, venc, vaapi_tail, vaapi_dev

GLASS = (90, 290, 900, 640)   # x, y, w, h of the liquid-glass pane (must match #glass in overlay.html)

def _vf(sc: dict, info: dict) -> str:
    crop = sc.get("crop", "auto")
    vertical = (info["width"] or 0) < (info["height"] or 1)
    if crop == "full" or (crop == "auto" and vertical):
        return f"scale={W}:{H}"
    if crop == "auto":
        return f"crop=ih*9/16:ih,scale={W}:{H}"
    return f"crop={crop},scale={W}:{H}"   # explicit "w:h:x:y" on the source (e.g. 2× punch-in)

def hwaccel_args() -> list[str]:
    """Intel/AMD VAAPI decode when available (Ubuntu laptop) — big win on 4K sources. Falls back silently."""
    import os
    dev = "/dev/dri/renderD128"
    if os.path.exists(dev) and os.environ.get("PULSE_NO_VAAPI") != "1":
        return ["-hwaccel", "vaapi", "-hwaccel_device", dev, "-hwaccel_output_format", "vaapi"]
    return []

def cut_scene(src: Path, sc: dict, info: dict, ss: float, d: float, tv: Path, ta: Path) -> None:
    """Cut one scene: crop/scale to 9:16, fx (zoomcut, glass), 30 fps, 2 s clone pad; ambience track at sc.amb_db."""
    fx = set(sc.get("fx") or [])
    vf = _vf(sc, info) + f",fps={FPS}"
    if "zoomcut" in fx:   # snap zoom: start 16 % in, settle over 11 frames (pairs with the whoosh + flash on the cut)
        vf += f",zoompan=z='if(lt(on,11),1.16-0.016*on,1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}"
    if "pullback" in fx:  # pull-back reveal: start 1.9× on the detail (scene.focus = [x, y] as fractions, default centre) and ease out over 40 frames
        fx_, fy_ = (sc.get("focus") or [0.5, 0.5])[:2]
        vf += (f",zoompan=z='if(lt(on,40),1+0.9*pow(1-on/40,2),1)':x='({fx_}*iw)-(iw/zoom)*{fx_}':y='({fy_}*ih)-(ih/zoom)*{fy_}':d=1:s={W}x{H}:fps={FPS}")
    vf += ",setsar=1,tpad=stop_mode=clone:stop_duration=2"
    tail = ""
    if "glass" in fx:     # liquid glass: blur the region behind the title block; the overlay draws the pane's edge + tint
        tail = f";[v0]split[ga][gb];[gb]crop={GLASS[2]}:{GLASS[3]}:{GLASS[0]}:{GLASS[1]},boxblur=26:2[gbl];[ga][gbl]overlay={GLASS[0]}:{GLASS[1]}[v]"
    hw = hwaccel_args()
    # hw frames skip ffmpeg's autorotate: apply the display rotation by hand after download
    turn = {90: "transpose=cclock,", 180: "hflip,vflip,", 270: "transpose=clock,"}.get(info.get("rotation", 0), "")
    def fc(v):   # [0:v] → filters → [v0] → (glass) → [v1] → (hwupload for VAAPI) → [v]
        chain = f"[0:v]{v}[v0]" + (tail.replace("[v]", "[v1]") if tail else ";[v0]null[v1]")
        return chain + f";[v1]null{vaapi_tail()}[v]"
    vf_hw = ("hwdownload,format=nv12," + turn + vf) if hw else vf
    cmd = [ffmpeg(), "-nostdin", "-y", "-v", "error", *vaapi_dev(), *hw, "-ss", str(ss), "-i", str(src), "-t", str(d), "-an", "-filter_complex", fc(vf_hw), "-map", "[v]",
           *venc("cut"), str(tv)]
    r = subprocess.run(cmd)
    if r.returncode != 0:
        if not hw:
            raise SystemExit(f"ffmpeg failed on {sc['clip']}")
        # VAAPI refused this file (codec/profile) → plain software decode
        subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", *vaapi_dev(), "-ss", str(ss), "-i", str(src), "-t", str(d), "-an", "-filter_complex", fc(vf), "-map", "[v]",
                        *venc("cut"), str(tv)], check=True)
    amp = float(sc.get("amb_db", -9))
    r = subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-ss", str(ss), "-i", str(src), "-t", str(d), "-vn", "-ac", "2", "-ar", "48000",
                        "-af", f"apad=whole_dur={d},volume={amp}dB", "-c:a", "aac", "-b:a", "160k", str(ta)])
    if r.returncode != 0:   # clip without an audio stream (screen recording, some phone exports): silence of the same length
        subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(d), "-c:a", "aac", "-b:a", "96k", str(ta)], check=True)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

def shots_of(sc: dict) -> list[dict]:
    """A scene's media in order: its `shots` list, or the single clip/in/crop as one shot."""
    if sc.get("shots"): return [dict(s) for s in sc["shots"] if s.get("file")]
    return [{"file": sc.get("clip"), "in": sc.get("in", 0), "crop": sc.get("crop", "auto"), "w": 1}] if sc.get("clip") else []

def cut_photo(src: Path, sc: dict, d: float, tv: Path, ta: Path) -> None:
    """A still as a video segment with a slow push-in (Ken Burns) + silent track."""
    vf = (f"scale={W * 1.12:.0f}:{H * 1.12:.0f}:force_original_aspect_ratio=increase,crop={W * 1.12:.0f}:{H * 1.12:.0f},"
          f"zoompan=z='1+0.0015*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS},setsar=1")
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", *vaapi_dev(), "-loop", "1", "-i", str(src), "-t", str(d), "-vf", vf + vaapi_tail(),
                    *venc("cut"), str(tv)], check=True)
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(d), "-c:a", "aac", "-b:a", "96k", str(ta)], check=True)

def cut_shots(b: Path, raw: Path, sc: dict, key: str, d: float, i, tv: Path, ta: Path) -> None:
    """All shots of one scene → one video + one ambience track of exactly d seconds (shots share d by their weights)."""
    shots = shots_of(sc)
    if not shots: raise SystemExit(f"scene {key}: no clip or shots")
    wsum = sum(float(x.get("w") or 1) for x in shots); parts_v, parts_a = [], []
    durs = [round(d * float(x.get("w") or 1) / wsum, 3) for x in shots]; durs[-1] = round(d - sum(durs[:-1]), 3)
    for j, sh in enumerate(shots):
        dj = durs[j]; src = raw / sh["file"]; pv, pa = (tv, ta) if len(shots) == 1 else (b / f"t{i}_{j}.mp4", b / f"t{i}_{j}.m4a")
        scj = {**sc, "crop": sh.get("crop", "auto"), "amb_db": sh.get("amb_db", sc.get("amb_db", -9)), "fx": (sc.get("fx") or []) if j == 0 else [x for x in (sc.get("fx") or []) if x != "zoomcut"]}
        if src.suffix.lower() in IMAGE_EXT:
            cut_photo(src, scj, dj, pv, pa)
        else:
            info = probe(src); ss = float(sh.get("in", 0) or 0)
            if ss + dj > info["duration"] + 0.05: print(f"  ! {key}: {sh['file']} is {info['duration']:.1f}s, needs in={ss}+{dj:.1f}s — will freeze last frame")
            cut_scene(src, scj, info, ss, dj, pv, pa)
        parts_v.append(pv); parts_a.append(pa)
    if len(shots) > 1:
        for lst, out, codec in ((parts_v, tv, ["-c", "copy"]), (parts_a, ta, ["-c:a", "aac", "-b:a", "160k"])):
            f = b / f"t{i}_{'v' if out == tv else 'a'}.txt"; f.write_text("".join(f"file '{p.resolve()}'\n" for p in lst))
            subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(f), *codec, str(out)], check=True)
    print(f"  scene {i} {key} done ({len(shots)} shot{'s' if len(shots) > 1 else ''})", flush=True)

def build(dir: Path, proj: dict, tl: dict, only: set[str] | None = None) -> tuple[Path, Path]:
    dir = Path(dir); b = dir / "build"; raw = dir / "raw"
    byk = {s["key"]: s for s in proj["scenes"]}
    vlist, alist = [], []
    import hashlib, json as _json
    man = b / "cuts_manifest.json"; old = _json.loads(man.read_text()) if man.exists() else {}; new = {}; changed = 0
    for i, s in enumerate(tl["scenes"], 1):
        sc = byk[s["key"]]; d = round(s["end"] - s["start"], 3)
        tv, ta = b / f"t{i}.mp4", b / f"t{i}.m4a"
        fp = hashlib.sha1(_json.dumps({"d": d, "shots": shots_of(sc), "fx": sc.get("fx"), "amb": sc.get("amb_db"), "crop": sc.get("crop"),
                                       "mtime": [int((raw / x["file"]).stat().st_mtime) for x in shots_of(sc) if (raw / x["file"]).exists()]}, sort_keys=True, default=str).encode()).hexdigest()[:12]
        new[str(i)] = fp
        if (only is not None and s["key"] in only) or old.get(str(i)) != fp or not tv.exists() or not ta.exists():
            cut_shots(b, raw, sc, s["key"], d, i, tv, ta); changed += 1
        vlist.append(tv); alist.append(ta)
    man.write_text(_json.dumps(new), encoding="utf-8")
    print(f"  cuts: {changed} re-cut, {len(vlist) - changed} reused", flush=True)
    if changed == 0 and (b / "base_v.mp4").exists() and (b / "base_a.m4a").exists() and old == new:
        return b / "base_v.mp4", b / "base_a.m4a"
    (b / "vlist.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in vlist))
    (b / "alist.txt").write_text("".join(f"file '{p.resolve()}'\n" for p in alist))
    base_v, base_a = b / "base_v.mp4", b / "base_a.m4a"
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", *vaapi_dev(), "-f", "concat", "-safe", "0", "-i", str(b / "vlist.txt"), "-vf",
                    "noise=alls=7:allf=t,vignette=PI/5,format=yuv420p" + vaapi_tail(), *venc("mid"), "-r", str(FPS), str(base_v)], check=True)
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(b / "alist.txt"), "-c:a", "aac", "-b:a", "160k", str(base_a)], check=True)
    return base_v, base_a
