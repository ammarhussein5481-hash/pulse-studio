#!/usr/bin/env python3
"""Trial: clone Ammar's voice with SILMA TTS v1 (150M, Arabic+English, Apache-2.0 weights) from one recorded take
and speak another line — to hear whether a synthetic Sudanese line is usable at all. NOT part of the pipeline.

  python3 -m venv ~/.pulse-studio/silma && ~/.pulse-studio/silma/bin/pip install silma-tts
  ~/.pulse-studio/silma/bin/python tools/voice_try.py sessions/2026-11-02-run intro warmup
      → build/voice_try_warmup.wav  (reference = vo/lines/intro.m4a + its script line; text = the warm-up script line)

Compare it with vo/lines/warmup.m4a (your real take). Judge: accent, the numbers, naturalness. First run downloads the model (~600 MB).
"""
import json, subprocess, sys, time
from pathlib import Path

def main():
    if len(sys.argv) < 4: raise SystemExit(__doc__)
    d = Path(sys.argv[1]); ref_key, gen_key = sys.argv[2], sys.argv[3]
    proj = json.loads((d / "project.json").read_text(encoding="utf-8")); by = {s["key"]: s for s in proj["scenes"]}
    ref = d / "vo" / "lines" / f"{ref_key}.m4a"
    if not ref.exists(): raise SystemExit(f"no take for {ref_key} ({ref})")
    wav = d / "build" / f"voice_ref_{ref_key}.wav"; wav.parent.mkdir(exist_ok=True)
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(ref), "-ac", "1", "-ar", "24000", str(wav)], check=True)
    ref_text = by[ref_key].get("script") or by[ref_key].get("caption") or None
    gen_text = by[gen_key].get("script") or by[gen_key].get("caption")
    if not gen_text: raise SystemExit(f"no script line for {gen_key}")
    from silma_tts.api import SilmaTTS
    print("loading model …", flush=True); t0 = time.time(); tts = SilmaTTS(); print(f"  {time.time() - t0:.0f} s")
    out = d / "build" / f"voice_try_{gen_key}.wav"
    print("generating:", gen_text, flush=True); t0 = time.time()
    tts.infer(ref_file=str(wav), ref_text=ref_text, gen_text=gen_text, file_wave=str(out), seed=1, speed=1)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout or 0)
    print(f"  {time.time() - t0:.0f} s for {dur:.1f} s of speech → {out}\ncompare with: {d / 'vo' / 'lines' / (gen_key + '.m4a')}")

if __name__ == "__main__":
    main()
