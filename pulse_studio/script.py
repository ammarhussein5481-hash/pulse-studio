"""Voice-over script: the Arabic (Sudanese) lines Ammar records, one per scene, with the session's real numbers.

Runs after ingest + data (the clips and the workout type are known). Template-based — instant, offline, the numbers are
right — and he rewrites any line in the web app or asks the Assistant to reword. The lines become the captions and the
transcription hint, so what he says, what Whisper hears and what the screen shows all come from the same text.
"""
from __future__ import annotations
import json
from pathlib import Path

ONES = ["", "واحد", "اتنين", "تلاتة", "أربعة", "خمسة", "ستة", "سبعة", "تمانية", "تسعة", "عشرة",
        "حداشر", "اتناشر", "تلتاشر", "أربعتاشر", "خمستاشر", "ستاشر", "سبعتاشر", "تمنتاشر", "تسعتاشر"]
TENS = {20: "عشرين", 30: "تلاتين", 40: "أربعين", 50: "خمسين", 60: "ستين", 70: "سبعين", 80: "تمانين", 90: "تسعين"}
# the "counting" form used right before a noun for 3–10 (تلات دقايق, not تلاتة دقايق)
COUNT = {3: "تلات", 4: "أربع", 5: "خمس", 6: "ست", 7: "سبع", 8: "تمن", 9: "تسع", 10: "عشر"}

def num(n: int) -> str:
    n = int(n)
    if n < 20: return ONES[n] if n else "صفر"
    if n < 100: t, o = (n // 10) * 10, n % 10; return (ONES[o] + " و" if o else "") + TENS[t]
    if n < 1000:
        h = n // 100; r = n % 100; hs = {1: "مية", 2: "ميتين", 3: "تلتمية", 4: "أربعمية", 5: "خمسمية", 6: "ستمية", 7: "سبعمية", 8: "تمنمية", 9: "تسعمية"}[h]
        return hs + (" و" + num(r) if r else "")
    k = n // 1000; r = n % 1000; ks = {1: "ألف", 2: "ألفين"}.get(k, COUNT.get(k, ONES[k]) + " آلاف")
    return ks + (" و" + num(r) if r else "")

def count(n: int, one: str, two: str, few: str, many: str) -> str:
    """n + noun in colloquial Arabic: 1 دقيقة, 2 دقيقتين, 3–10 تلات دقايق, 11+ حداشر دقيقة."""
    n = int(n)
    if n == 1: return one
    if n == 2: return two
    if 3 <= n <= 10: return f"{COUNT[n]} {few}"
    return f"{num(n)} {many}"

def mins(n): return count(n, "دقيقة", "دقيقتين", "دقايق", "دقيقة")
def secs(n): return count(n, "ثانية", "ثانيتين", "ثواني", "ثانية")

def duration(s: float) -> str:
    m, sec = int(s // 60), int(round(s % 60))
    if sec == 60: m, sec = m + 1, 0
    if not m: return secs(sec)
    if sec < 3: return mins(m)
    return f"{mins(m)} و{secs(sec)}"

def metres(m: float) -> str:
    m = int(round(m / 10.0) * 10)
    if m >= 1000 and m % 500 == 0: return {1000: "كيلو", 1500: "كيلو ونص", 2000: "كيلوين"}.get(m, f"{num(m // 1000)} كيلو")
    if m == 1000: return "ألف متر"
    return f"{num(m)} متر"

def km(m: float) -> str:
    k = m / 1000
    if abs(k - round(k)) < 0.05: return {1: "كيلو", 2: "كيلوين"}.get(round(k), f"{num(round(k))} كيلو")
    if abs(k - int(k) - 0.5) < 0.05: return {0: "نص كيلو", 1: "كيلو ونص"}.get(int(k), f"{num(int(k))} كيلو ونص")
    whole = int(k); rest = int(round((k - whole) * 10)) * 100
    if not whole: return f"{num(rest)} متر"
    base = {1: "كيلو", 2: "كيلوين"}.get(whole, f"{num(whole)} كيلو")
    return f"{base} و{num(rest)} متر" if rest else base

AR = {"skierg": "سكي إيرق", "row": "التجديف", "farmers": "الفارمرز كاري", "lunges": "اللانجز بالساندباق", "wall_balls": "الوول بولز",
      "burpee_bj": "البيربيز", "sled_push": "السلد بوش", "sled_pull": "السلد بول", "run": "الجري", "rowing": "التجديف"}
DIST = {"skierg": "ألف متر", "row": "ألف متر", "wall_balls": "مية كورة", "sled_push": None}
DAYS = {0: "الاتنين", 1: "التلاتاء", 2: "الأربعاء", 3: "الخميس", 4: "الجمعة", 5: "السبت", 6: "الأحد"}
TYPE_AR = {"hyrox": "الهايروكس", "run": "الجري", "ride": "السيكل", "strength": "تمرين الحديد", "swim": "السباحة"}

EN = {"skierg": "SkiErg", "row": "Row", "farmers": "Farmers Carry", "lunges": "Sandbag Lunges", "wall_balls": "Wall Balls", "burpee_bj": "Burpee Broad Jumps",
      "sled_push": "Sled Push", "sled_pull": "Sled Pull", "run": "Run"}
DAYS_EN = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"}
def mmss(x): x = int(round(x)); return f"{x // 60}:{x % 60:02d}"
def dist_en(k, d):
    if k in ("skierg", "row"): return "1000 m"
    if k == "wall_balls": return "100 reps"
    if d.get("m"): return f"{d['m'] / 1000:.1f} km" if d["m"] >= 1000 else f"{int(round(d['m'] / 10) * 10)} m"
    return ""

ORD = ["", "الأول", "التاني", "التالت", "الرابع", "الخامس", "السادس", "السابع", "التامن", "التاسع", "العاشر", "الحداشر", "الاتناشر"]
ORD_EN = ["", "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th", "11th", "12th"]

def pace_ar(sec_per_km: float) -> str:
    m, sec = int(sec_per_km // 60), int(round(sec_per_km % 60))
    return f"{mins(m)}" if sec < 3 else f"{mins(m)} و{secs(sec)}"

def phases(data: dict) -> list[tuple[str, list[str]]]:
    """Scenes as PHASES: [(scene key, data parts it summarises)]. Runs/rides: warmup → workout (all reps / the tempo block / all
    distance parts) → cooldown. HYROX / strength: one scene per station (the station is the phase)."""
    s = data.get("_session", {}); order = [k for k in s.get("order", []) if isinstance(data.get(k), dict)]
    if s.get("type") in ("run", "ride") or any(k.startswith(("rep", "part")) for k in order):
        out = []
        if "warmup" in order: out.append(("warmup", ["warmup"]))
        work = [k for k in order if k.startswith(("rep", "part"))]
        if work: out.append(("workout", work))
        if "cooldown" in order: out.append(("cooldown", ["cooldown"]))
        return out or [(k, [k]) for k in order]
    return [(k, [k]) for k in order]

def pick_parts(data: dict, clips: list[dict] | None, proj: dict, max_parts: int = 8) -> list[str]:
    """Which parts become scenes. With clips: the parts that were filmed (shoot time on the session clock), in order.
    Without: for intervals warm-up + first / middle / last rep + cool-down; otherwise every part up to max_parts."""
    s = data.get("_session", {}); order = [k for k in s.get("order", []) if isinstance(data.get(k), dict)]
    if clips:
        from . import clipmap, label as labelmod
        m = clipmap.map_clips(data, clips, proj["session"].get("clip_offset_s"))
        byname = {c["file"]: c for c in clips}
        # a clip whose picture contradicts its clock position (recovery walk during a rep, warm-up drills on the cool-down) does not make a scene for that part
        filmed = [k for k in order if any(v["part"] == k and labelmod.consistent(byname[f].get("label"), k) is not False for f, v in m.items())]
        if filmed: return filmed
        # no clock (no shoot times): the labels alone — warm-up clips → warmup, fast → reps, easy/stretch → cooldown
        labs = {c.get("label") for c in clips}
        if labs & {"warmup", "easy_run", "fast_run", "recovery_walk", "stretch"}:
            reps_ = [k for k in order if k.startswith("rep")]; out = []
            if "warmup" in labs and "warmup" in order: out.append("warmup")
            nfast = sum(1 for c in clips if c.get("label") == "fast_run")
            for k in reps_[:nfast] if nfast else reps_[:1]: out.append(k)
            if labs & {"easy_run", "stretch"} and "cooldown" in order: out.append("cooldown")
            if out: return [k for k in order if k in out]
    reps_ = [k for k in order if k.startswith("rep")]
    if len(reps_) > 4:
        keep = {reps_[0], reps_[len(reps_) // 2], reps_[-1]}
        best = min(reps_, key=lambda k: data[k]["s"] / max(1, data[k]["m"]))
        keep.add(best); return [k for k in order if not k.startswith("rep") or k in keep]
    return order[:max_parts]

def generate(proj: dict, data: dict, keys: list[str] | None = None) -> list[dict]:
    """[{key, text, en}] in scene order. Uses the scenes that exist (or `keys`); if none, intro + parts + closing."""
    import datetime
    s = data.get("_session", {}); kind = proj["session"].get("type", "hyrox"); order = s.get("order") or [k for k in data if not k.startswith("_")]
    try: day = DAYS[datetime.date.fromisoformat(proj["session"]["date"]).weekday()]
    except Exception: day = ""
    keys = keys or [sc["key"] for sc in proj["scenes"]] or (["intro"] + order + ["closing"])
    sc_parts = {sc["key"]: sc.get("parts") or [] for sc in proj["scenes"]}
    if "workout" in keys and not sc_parts.get("workout"): sc_parts["workout"] = [k for k in order if k.startswith(("rep", "part"))]
    lines = []; first = True; peak_done = False; rec_said = False
    reps_total = s.get("reps") or sum(1 for k in order if k.startswith("rep")); target = s.get("target")
    try: day_en = DAYS_EN[datetime.date.fromisoformat(proj["session"]["date"]).weekday()]
    except Exception: day_en = ""
    for k in keys:
        d = data.get(k) or {}
        en = ""
        if k == "intro":
            if kind == "run" and s.get("structure") == "intervals" and reps_total:
                rep_m = data[next(x for x in order if x.startswith("rep"))]["m"]
                t = f"السلام عليكم. اليوم {day}، جري إنترفال: {num(reps_total)} في {km(rep_m) if rep_m >= 1000 else metres(rep_m)}{'، على ' + pace_ar(_tosec(target)) + ' للكيلو' if target else ''}. بسم الله."
                en = f"{day_en + ' — ' if day_en else ''}Interval run: {reps_total} × {rep_m / 1000:.0f} km{' @ ' + target + ' /km' if target else ''}."
            elif kind == "run" and s.get("structure") == "tempo":
                t = f"السلام عليكم. اليوم {day}، جري تيمبو. بسم الله."; en = f"{day_en + ' — ' if day_en else ''}Tempo run."
            else:
                t = f"السلام عليكم. اليوم {day}، يوم {TYPE_AR.get(kind, kind)}. بسم الله نبدأ." if day else f"السلام عليكم. يوم {TYPE_AR.get(kind, kind)}. بسم الله نبدأ."
                en = f"{day_en + ' — ' if day_en else ''}{kind.upper()} day. Let's go."
        elif k in ("warmup", "cooldown") and d.get("m"):
            what = "تسخين" if k == "warmup" else "تهدئة"; what_en = "Warm-up" if k == "warmup" else "Cool-down"
            t = f"{'أول حاجة' if k == 'warmup' else 'وفي الآخر'}، {what} {km(d['m'])}، {pace_ar(d['s'] / (d['m'] / 1000))} للكيلو."
            en = f"{what_en}: {d['m'] / 1000:.1f} km at {mmss(d['s'] / (d['m'] / 1000))} /km."; first = False
        elif k == "workout" or (not d and sc_parts.get(k)):
            P = [data[x] for x in sc_parts.get(k, []) if isinstance(data.get(x), dict)]; R = [x for x in P if x.get("rep")]
            if R:
                paces = [x["s"] / (x["m"] / 1000) for x in R]; avg = sum(paces) / len(paces); best = min(paces); hr = round(sum(x["hr"] * x["s"] for x in R if x.get("hr")) / sum(x["s"] for x in R if x.get("hr"))) if any(x.get("hr") for x in R) else None
                rep_m = R[0]["m"]
                t = f"الشغل: {num(len(R))} في {km(rep_m) if rep_m >= 1000 else metres(rep_m)}، المتوسط {pace_ar(avg)}{'، وأسرع واحد ' + pace_ar(best) if best < avg - 2 else ''}." + (f" النبض {num(hr)}." if hr else "") + (f" وبين كل كيلو {secs(round(R[0]['rec_s']))} راحة." if R[0].get("rec_s") else "")
                en = f"The work: {len(R)} × {rep_m / 1000:.0f} km, avg {mmss(avg)} /km{', best ' + mmss(best) if best < avg - 2 else ''}{', HR ' + str(hr) if hr else ''}." + (f" {int(round(R[0]['rec_s']))} s recovery between." if R[0].get("rec_s") else "")
            elif P:
                m_ = sum(x.get("m") or 0 for x in P); s_ = sum(x.get("s") or 0 for x in P)
                t = f"الشغل: {km(m_)} في {duration(s_)}{'، ' + pace_ar(s_ / (m_ / 1000)) + ' للكيلو' if m_ else ''}."; en = f"The work: {m_ / 1000:.1f} km in {mmss(s_)}{' at ' + mmss(s_ / (m_ / 1000)) + ' /km' if m_ else ''}."
            else: t = "الشغل."; en = "The work."
            first = False
        elif k.startswith("rep") and d.get("m"):
            n = d.get("rep", 1); pace = d["s"] / (d["m"] / 1000)
            t = f"الكيلو {ORD[n] if n < len(ORD) else num(n)}: {pace_ar(pace)}. النبض {num(d['hr'])}." if d.get("hr") else f"الكيلو {ORD[n]}: {pace_ar(pace)}."
            if d.get("rec_s") and not rec_said: t += f" وبعد كل كيلو {secs(round(d['rec_s']))} راحة."; rec_said = True
            if n == reps_total and reps_total > 1: t = t.replace("الكيلو", "الكيلو الأخير،", 1).replace(f"الأخير، {ORD[n]}", "الأخير")
            en = f"{ORD_EN[n] if n < len(ORD_EN) else n} km: {mmss(pace)} /km, HR {d.get('hr', '')}." + (f" {int(round(d['rec_s']))} s recovery after each." if "راحة" in t else "")
            first = False
        elif k == "warmup":
            t = "قبل أي حاجة، تسخين خفيف خمس دقايق، وبعدين نبدأ."; en = "First, a light 5-minute warm-up."
        elif k == "closing":
            tot = s.get("total_s"); n = len(order)
            if kind == "hyrox" or not s.get("distance_m"):
                t = (f"{mins(round(tot / 60))}، {count(n, 'محطة', 'محطتين', 'محطات', 'محطة')}. " if tot else "") + "الأرقام كلها من ساعة قارمن ومن تطبيق نبض."
                en = (f"{round(tot / 60)} minutes, {n} stations. " if tot else "") + "All numbers from the Garmin watch and the Pulse app."
            elif s.get("structure") == "intervals" and reps_total:
                fast_m = sum(data[x]["m"] for x in order if x.startswith("rep"))
                t = f"{km(s['distance_m'])} كلها، {km(fast_m)} منها سريعة. الأرقام كلها من ساعة قارمن ومن تطبيق نبض."
                en = f"{s['distance_m'] / 1000:.1f} km total, {fast_m / 1000:.0f} km of it fast. All numbers from the Garmin watch and the Pulse app."
            else:
                t = f"{km(s['distance_m'])} في {duration(tot)}. الأرقام كلها من ساعة قارمن ومن تطبيق نبض."
                en = f"{s['distance_m'] / 1000:.1f} km in {mmss(tot)}. All numbers from the Garmin watch and the Pulse app."
        else:
            name = AR.get(k, d.get("station") or k.replace("_", " ")); lead = "أول حاجة" if first else "بعده"; first = False
            dist = DIST.get(k, (km(d["m"]) if d["m"] >= 1000 else metres(d["m"])) if d.get("m") else None)
            if kind == "hyrox":
                tm = d["erg"][0] if d.get("erg") else d.get("s")
                t = f"{lead} {name}{'، ' + dist if dist else ''}. {duration(tm) + '.' if tm else ''}"
                if d.get("max") and d["max"] == s.get("max_hr") and not peak_done: t += f" النبض طلع {num(d['max'])}."; peak_done = True
            elif kind in ("run", "ride"):
                t = f"{lead} {name}، {km(d['m']) if d.get('m') else ''} في {duration(d['s'])}." if d.get("s") else f"{lead} {name}."
            else:
                t = f"{lead} {name}. {duration(d['s']) + '.' if d.get('s') else ''}"
            t = t.replace("..", ".").strip()
            nm = EN.get(k, d.get("station") or k.replace("_", " ").title()); de = dist_en(k, d)
            tm = d["erg"][0] if d.get("erg") else d.get("s")
            en = f"{'First up' if lead == 'أول حاجة' else 'Then'}: {nm}{', ' + de if de else ''}{' — ' + mmss(tm) if tm else ''}." + (f" HR peaked at {d['max']}." if "النبض طلع" in t else "")
        lines.append({"key": k, "text": t, "en": en})
    return lines

def _tosec(t):
    try: a, b = str(t).split(":"); return int(a) * 60 + int(b)
    except Exception: return 0

def write(dir: Path, proj: dict, data: dict, force: bool = False) -> list[dict]:
    """Fills scene.script (and caption + dialect hint when empty), writes build/script.md for recording.
    Scenes are created from the parts that were FILMED when clips.json exists (shoot time vs session clock)."""
    dir = Path(dir); clips = None
    cj = dir / "build" / "clips.json"
    if cj.exists():
        try: clips = json.loads(cj.read_text(encoding="utf-8"))
        except Exception: clips = None
    keys = None; ph = None
    if not proj["scenes"]:
        ph = phases(data); keys = ["intro"] + [k for k, _ in ph] + ["closing"]
        from .project import SCENE_TEMPLATE
        for k in keys:
            sc = json.loads(json.dumps(SCENE_TEMPLATE)); sc.update(key=k, clip="", caption="", title=None, parts=dict(ph).get(k)); proj["scenes"].append(sc)
    lines = generate(proj, data, keys)
    if ph is not None and clips:   # shots: every clip filmed during a phase (clock) that does not contradict it (label), up to 4 per scene
        from . import clipmap, suggest as sugg, label as labelmod
        m = clipmap.map_clips(data, clips, proj["session"].get("clip_offset_s")); byname = {c["file"]: c for c in clips}; used = set()
        def shot(c, key):
            sh = {"file": c["file"], "in": 0.5 if key == "intro" else (0 if c.get("photo") else sugg.in_point(c)), "crop": "full" if c.get("vertical") else "auto", "w": 1}
            if c.get("label"): sh["label"] = c["label"]
            return sh
        for sc in proj["scenes"]:
            parts_ = sc.get("parts") or [sc["key"]]
            if sc["key"] in ("intro", "closing"):
                talk = [byname[f] for f in sorted(m, key=lambda f: m[f]["t"]) if byname[f].get("label") == "talking"]
                pick = (talk[:1] if sc["key"] == "intro" else talk[-1:]) if talk else ([min(byname.values(), key=lambda c: c.get("created") or "")] if sc["key"] == "intro" else [max(byname.values(), key=lambda c: c.get("created") or "")])
                sc["shots"] = [shot(c, sc["key"]) for c in pick]
                if sc["key"] == "closing" and sc["shots"]: sc["shots"][0]["in"] = max(0.0, (pick[0].get("duration") or 8) - 8)
                continue
            cands = [f for f, v in sorted(m.items(), key=lambda x: x[1]["t"]) if v["part"] in parts_ and f not in used and labelmod.consistent(byname[f].get("label"), v["part"]) is not False]
            cands = cands[:4]; used.update(cands)
            sc["shots"] = [shot(byname[f], sc["key"]) for f in cands]
        if not any(sc.get("shots") for sc in proj["scenes"] if sc["key"] not in ("intro", "closing")):   # no clock match at all: labels, then shoot order
            pool = [c for c in sorted(clips, key=lambda c: c.get("created") or "")]
            for sc in proj["scenes"]:
                if sc["key"] in ("intro", "closing"): continue
                want = {"warmup": {"warmup", "stretch", "easy_run"}, "workout": {"fast_run", "easy_run", "ride", "strength"}, "cooldown": {"easy_run", "stretch", "recovery_walk"}}.get(sc["key"], set())
                pick = [c for c in pool if c.get("label") in want][:4] or pool[:2]
                sc["shots"] = [shot(c, sc["key"]) for c in pick]; pool = [c for c in pool if c not in pick]
    for sc in proj["scenes"]:
        if sc.get("shots") == []: sc["shots"] = None
    by = {sc["key"]: sc for sc in proj["scenes"]}
    for l in lines:
        sc = by.get(l["key"])
        if not sc: continue
        if force or not sc.get("script"): sc["script"] = l["text"]
        if force or not sc.get("caption_en"): sc["caption_en"] = l.get("en", "")
        if force or not sc.get("caption"): sc["caption"] = sc["script"]
        if sc.get("key") != "closing" and "windows" not in sc.get("vo", {}): sc.setdefault("vo", {"file": "main"})
    hint = " ".join(sc.get("script", "") for sc in proj["scenes"] if sc["key"] != "warmup")
    if force or not proj["vo"].get("dialect_hint"): proj["vo"]["dialect_hint"] = hint[:600]
    md = ["# Voice-over script — " + proj["name"], "",
          "Record ONE file for everything (main), pause ~1 s between lines; the warm-up line can be its own file. Say the numbers as written. Mistakes are fine — just repeat the line.", ""]
    for i, sc in enumerate(proj["scenes"], 1):
        md.append(f"{i}. **{sc['key']}** — {sc.get('script', '')}" + (f"  \n   _{sc['caption_en']}_" if sc.get("caption_en") else ""))
    (dir / "build").mkdir(exist_ok=True); (dir / "build" / "script.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return [{"key": sc["key"], "text": sc.get("script", "")} for sc in proj["scenes"]]
