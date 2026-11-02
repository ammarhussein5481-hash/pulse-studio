"""Code-generated sound effects timed to the timeline: whoosh on every cut, ticks while the big number counts up,
a hit when it lands, pops as the sub-line words appear, and the closing grid's ticks/pops."""
from __future__ import annotations
import wave
import numpy as np
from pathlib import Path

SR = 48000

def _env(n, a, d):
    e = np.ones(n); A = int(a * SR); D = int(d * SR)
    e[:A] = np.linspace(0, 1, A); e[-D:] = np.linspace(1, 0, D); return e

def whoosh(d=0.38):
    n = int(d * SR); x = np.random.randn(n); y = np.zeros(n); seg = 8
    for k in range(seg):
        a, b = int(k * n / seg), int((k + 1) * n / seg); c = 400 * (2 ** (k * 0.45))
        xs = x[a:b]; Xs = np.fft.rfft(xs); fs = np.fft.rfftfreq(len(xs), 1 / SR)
        y[a:b] = np.fft.irfft(Xs * np.exp(-((fs - c) / (c * 0.6)) ** 2), len(xs))
    y /= np.max(np.abs(y)) + 1e-9; return y * _env(n, 0.12, 0.2)

def hit(d=0.35):
    n = int(d * SR); t = np.arange(n) / SR
    y = np.sin(2 * np.pi * (90 * np.exp(-t * 6) + 45) * t) * np.exp(-t * 9) + 0.25 * np.random.randn(n) * np.exp(-t * 60)
    return y / np.max(np.abs(y))

def tick():
    n = int(0.018 * SR); t = np.arange(n) / SR; return np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 300)

def pop():
    n = int(0.07 * SR); t = np.arange(n) / SR; return np.sin(2 * np.pi * (380 + 600 * t / 0.07) * t) * np.exp(-t * 45)

def generate(tl: dict, out: Path, total_s: float = 60.0, proj: dict | None = None) -> Path:
    buf = np.zeros(int(SR * total_s)); events = []
    def put(sig, t, g=1.0, kind="hit"):
        i = int(t * SR); n = min(len(sig), len(buf) - i)
        if n > 0: buf[i:i + n] += sig[:n] * g; events.append([round(t, 3), kind, round(g, 2)])
    scenes = tl["scenes"]
    for s in scenes[1:]: put(whoosh(), s["start"] - 0.12, 0.55)
    for s in scenes:
        if s["key"] in ("intro", "closing"): continue
        c = s["start"]
        for k in range(12): put(tick(), c + 0.15 + k * 0.05, 0.22, "tick")
        put(hit(), c + 0.72, 0.7)
        for i in range(5): put(pop(), c + 0.8 + i * 0.07, 0.18, "pop")
    fin = scenes[-1]["start"]
    for i in range(4):
        for k in range(10): put(tick(), fin + 0.5 + i * 0.2 + k * 0.06, 0.2, "tick")
        put(pop(), fin + 0.5 + i * 0.2 + 0.7, 0.3, "pop")
    put(hit(), fin + 0.3, 0.6)
    if proj:
        opts = {s["key"]: s for s in proj["scenes"]}
        if (opts.get("closing") or {}).get("style") == "checklist":   # one pop per station ticking off
            n = len((tl.get("order") or [])) or 8
            for i in range(n): put(pop(), fin + 0.6 + i * 0.35, 0.4, "pop")
        for s in scenes:
            if "storm" in (opts.get(s["key"], {}).get("fx") or []):     # headline storm: a tick per flashed word
                for k in range(5): put(tick(), s["start"] + 0.1 + k * 0.16, 0.35, "tick")
    import json
    Path(out).with_name("sfx_events.json").write_text(json.dumps(events), encoding="utf-8")
    buf = np.clip(buf / (np.max(np.abs(buf)) + 1e-9) * 0.7, -1, 1)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((buf * 32767).astype(np.int16).tobytes())
    return out
