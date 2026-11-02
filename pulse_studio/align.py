"""Match the script to the recording: which transcript words belong to which scene, and did he say what the script says.

After `stt`, each scene's script line is aligned (in order) against the transcribed words; the best-matching window becomes the
scene's vo window (from/to), so nobody has to click words by hand. The report shows, per line, what was heard, a match
percentage, and words that differ — numbers above all, because a wrong number on screen is the one mistake that matters.
"""
from __future__ import annotations
import re, difflib

DIAC = re.compile(r"[ً-ْٰـ]")
def norm(w: str) -> str:
    w = DIAC.sub("", w).strip(".,،؟!:;\"'()[]")
    w = re.sub("[إأآا]", "ا", w).replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي").replace("ث", "ت").replace("ذ", "ز")   # Sudanese: ث→ت, ذ→ز
    return w.lower()

ARNUM = ("واحد", "اتنين", "تلات", "ثلاث", "اربع", "خمس", "ست", "سبع", "تمان", "ثمان", "تسع", "عشر", "حداشر", "اتناشر", "عشرين", "تلاتين", "ثلاثين", "اربعين", "خمسين", "ستين", "سبعين", "تمانين", "ثمانين", "تسعين", "ميه", "مية", "ميتين", "الف", "كيلو", "نص")
def is_num(w: str) -> bool:
    n = norm(w); return n.isdigit() or any(n.startswith(a) or n.startswith("و" + a) for a in ARNUM)
def fold(w: str) -> str:
    """Matching form: خمس ≈ خمسة ≈ وخمسة (counting form, ة/ه ending, leading و are the same word)."""
    return norm(w).lstrip("و").rstrip("ه")
def same_num(a: str, b: str) -> bool: return fold(a) == fold(b)

def words_of(segs: list[dict]) -> list[dict]:
    return [dict(w=x[0], s=x[1], e=x[2], p=x[3] if len(x) > 3 else 1.0) for sg in segs for x in sg["words"]]

def best_window(script: list[str], tw: list[dict], start: int, slack: int = 8) -> tuple[int, int, float]:
    """Best contiguous window of transcript words (from index `start` on) for this line: max SequenceMatcher ratio."""
    n = len(script); best = (start, start, 0.0)
    if not n or start >= len(tw): return best
    lo = start; hi = min(len(tw), start + 3 * n + 40)
    for i in range(lo, hi):
        for L in range(max(1, n - slack), n + slack + 1):
            j = i + L
            if j > len(tw): break
            sm = difflib.SequenceMatcher(None, script, [fold(x["w"]) for x in tw[i:j]])
            M = sum(b.size for b in sm.get_matching_blocks())
            r = M / n - 0.15 * (L - M) / n          # coverage of the script, minus a small penalty for extra words
            if r > best[2]: best = (i, j, r)
    return best

def align(proj: dict, stt: dict[str, list], lines: dict | None = None) -> list[dict]:
    """Sets scene.vo = {file, from, to} for every scene with a script line; returns the per-scene report.
    `lines` = take boundaries {key: [start, end]} in main.m4a when the lines were recorded one by one — then the window is
    KNOWN and the words are only compared; otherwise the window is found by aligning the text."""
    cursors = {name: 0 for name in stt}; report = []; lines = lines or {}
    for sc in proj["scenes"]:
        line = sc.get("script") or sc.get("caption") or ""
        name = (sc.get("vo") or {}).get("file", "main")
        if sc["key"] in lines: name = "main"
        if not line.strip() or name not in stt:
            report.append({"key": sc["key"], "ok": None, "note": "no script line" if not line.strip() else f"no transcript '{name}'"}); continue
        tw = words_of(stt[name]); sw = [fold(w) for w in line.split()]
        if sc["key"] in lines:
            a, b = lines[sc["key"]]; idx = [k for k, x in enumerate(tw) if x["s"] >= a - 0.15 and x["e"] <= b + 0.15]
            if not idx:
                sc["vo"] = {"file": "main", "from": round(a, 2), "to": round(b, 2)}
                report.append({"key": sc["key"], "ok": False, "ratio": 0, "from": a, "to": b, "heard": "", "diffs": [], "unsure": [], "note": "take recorded but nothing transcribed — re-record louder/closer"}); continue
            i, j = idx[0], idx[-1] + 1; r = difflib.SequenceMatcher(None, sw, [fold(x["w"]) for x in tw[i:j]]).ratio()
            heard = tw[i:j]; sc["vo"] = {"file": "main", "from": round(a, 2), "to": round(b, 2)}
        else:
            i, j, r = best_window(sw, tw, cursors[name])
            if j <= i:
                report.append({"key": sc["key"], "ok": False, "ratio": 0, "note": "not found in the recording"}); continue
            heard = tw[i:j]; cursors[name] = j
            sc["vo"] = {"file": name, "from": round(heard[0]["s"], 2), "to": round(heard[-1]["e"], 2)}
        # word-level differences, numbers flagged
        sm = difflib.SequenceMatcher(None, sw, [fold(x["w"]) for x in heard]); diffs = []
        for tag, a0, a1, b0, b1 in sm.get_opcodes():
            if tag == "equal": continue
            exp = " ".join(line.split()[a0:a1]); got = " ".join(x["w"] for x in heard[b0:b1])
            ew, gw = exp.split(), got.split()
            if len(ew) == len(gw) and all(same_num(x, y) or norm(x) == norm(y) for x, y in zip(ew, gw)): continue   # spelling only
            diffs.append({"expected": exp, "heard": got, "number": any(is_num(w) for w in ew + gw)})
        low = [x["w"] for x in heard if x["p"] < 0.5]
        report.append({"key": sc["key"], "ok": (r >= 0.75 or sc["key"] in lines and r >= 0.5) and not any(d["number"] for d in diffs), "ratio": round(max(0, min(1, r)), 2), "fixed": sc["key"] in lines,
                       "from": sc["vo"]["from"], "to": sc["vo"]["to"], "heard": " ".join(x["w"] for x in heard), "diffs": diffs, "unsure": low})
    return report

def describe(rep: list[dict]) -> str:
    out = []
    for r in rep:
        if r.get("ok") is None: out.append(f"  {r['key']:11s} — {r['note']}"); continue
        flag = "✓" if r["ok"] else "!"
        out.append(f"  {flag} {r['key']:11s} {int(r.get('ratio', 0) * 100):3d}%  {r.get('from', '')}-{r.get('to', '')}  {r.get('heard', r.get('note', ''))[:70]}")
        for d in r.get("diffs", []):
            if d["number"]: out.append(f"      NUMBER differs: script «{d['expected']}» · heard «{d['heard']}»")
    return "\n".join(out)
