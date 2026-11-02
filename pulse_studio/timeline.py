"""Turns project.json scenes + transcripts into timeline.json: scene times derived from speech, pauses compressed,
uniform tempo if over budget, word times for karaoke captions, VO segment wavs."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
from .config import ffmpeg, ffprobe

GAP, PAD = 0.26, 0.2
WPS = 2.1   # Ammar's pace in Sudanese Arabic (first reel: ~2.3 words/s after pause compression; 2.1 leaves room for the real take)

def estimate_speech(lines: list[str]) -> float:
    """Seconds of speech a script will take, before any recording exists."""
    words = sum(len(l.split()) for l in lines if l)
    return round(words / WPS + 0.3 * len([l for l in lines if l]), 1)   # + a breath per line

def suggest_budget(speech_s: float, n_scenes: int, tmax: float = 1.12) -> dict:
    """Recommended reel length from the speech. Story = 60 s max per segment; a Reel can run longer, but 30–60 s holds
    attention best and the voice should never be sped up past ~×1.12 (it stops sounding like him)."""
    natural = speech_s + 2 * PAD * n_scenes          # no tempo at all
    tight = natural / tmax                            # fastest that still sounds natural
    opts = []
    for L in (30, 45, 60, 75, 90):
        if L >= tight - 0.5:
            tempo = max(1.0, round(natural / L, 2))
            opts.append({"len": L, "tempo": tempo, "fits_story": L <= 60, "note": "" if tempo < 1.08 else "slightly faster speech"})
    if not opts: opts.append({"len": int(round(tight / 5 + 0.5) * 5), "tempo": tmax, "fits_story": False, "note": "needs trimming for a Story"})
    best = (next((o for o in opts if o["fits_story"] and o["tempo"] <= 1.10), None)       # a Story at natural-ish pace
            or next((o for o in opts if not o["fits_story"] and o["tempo"] <= 1.05), None) # else a relaxed Reel
            or opts[0])
    cut = max(0.0, round(natural - 60 * tmax, 1))     # seconds of speech to drop to make a 60 s Story
    return {"speech": round(speech_s, 1), "natural": round(natural, 1), "best": best["len"], "options": opts, "cut_for_story": cut}

def describe_budget(sg: dict) -> str:
    o = ", ".join(f"{x['len']}s (×{x['tempo']}{', Story' if x['fits_story'] else ', Reel only'})" for x in sg["options"])
    s = f"speech ≈ {sg['speech']}s → natural length {sg['natural']}s. Recommended: {sg['best']}s. Options: {o}."
    if sg["cut_for_story"] > 0: s += f" For a 60 s Story drop ~{sg['cut_for_story']}s of speech (one or two phrases)."
    return s

def _words(segs): return [dict(w=x[0], s=x[1], e=x[2]) for s in segs for x in s["words"]]

def build(dir: Path, proj: dict, stt: dict[str, list]) -> dict:
    dir = Path(dir); vd = dir / "build" / "voseg"; vd.mkdir(parents=True, exist_ok=True)
    budget = float(proj["vo"].get("budget_s", 60)); tmax = float(proj["vo"].get("tempo_max", 1.15))
    scenes = []
    for sc in proj["scenes"]:
        vo = sc.get("vo") or {}
        name = vo.get("file", "main"); segs = stt.get(name)
        if not segs:
            scenes.append(dict(key=sc["key"], cap=sc.get("caption", ""), vo=None, vo_len=0.0, words=[], fixed=float(sc.get("duration", 4.0)))); continue
        ws = _words(segs)
        wins = vo.get("windows") or [[vo.get("from", 0.0), vo.get("to", 1e9)]]
        words = [w for a, b in wins for w in ws if a - 0.01 <= w["s"] <= b + 0.01]
        if not words:
            raise SystemExit(f"scene {sc['key']}: no words in {name} within {wins}")
        pieces, cur = [], [words[0]]
        for w in words[1:]:
            if w["s"] - cur[-1]["e"] > GAP + 0.15: pieces.append(cur); cur = [w]
            else: cur.append(w)
        pieces.append(cur)
        parts, t, cap_words = [], 0.0, []
        src = dir / "build" / f"vo_{name}.wav"
        for i, p in enumerate(pieces):
            pa, pb = max(0, p[0]["s"] - 0.06), p[-1]["e"] + 0.08
            f = vd / f"{sc['key']}_{i}.wav"
            subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-ss", str(pa), "-t", str(pb - pa), "-i", str(src), "-af",
                            f"afade=t=in:d=0.02,afade=t=out:st={pb - pa - 0.03:.3f}:d=0.03", str(f)], check=True); parts.append(f)
            for w in p: cap_words.append([w["w"], round(t + (w["s"] - pa), 2), round(t + (w["e"] - pa), 2)])
            t += pb - pa
            if i < len(pieces) - 1:
                g = vd / f"{sc['key']}_g{i}.wav"
                subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", str(GAP), str(g)], check=True)
                parts.append(g); t += GAP
        lst = vd / f"{sc['key']}.txt"; lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
        out = vd / f"{sc['key']}.wav"
        subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)], check=True)
        d = float(subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout.strip() or t)
        scenes.append(dict(key=sc["key"], cap=sc.get("caption", "") or " ".join(w["w"] for w in words), vo=str(out.relative_to(dir)), vo_len=round(d, 2), words=cap_words, fixed=None))
    speech = sum(s["vo_len"] for s in scenes); fixed = sum(s["fixed"] or 0 for s in scenes)
    tot = speech + fixed + 2 * PAD * len(scenes)
    tempo = min(tmax, max(1.0, round(tot / budget, 3)))
    t = 0.0
    for s in scenes:
        L = (s["fixed"] if s["fixed"] else s["vo_len"] / tempo)
        s["start"] = round(t, 2); s["vo_at"] = round(t + PAD, 2); s["end"] = round(t + L + 2 * PAD, 2); t = s["end"]
        s["words"] = [[w, round(a / tempo + s["vo_at"], 2), round(b / tempo + s["vo_at"], 2)] for w, a, b in s["words"]]
    k = budget / t
    for s in scenes:
        for f in ("start", "end", "vo_at"): s[f] = round(s[f] * k, 2)
        s["words"] = [[w, round(a * k, 2), round(b * k, 2)] for w, a, b in s["words"]]
    tl = dict(tempo=tempo, k=round(k, 4), budget=budget, speech=round(speech, 1), scenes=scenes, suggest=suggest_budget(speech, len(scenes), tmax), order=[s["key"] for s in scenes if s["key"] not in ("intro", "warmup", "closing")])
    (dir / "build" / "timeline.json").write_text(json.dumps(tl, ensure_ascii=False, indent=1), encoding="utf-8")
    return tl

def describe(tl: dict) -> str:
    lines = [f"speech {tl['speech']}s → tempo ×{tl['tempo']} (stretch k={tl['k']}) budget {tl['budget']}s"]
    for s in tl["scenes"]:
        lines.append(f"  {s['key']:12s} {s['start']:5.1f}-{s['end']:5.1f}  vo {s['vo_len']:4.1f}s  {s['cap'][:50]}")
    if tl["tempo"] >= 1.12: lines.append("  ! tempo above 1.12 — consider dropping a phrase or raising budget_s")
    if tl.get("suggest"): lines.append("  " + describe_budget(tl["suggest"]))
    return "\n".join(lines)
