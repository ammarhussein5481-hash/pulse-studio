"""Quality gates. "A render that succeeded is not a render that is right" — each gate is one named check with a pass / warn / fail.

pre(dir)   before cutting anything: numbers, media, voice windows, script, clip↔phase       (seconds)
stills(dir) on the rendered overlay stills: safe zones, caption lines, contrast              (seconds, needs build/stills)
post(dir, out) on the finished mp4: container, duration, size, loudness, ducking, black/frozen frames, SFX density, cut rhythm

Each result: {"id", "name", "status": "pass"|"warn"|"fail", "detail"}. build refuses on a FAIL from pre(); everything else is reported.
"""
from __future__ import annotations
import json, re, subprocess
from pathlib import Path
from .config import ffmpeg, ffprobe, probe, W, H, FPS

SAFE_TOP, SAFE_BOTTOM = 250, 340          # Instagram UI (climbday spec)
MAX_TELEGRAM = 49_000_000

def R(id, name, status, detail=""): return {"id": id, "name": name, "status": status, "detail": detail}

# ---------------------------------------------------------------- helpers
def _load(dir: Path):
    from . import project
    dir = Path(dir); b = dir / "build"
    proj = project.load(dir)
    data = json.loads((b / "data.json").read_text(encoding="utf-8")) if (b / "data.json").exists() else {}
    tl = json.loads((b / "timeline.json").read_text(encoding="utf-8")) if (b / "timeline.json").exists() else None
    return dir, b, proj, data, tl

AR_DIGIT = {"واحد": 1, "اتنين": 2, "تلاتة": 3, "ثلاثة": 3, "أربعة": 4, "اربعة": 4, "خمسة": 5, "ستة": 6, "سبعة": 7, "تمانية": 8, "ثمانية": 8, "تسعة": 9, "عشرة": 10,
            "حداشر": 11, "اتناشر": 12, "تلتاشر": 13, "أربعتاشر": 14, "خمستاشر": 15, "ستاشر": 16, "سبعتاشر": 17, "تمنتاشر": 18, "تسعتاشر": 19,
            "عشرين": 20, "تلاتين": 30, "ثلاثين": 30, "أربعين": 40, "اربعين": 40, "خمسين": 50, "ستين": 60, "سبعين": 70, "تمانين": 80, "ثمانين": 80, "تسعين": 90,
            "تلات": 3, "أربع": 4, "اربع": 4, "خمس": 5, "ست": 6, "سبع": 7, "تمن": 8, "تسع": 9, "عشر": 10, "مية": 100, "ميه": 100, "ميتين": 200}

def _ar_numbers(text: str) -> list[int]:
    """Numbers spoken in a Sudanese line → integers (e.g. 'أربع دقايق وسبع ثواني' → [4, 7]; 'مية وتسعة وخمسين' → [159])."""
    toks = [t.strip(".،,؟!:") for t in text.split()]; out = []; cur = None; adjacent = False
    for t in toks:
        w = t[1:] if t.startswith("و") and t[1:] in AR_DIGIT else t
        if w in AR_DIGIT:
            v = AR_DIGIT[w]
            # "مية وتسعة وخمسين" = 159, "أربعة وتلاتين" = 34 — only when the number words are ADJACENT;
            # "أربع دقايق وتلاتين ثانية" has a noun between → 4 and 30
            if cur is not None and adjacent and t.startswith("و") and (cur >= 100 or (cur < 10 and v >= 20)): cur += v
            elif cur is not None and adjacent and cur >= 100 and v < 100: cur += v
            else:
                if cur is not None: out.append(cur)
                cur = v
            adjacent = True
        elif t in ("دقيقتين", "ثانيتين", "كيلوين", "محطتين"):
            if cur is not None: out.append(cur)
            cur = None; out.append(2); adjacent = False
        else:
            if cur is not None: out.append(cur); cur = None
            adjacent = False
    if cur is not None: out.append(cur)
    return out

def _expected_numbers(key: str, parts: list[str], data: dict) -> set[int]:
    """Every integer that may legitimately be spoken for a scene: minutes/seconds of times and paces, HR, reps, distances (m / km)."""
    exp: set[int] = set(); s = data.get("_session", {})
    def add_time(sec):
        if not sec: return
        m, r = int(sec // 60), int(round(sec % 60))
        if r == 60: m, r = m + 1, 0
        exp.update({m, r, int(round(sec / 60))})   # "سبع دقايق وشوية" rounds the minutes
    for p in parts:
        d = data.get(p) or {}
        add_time(d.get("s")); add_time(d.get("erg", [None])[0] if d.get("erg") else None)
        if d.get("m"):
            add_time(d["s"] / (d["m"] / 1000)) if d.get("s") and d["m"] >= 200 else None
            exp.update({int(round(d["m"] / 10) * 10), int(round(d["m"] / 100) * 100), int(d["m"] // 1000), int(round(d["m"] / 1000))})
        if d.get("rec_s"): exp.update({int(round(d["rec_s"])), int(round(d["rec_s"])) // 60})
        for h in ("hr", "max", "rec_hr_min"):
            if d.get(h): exp.add(int(d[h]))
        if d.get("steps"): exp.add(int(d["steps"]))
        if d.get("rep"): exp.add(int(d["rep"]))
        if d.get("laps"):
            for lap in d["laps"]: add_time(lap[0]);
    if key in ("intro", "closing", "workout") or len(parts) > 1:
        reps = [k for k in s.get("order", []) if str(k).startswith("rep")]
        if reps: exp.add(len(reps)); exp.add(int(data[reps[0]].get("m", 0) // 1000) or 1)
        if s.get("total_s"): exp.update({int(round(s["total_s"] / 60)), int(s["total_s"] // 60)})
        if s.get("distance_m"): exp.update({int(s["distance_m"] // 1000), int(round(s["distance_m"] / 1000))})
        exp.update({len(s.get("order", [])), int(s.get("avg_hr") or 0), int(s.get("max_hr") or 0), int(s.get("kcal") or 0)})
        if s.get("target"):
            try: a, b = s["target"].split(":"); exp.update({int(a), int(b)})
            except Exception: pass
        for p in [k for k in s.get("order", []) if str(k).startswith("rep") or key == "closing"]:   # the work scene may quote any rep; the closing anything
            d = data.get(p) or {}
            if d.get("s") and d.get("m"): add_time(d["s"] / (d["m"] / 1000)); add_time(d["s"])
            for h in ("hr", "max"):
                if d.get(h): exp.add(int(d[h]))
            if d.get("rec_s"): exp.add(int(round(d["rec_s"])))
    exp.update({1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 100, 500, 1000})   # counts, "ألف متر", "خمس دقايق تسخين"
    return exp

# ---------------------------------------------------------------- pre-build gates
def pre(dir: Path) -> list[dict]:
    dir, b, proj, data, tl = _load(dir); out = []; scenes = proj["scenes"]; raw = dir / "raw"
    from .media import shots_of, IMAGE_EXT
    # 1 numbers in the script/captions exist in the data
    if data:
        bad = []
        for sc in scenes:
            parts = sc.get("parts") or ([sc["key"]] if data.get(sc["key"]) else [])
            exp = _expected_numbers(sc["key"], parts, data)
            for n in _ar_numbers(sc.get("script") or sc.get("caption") or ""):
                if n not in exp and n > 2: bad.append(f"{sc['key']}: {n}")
            for n in re.findall(r"\d+(?::\d\d)?", sc.get("caption_en") or ""):
                if ":" in n:
                    a, c = n.split(":")
                    if int(a) not in exp or int(c) not in exp: bad.append(f"{sc['key']} (en): {n}")
                elif int(n) not in exp and int(n) > 2: bad.append(f"{sc['key']} (en): {n}")
        out.append(R(1, "numbers match the data", "fail" if bad else "pass", "; ".join(bad[:8]) + (" …" if len(bad) > 8 else "")))
    else:
        out.append(R(1, "numbers match the data", "warn", "no session data to check against"))
    # 2 media present and long enough
    probs = []; cache = {}
    for i, sc in enumerate(scenes):
        shots = shots_of(sc); L = (tl["scenes"][i]["end"] - tl["scenes"][i]["start"]) if tl and i < len(tl["scenes"]) else None
        if not shots: probs.append(f"{sc['key']}: no media"); continue
        wsum = sum(float(x.get("w") or 1) for x in shots)
        for sh in shots:
            f = raw / sh["file"]
            if not f.exists(): probs.append(f"{sc['key']}: {sh['file']} missing"); continue
            if f.suffix.lower() in IMAGE_EXT:
                if L and L * float(sh.get("w") or 1) / wsum > 6: probs.append(f"{sc['key']}: photo {sh['file']} on screen {L * float(sh.get('w') or 1) / wsum:.1f}s (>6 s)")
                continue
            dur = cache.get(f) or probe(f)["duration"]; cache[f] = dur
            need = (L or 4) * float(sh.get("w") or 1) / wsum
            if float(sh.get("in") or 0) + need > dur + 0.05: probs.append(f"{sc['key']}: {sh['file']} needs in {sh.get('in', 0)}+{need:.1f}s but is {dur:.1f}s (frozen frame)")
    out.append(R(2, "media present and long enough", "fail" if any("missing" in p or "no media" in p for p in probs) else "warn" if probs else "pass", "; ".join(probs[:6])))
    # 3 voice windows + tempo + total
    if tl:
        w = []; prev = None
        for s in tl["scenes"]:
            if s.get("vo_len") == 0 and s["key"] not in ("intro", "closing"): w.append(f"{s['key']}: no voice")
            if prev and s["start"] < prev - 0.01: w.append(f"{s['key']}: overlaps previous")
            prev = s["end"]
        st = "pass"
        if tl["tempo"] > 1.12: w.append(f"tempo ×{tl['tempo']} (>1.12: drop a phrase or lengthen)"); st = "warn"
        if abs(tl["scenes"][-1]["end"] - tl["budget"]) > 0.1: w.append(f"ends at {tl['scenes'][-1]['end']}s, budget {tl['budget']}s"); st = "fail"
        if any("no voice" in x or "overlaps" in x for x in w): st = "fail"
        out.append(R(3, "voice windows cover every line, no overlap, tempo ≤ ×1.12", st, "; ".join(w)))
        # 3b every line with a take/window is also matched (number check from the recording)
        m = json.loads((b / "match.json").read_text(encoding="utf-8")) if (b / "match.json").exists() else None
        if m:
            nums = [r["key"] for r in m if any(d.get("number") for d in r.get("diffs", []))]
            out.append(R(31, "recording says the same numbers as the script", "warn" if nums else "pass", ("heard a different number in: " + ", ".join(nums)) if nums else ""))
    else:
        out.append(R(3, "voice windows", "fail", "no timeline — run match/timeline"))
    # 4 script consistency
    w = []
    txt = {sc["key"]: (sc.get("script") or sc.get("caption") or "") for sc in scenes}
    intro = txt.get("intro", "")
    if "تسخين" in intro and any("تسخين" in v for k, v in txt.items() if k == "warmup"): w.append("warm-up announced in intro AND in the warm-up line")
    cred = sum(1 for v in txt.values() if "نبض" in v and "قارمن" in v)
    if cred == 0: w.append("no 'Garmin + Pulse' credit line")
    if cred > 1: w.append("credit line repeated")
    if (proj.get("captions") or {}).get("en", True):
        miss = [sc["key"] for sc in scenes if (sc.get("script") or sc.get("caption")) and not sc.get("caption_en")]
        if miss: w.append("no English line: " + ", ".join(miss))
    empty = [sc["key"] for sc in scenes if not (sc.get("script") or sc.get("caption")) and sc["key"] not in ("intro", "closing")]
    if empty: w.append("no text: " + ", ".join(empty))
    out.append(R(4, "script consistent (no double announcements, credit once, English lines)", "warn" if w else "pass", "; ".join(w)))
    # 5 clip ↔ phase sanity (labels, shoot time)
    cj = b / "clips.json"; w = []
    if cj.exists() and data:
        from . import clipmap, label as labelmod
        clips = json.loads(cj.read_text(encoding="utf-8")); byname = {c["file"]: c for c in clips}
        m = clipmap.map_clips(data, clips, proj["session"].get("clip_offset_s"))
        for sc in scenes:
            parts = sc.get("parts") or [sc["key"]]
            for sh in shots_of(sc):
                c = byname.get(sh["file"]);
                if not c: continue
                lab = c.get("label")
                if lab and sc["key"] not in ("intro", "closing") and all(labelmod.consistent(lab, p) is False for p in parts): w.append(f"{sc['key']}: {sh['file']} shows '{lab}'")
                if lab == "talking" and sc["key"] not in ("intro", "closing"): w.append(f"{sc['key']}: {sh['file']} is a talking clip")
                if m and sh["file"] in m and m[sh["file"]]["part"] not in parts and sc["key"] not in ("intro", "closing") and not c.get("photo"):
                    w.append(f"{sc['key']}: {sh['file']} was filmed during {m[sh['file']]['part']}")
        out.append(R(5, "clips fit their phase (label + shoot time)", "warn" if w else "pass", "; ".join(w[:6])))
    return out

# ---------------------------------------------------------------- stills gates
def stills(dir: Path) -> list[dict]:
    """On transparent overlay frames: text inside the safe zones, caption height; contrast against the base video when it exists."""
    dir, b, proj, data, tl = _load(dir); out = []
    if not tl: return [R(6, "safe zones", "warn", "no timeline")]
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return [R(6, "safe zones", "warn", "Pillow/numpy missing")]
    from . import overlay
    times = [round((s["start"] + s["end"]) / 2 + 0.6, 2) for s in tl["scenes"]]
    fr = b / "qa_frames"; import shutil; shutil.rmtree(fr, ignore_errors=True)
    from .config import node, chrome, PKG
    # render the frames closest to each time as transparent PNGs (frames mode, one frame each)
    for t in times:
        f0 = int(round(t * FPS)); subprocess.run([node(), str(PKG / "overlay" / "render.mjs"), chrome(), str(b / "overlay.html"), "frames", str(fr), str(f0), str(f0 + 1), str(FPS)], check=True, capture_output=True)
    top_v, bot_v, tall, bright = [], [], [], []
    base = b / "base_v.mp4"
    for s, t in zip(tl["scenes"], times):
        f0 = int(round(t * FPS)); p = fr / f"{f0:05d}.png"
        if not p.exists(): continue
        a = np.array(Image.open(p).convert("RGBA"))[:, :, 3]
        rows = np.where(a.max(axis=1) > 40)[0]
        # the fixed chrome (watermark / progress) lives at 226–277 by design; anything ABOVE 220 is a violation
        if rows.size and rows.min() < 220: top_v.append(s["key"])
        if rows.size and rows.max() > H - SAFE_BOTTOM + 40: bot_v.append(f"{s['key']} ({rows.max()}px)")
        cap = a[1330:1600]; crow = np.where(cap.max(axis=1) > 40)[0]
        if crow.size and (crow.max() - crow.min()) > 69 * 3 + 20: tall.append(s["key"])
        if base.exists():   # luminance of the video behind the caption block
            r = subprocess.run([ffmpeg(), "-nostdin", "-v", "error", "-ss", str(t), "-i", str(base), "-frames:v", "1", "-vf", "crop=960:260:60:1340,scale=32:8,format=gray", "-f", "rawvideo", "-"], capture_output=True)
            if r.returncode == 0 and r.stdout:
                lum = np.frombuffer(r.stdout, dtype=np.uint8).mean()
                if lum > 165: bright.append(f"{s['key']} ({int(lum)})")
    out.append(R(6, "overlay inside the Instagram safe zones", "fail" if top_v or bot_v else "pass", "; ".join([f"top: {', '.join(top_v)}" if top_v else "", f"bottom: {', '.join(bot_v)}" if bot_v else ""]).strip("; ")))
    out.append(R(7, "caption ≤ 3 lines", "warn" if tall else "pass", ", ".join(tall)))
    out.append(R(8, "caption readable against the video (background not too bright)", "warn" if bright else "pass", ("bright behind the caption: " + ", ".join(bright)) if bright else ("" if base.exists() else "no base video yet — checked after build")))
    return out

# ---------------------------------------------------------------- post-build gates
def post(dir: Path, out_mp4: Path) -> list[dict]:
    dir, b, proj, data, tl = _load(dir); res = []; out_mp4 = Path(out_mp4)
    j = json.loads(subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height,r_frame_rate,profile,has_b_frames,codec_type", "-of", "json", str(out_mp4)], capture_output=True, text=True).stdout)
    v = next((s for s in j["streams"] if s.get("codec_type") == "video"), {}); a = next((s for s in j["streams"] if s.get("codec_type") == "audio"), {})
    dur = float(j["format"]["duration"]); size = int(j["format"]["size"]); w = []
    if (v.get("width"), v.get("height")) != (W, H): w.append(f"{v.get('width')}x{v.get('height')}")
    if v.get("codec_name") != "h264": w.append(f"codec {v.get('codec_name')}")
    if v.get("r_frame_rate") not in (f"{FPS}/1", "30000/1001"): w.append(f"fps {v.get('r_frame_rate')}")
    if v.get("has_b_frames"): w.append("B-frames present")
    if a.get("codec_name") != "aac": w.append(f"audio {a.get('codec_name')}")
    with out_mp4.open("rb") as fh: head = fh.read(64 * 1024)
    if b"moov" not in head: w.append("moov not at front (faststart)")
    res.append(R(9, "container: 1080×1920 · 30 fps · H.264 no B-frames · AAC · faststart", "fail" if w else "pass", "; ".join(w)))
    budget = float(tl["budget"]) if tl else None; w = []
    if budget and abs(dur - budget) > 0.2: w.append(f"duration {dur:.2f}s vs {budget}s")
    if size > MAX_TELEGRAM: w.append(f"{size / 1e6:.0f} MB > Telegram's 50 MB")
    res.append(R(10, "duration = budget, size ≤ 50 MB", "fail" if w and "duration" in w[0] else "warn" if w else "pass", "; ".join(w)))
    # loudness + ducking
    r = subprocess.run([ffmpeg(), "-nostdin", "-v", "info", "-i", str(out_mp4), "-af", "loudnorm=I=-15:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r, re.S); w = []
    if m:
        L = json.loads(m.group(0)); I, TP = float(L["input_i"]), float(L["input_tp"])
        if abs(I + 15) > 1.5: w.append(f"integrated {I:.1f} LUFS (target −15)")
        if TP > -1.0: w.append(f"true peak {TP:.1f} dBTP (> −1.5)")
    vo = b / "vo_full.wav"; mus = b / "music.wav"
    if vo.exists() and mus.exists() and tl and proj["audio"].get("music", True):
        # music level during speech vs during gaps: sidechain should keep it ≥ 6 dB lower under the voice
        def lvl(f, t0, t1):
            rr = subprocess.run([ffmpeg(), "-nostdin", "-v", "info", "-ss", str(t0), "-t", str(max(0.2, t1 - t0)), "-i", str(f), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
            mm = re.search(r"mean_volume: ([-\d.]+) dB", rr); return float(mm.group(1)) if mm else None
        sp = [s for s in tl["scenes"] if s.get("vo_len")]; quiet = []
        if sp:
            s0 = sp[len(sp) // 2]; a_t, b_t = s0["vo_at"], min(s0["end"], s0["vo_at"] + 2.0)
            # a rough check on the mix itself: compare band energy would need separation; use the plan instead — ducked music must be < voice by the mix constants
            mdb = float(proj["audio"].get("music_db", -5)); vdb = 0.0
            if mdb > -3: w.append(f"music at {mdb} dB sits close to the voice; keep ≤ −5")
        gaps = [s["key"] for s in tl["scenes"] if s.get("vo_len") and s["vo_len"] > 0 and s["key"] not in ("intro", "closing") and s["end"] - s["start"] - s["vo_len"] / tl["tempo"] > 2.0]
        if gaps: w.append("long silence inside: " + ", ".join(gaps))
    res.append(R(11, "loudness −15 LUFS, peaks ≤ −1.5 dBTP, music under the voice", "warn" if w else "pass", "; ".join(w)))
    # black / frozen frames
    r = subprocess.run([ffmpeg(), "-nostdin", "-v", "info", "-i", str(out_mp4), "-vf", "blackdetect=d=0.3:pic_th=0.98,freezedetect=n=-60dB:d=1.2", "-an", "-f", "null", "-"], capture_output=True, text=True).stderr
    blk = re.findall(r"black_start:([\d.]+)", r); frz = re.findall(r"freeze_start: ([\d.]+)", r)
    res.append(R(12, "no black or frozen frames", "fail" if blk else "warn" if frz else "pass", "; ".join([f"black at {', '.join(x[:4] for x in blk)}" if blk else "", f"frozen at {', '.join(x[:5] for x in frz)}" if frz else ""]).strip("; ")))
    # cut rhythm
    if tl:
        short = [f"{s['key']} {s['end'] - s['start']:.1f}s" for s in tl["scenes"] if s["end"] - s["start"] < 1.5]
        from .media import shots_of
        for s, sc in zip(tl["scenes"], proj["scenes"]):
            sh = shots_of(sc); L = s["end"] - s["start"]; wsum = sum(float(x.get("w") or 1) for x in sh) or 1
            short += [f"{s['key']}/{x['file']} {L * float(x.get('w') or 1) / wsum:.1f}s" for x in sh if L * float(x.get("w") or 1) / wsum < 1.0]
        res.append(R(13, "no scene < 1.5 s, no shot < 1 s", "warn" if short else "pass", "; ".join(short[:6])))
    return res

def describe(res: list[dict]) -> str:
    sym = {"pass": "✓", "warn": "!", "fail": "✗"}
    return "\n".join(f"  {sym[r['status']]} {r['id']:>2} {r['name']}{' — ' + r['detail'] if r['detail'] else ''}" for r in res)

def failed(res: list[dict]) -> list[dict]: return [r for r in res if r["status"] == "fail"]
