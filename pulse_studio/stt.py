"""Voice-over transcription with word timestamps (faster-whisper, CPU int8 by default)."""
from __future__ import annotations
import json, subprocess
from pathlib import Path
from .config import ffmpeg

MODEL = "large-v3-turbo"

def to_wav(src: Path, dst: Path, rate: int = 16000) -> Path:
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(rate), str(dst)], check=True)
    return dst

def transcribe(wav: Path, language: str = "ar", hint: str = "", model: str = MODEL) -> list[dict]:
    from faster_whisper import WhisperModel  # heavy import, keep it lazy
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(wav), language=language, vad_filter=True, vad_parameters=dict(min_silence_duration_ms=400),
                           word_timestamps=True, beam_size=5, condition_on_previous_text=False, initial_prompt=hint or None)
    out = []
    for s in segs:
        out.append({"s": round(s.start, 2), "e": round(s.end, 2), "text": s.text.strip(),
                    "words": [[w.word.strip(), round(w.start, 2), round(w.end, 2), round(w.probability, 2)] for w in s.words]})
    return out

def transcribe_project(dir: Path, proj: dict, force: bool = False) -> dict[str, list]:
    """Transcribes vo.main and every vo.extra file → build/stt_<name>.json. Returns {name: segments}."""
    dir = Path(dir); build = dir / "build"; build.mkdir(exist_ok=True)
    files = {"main": proj["vo"]["main"], **proj["vo"].get("extra", {})}
    res = {}
    for name, rel in files.items():
        src = dir / rel
        if not src.exists():
            print(f"  [stt] missing {rel} — skipped"); continue
        out = build / f"stt_{name}.json"
        if out.exists() and not force:
            res[name] = json.loads(out.read_text(encoding="utf-8")); continue
        wav = to_wav(src, build / f"vo_{name}.wav")
        print(f"  [stt] {rel} …", flush=True)
        segs = transcribe(wav, proj["vo"].get("language", "ar"), proj["vo"].get("dialect_hint", ""))
        out.write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf-8"); res[name] = segs
    return res

def print_words(segs: list[dict]) -> str:
    return " ".join(f"{w[0]}@{w[1]}" for s in segs for w in s["words"])
