#!/usr/bin/env python3
"""Sound design for v2: whoosh on every cut, impact hits on hook slams + closing totals, ticks under count-ups. Writes sfx2.wav"""
import json, numpy as np, os, wave
D = os.path.dirname(os.path.abspath(__file__))
tl = json.load(open(os.path.join(D, "timeline2.json")))
SR = 48000; T = tl["total"] + 0.5; buf = np.zeros(int(SR * T))
rng = np.random.default_rng(7)
def put(x, at, gain=1.0):
    i = int(at * SR); j = min(len(buf), i + len(x));
    if i < len(buf): buf[i:j] += x[:j - i] * gain
def env(n, a, d): e = np.ones(n); A = int(a * SR); Dd = int(d * SR); e[:A] = np.linspace(0, 1, A); e[-Dd:] *= np.linspace(1, 0, Dd); return e
def whoosh(dur=0.28):
    n = int(dur * SR); x = rng.standard_normal(n)
    # sweep a band-pass by mixing a rising-pitch resonant filter approximation: simple one-pole LP with time-varying cutoff
    y = np.zeros(n); z = 0.0; cut = np.linspace(400, 5000, n) / SR
    for i in range(n): z += (x[i] - z) * cut[i] * 6.28; y[i] = z
    y /= np.max(np.abs(y)) + 1e-9; return y * env(n, 0.05, 0.15) * 0.9
def hit(dur=0.5, f=60):
    n = int(dur * SR); t = np.arange(n) / SR
    body = np.sin(2 * np.pi * (f * np.exp(-t * 6) + 35) * t) * np.exp(-t * 7)
    click = rng.standard_normal(int(0.012 * SR)) * np.linspace(1, 0, int(0.012 * SR)); body[:len(click)] += click * 0.6
    return body * 0.95
def tick():
    n = int(0.018 * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * 2400 * t) * np.exp(-t * 400) * 0.35
sc = {s["id"]: s for s in tl["scenes"]}
# cuts
for s in tl["scenes"]:
    if s["start"] > 0: put(whoosh(), s["start"] - 0.08, 0.55)
# hook slams
for k in ("hookA", "hookB", "hookC"): put(hit(), sc[k]["start"] + 0.05, 1.0)
put(hit(0.7, 50), sc["hookD"]["start"] + 0.05, 0.9)
# day stat count-ups: ticks 0.3..1.5 s after each day start (first scene of each day), then a soft hit
for k in ("d1a", "d2a", "d3a", "d4a", "d5a", "d6"):
    t0 = sc[k]["start"]
    for i in range(16): put(tick(), t0 + 0.3 + i * 0.075, 0.6 + 0.3 * i / 16)
    put(hit(0.35, 70), t0 + 1.5, 0.45)
# closing totals
c = sc["close"]["start"]
for i in range(26): put(tick(), c + 0.4 + i * 0.077, 0.6)
for i in range(4): put(hit(0.45, 55), c + 0.45 + i * 0.22, 0.7)
put(hit(0.8, 45), c + 2.4, 0.9)
buf = np.clip(buf, -1, 1)
with wave.open(os.path.join(D, "sfx2.wav"), "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((buf * 32767).astype(np.int16).tobytes())
print("sfx2.wav", T)
