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
    return f"{k:.1f} كيلو"

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

def generate(proj: dict, data: dict) -> list[dict]:
    """[{key, text}] in scene order. Uses the scenes that exist; if there are none yet, intro + stations + closing."""
    import datetime
    s = data.get("_session", {}); kind = proj["session"].get("type", "hyrox"); order = s.get("order") or [k for k in data if not k.startswith("_")]
    try: day = DAYS[datetime.date.fromisoformat(proj["session"]["date"]).weekday()]
    except Exception: day = ""
    keys = [sc["key"] for sc in proj["scenes"]] or (["intro"] + order + ["closing"])
    lines = []; first = True; peak_done = False
    try: day_en = DAYS_EN[datetime.date.fromisoformat(proj["session"]["date"]).weekday()]
    except Exception: day_en = ""
    for k in keys:
        d = data.get(k) or {}
        en = ""
        if k == "intro":
            t = f"السلام عليكم. اليوم {day}، يوم {TYPE_AR.get(kind, kind)}. بسم الله نبدأ." if day else f"السلام عليكم. يوم {TYPE_AR.get(kind, kind)}. بسم الله نبدأ."
            en = f"{day_en + ' — ' if day_en else ''}{kind.upper()} day. Let's go."
        elif k == "warmup":
            t = "قبل أي حاجة، تسخين خفيف خمس دقايق، وبعدين نبدأ."; en = "First, a light 5-minute warm-up."
        elif k == "closing":
            tot = s.get("total_s"); n = len(order)
            if kind == "hyrox" or not s.get("distance_m"):
                t = (f"{mins(round(tot / 60))}، {count(n, 'محطة', 'محطتين', 'محطات', 'محطة')}. " if tot else "") + "الأرقام كلها من ساعة قارمن ومن تطبيق نبض."
                en = (f"{round(tot / 60)} minutes, {n} stations. " if tot else "") + "All numbers from the Garmin watch and the Pulse app."
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

def write(dir: Path, proj: dict, data: dict, force: bool = False) -> list[dict]:
    """Fills scene.script (and caption + dialect hint when empty), writes build/script.md for recording."""
    dir = Path(dir); lines = generate(proj, data)
    if not proj["scenes"]:
        from .project import SCENE_TEMPLATE
        for l in lines:
            sc = json.loads(json.dumps(SCENE_TEMPLATE)); sc.update(key=l["key"], clip="", caption="", title=None); proj["scenes"].append(sc)
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
