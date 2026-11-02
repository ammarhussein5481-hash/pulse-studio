"""Original 60 s track (120 BPM, D minor -> D major at the verdict/closing). Code-generated, no rights issues.
Usage as module: music.generate(verdict_s, out_path). From the pulse repo demo/story/music.py."""
import numpy as np, wave, sys
sr = 48000; T = 60.0; n = int(sr * T); L = np.zeros(n); R = np.zeros(n)
BEAT = 0.5

def generate(VER, OUT):
    _generate(float(VER), str(OUT))

def library_dir():
    from .config import HOME
    d = HOME / "music"; d.mkdir(parents=True, exist_ok=True); return d

def prepare(proj: dict, tl: dict, out):
    """build/music.wav for the mix: a file from the library (audio.music_file, trimmed from audio.music_in, faded at the end)
    or the generated track when music_file is empty/"generated"."""
    import subprocess
    from pathlib import Path
    from .config import ffmpeg
    a = proj.get("audio", {}); f = a.get("music_file")
    if not f or f == "generated":
        return generate(tl["scenes"][-1]["start"], out)
    src = library_dir() / Path(f).name
    if not src.exists():
        raise SystemExit(f"music file {f} not in the library ({library_dir()}) — upload it in the web app or copy it there")
    T = float(tl["budget"]); st = float(a.get("music_in", 0) or 0)
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-ss", str(st), "-i", str(src), "-t", str(T), "-ac", "2", "-ar", "48000",
                    "-af", f"apad=whole_dur={T},afade=t=in:d=0.5,afade=t=out:st={T - 2.5:.2f}:d=2.5", str(out)], check=True)
    return out

def _generate(VER, OUT):
    global L, R
    L = np.zeros(n); R = np.zeros(n)
    _body(VER, OUT)

def _body(VER, OUT):
    rng = np.random.default_rng(19)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    def put(sig, t0, gl=1.0, gr=1.0):
        i = int(t0 * sr); j = min(n, i + len(sig))
        if i >= n or j <= i: return
        L[i:j] += sig[: j - i] * gl; R[i:j] += sig[: j - i] * gr
    def tone(f, dur, bright, amp, att=0.004, dec=6.0, sus=0.0):
        t = np.arange(int(dur * sr)) / sr; s = np.zeros_like(t)
        for k in range(1, 16):
            a = np.exp(-k * f / bright) / k
            if a < 1e-3 or k * f > 16000: break
            s += a * np.sin(2 * np.pi * k * f * t)
        env = np.minimum(1, t / att) * (sus + (1 - sus) * np.exp(-t * dec))
        return s * env * amp
    def kick(amp=0.55):
        t = np.arange(int(0.35 * sr)) / sr; f = 45 + 110 * np.exp(-t * 28)
        return np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t * 9) * amp
    def hat(amp=0.05, dec=60):
        x = rng.standard_normal(int(0.06 * sr)); x = np.diff(x, prepend=0); return x * np.exp(-np.arange(len(x)) / sr * dec) * amp
    def rim(amp=0.12):
        t = np.arange(int(0.05 * sr)) / sr; return (np.sin(2 * np.pi * 1700 * t) + 0.5 * rng.standard_normal(len(t))) * np.exp(-t * 90) * amp
    def tick(amp=0.10):
        t = np.arange(int(0.03 * sr)) / sr; return np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 200) * amp
    MIN = [62, 65, 69, 74]; MAJ_PENT = [62, 64, 66, 69, 71, 74]
    # ---- pad: sustained chord, swells; up a fifth at 27; heartbeat side-chain 30-35; D major after verdict
    def pad_seg(t0, t1, notes, amp, bright=900):
        d = t1 - t0; t = np.arange(int(d * sr)) / sr; s = np.zeros_like(t)
        for m in notes:
            f = hz(m); s += tone(f, d, bright, 1, att=0.6, dec=0, sus=1)[: len(t)] * 0.5 + tone(f * 1.004, d, bright, 1, att=0.6, dec=0, sus=1)[: len(t)] * 0.5
        fade = np.minimum(1, np.minimum(t / 0.8, (d - t) / 0.8)); return s * fade * amp
    put(pad_seg(0, 4.6, [50, 57, 62, 65], 0.05), 0)
    put(pad_seg(4.0, 27.6, [50, 57, 62, 65], 0.035), 4.0)
    put(pad_seg(27.0, 30.4, [57, 64, 69, 72], 0.045), 27.0)
    hb = pad_seg(30.0, 35.4, [50, 57, 62, 65], 0.06); th = np.arange(len(hb)) / sr; rate = 1.4 + (2.85 - 1.4) * np.clip(th / 4.0, 0, 1)
    ph = np.cumsum(rate) / sr; hb *= 0.35 + 0.65 * (0.5 + 0.5 * np.cos(2 * np.pi * ph)) ** 3; put(hb, 30.0)
    for k in range(len(th)):  # heartbeat thumps at the same rate
        pass
    p0 = 0.0; tt = 30.0
    while tt < 35.0:
        r = 1.4 + (2.85 - 1.4) * min(1, (tt - 30) / 4.0); put(tone(55, 0.18, 120, 0.35, dec=22), tt); put(tone(55, 0.15, 120, 0.22, dec=25), tt + 0.16); tt += 1 / r
    put(pad_seg(35.0, VER + 0.3, [50, 57, 62, 65], 0.035), 35.0)
    put(pad_seg(VER, 60.0, [50, 57, 62, 66], 0.045), VER)          # D major from the verdict
    # ---- ticks (clock) 0-4 and slow at the end
    for b in np.arange(0, 4.0, BEAT): put(tick(), b)
    for b in np.arange(54.5, 59.0, 1.0): put(tick(0.07), b)
    # ---- hats (cadence 8ths) from 4.0; quarters at the end; pause one beat at verdict
    for b in np.arange(4.0, 54.5, BEAT / 2):
        if VER <= b < VER + BEAT: continue
        put(hat(0.045 if (b * 4) % 2 else 0.06), b, 0.8, 1.0)
    for b in np.arange(54.5, 59.0, BEAT): put(hat(0.04), b, 0.8, 1.0)
    # ---- pluck arpeggio 16ths, brightness opening up; D major pentatonic after the verdict
    for b in np.arange(4.0, 54.5, BEAT / 4):
        if 30.0 <= b < 35.0 or VER <= b < VER + 0.5: continue
        br = 400 if b < 9.5 else 800 if b < 13.5 else 1200 if b < 18 else 3000
        k = int(round((b - 4.0) * 8)); seq = MAJ_PENT if b >= VER else MIN; m = seq[k % len(seq)] + (12 if (k // len(seq)) % 2 else 0)
        amp = (0.05 if b < 18 else 0.06) * (0.8 if b >= VER + 0.5 else 1.0) * (0.6 if 50 <= b else 1.0)
        pan = 0.3 + 0.4 * ((k % 4) / 3); put(tone(hz(m), 0.22, br, amp, dec=14), b, 1.2 - pan, 0.4 + pan)
    # ---- rim on 2 and 4 from 9.5
    for b in np.arange(9.5, 54.5, 1.0):
        if 30.0 <= b < 35.0 or VER <= b < VER + 0.5: continue
        put(rim(0.08), b + 0.5)
    # ---- riser 13.5-18
    d = 4.5; t = np.arange(int(d * sr)) / sr; x = rng.standard_normal(len(t)); x = np.diff(x, prepend=0) * (t / d) ** 2 * 0.10; put(x, 13.5)
    # ---- kicks
    def kicks(a, b, step, amp=0.55):
        for k in np.arange(a, b, step): put(kick(amp), k)
    kicks(13.5, 18.0, 1.0, 0.45); kicks(18.0, 30.0, BEAT); kicks(35.0, VER, 1.0, 0.5); kicks(VER + 0.5, 50.0, BEAT, 0.45); kicks(50.0, 54.5, 2.0, 0.4)
    # ---- sub bass on the off-beats during the drop and after
    for b in np.arange(18.0, 30.0, BEAT): put(tone(hz(38), 0.4, 200, 0.22, dec=5), b + 0.25)
    for b in np.arange(VER + 0.5, 50.0, BEAT): put(tone(hz(38), 0.4, 200, 0.16, dec=5), b + 0.25)
    # ---- rep stabs (Dm, 2 octaves) on each bar of scene 5
    for b in (18.0, 19.5, 21.0, 22.5, 24.0, 25.5):
        for m in (50, 62, 65, 69, 74): put(tone(hz(m), 0.6, 2500, 0.05, dec=7), b)
    # ---- verdict: D major stab + impact
    for m in (38, 50, 62, 66, 69, 74): put(tone(hz(m), 2.2, 2000, 0.07, dec=1.6), VER)
    t = np.arange(int(1.2 * sr)) / sr; put(np.sin(2 * np.pi * (40 + 60 * np.exp(-t * 10)) * t) * np.exp(-t * 3) * 0.6 + rng.standard_normal(len(t)) * np.exp(-t * 18) * 0.12, VER)
    # ---- final low D and hard cut
    put(tone(hz(38), 1.0, 300, 0.4, att=0.01, dec=2.5), 59.0)
    # master: gentle fade-in, hard cut with a 20 ms ramp, normalise
    L[: int(0.3 * sr)] *= np.linspace(0, 1, int(0.3 * sr)); R[: int(0.3 * sr)] *= np.linspace(0, 1, int(0.3 * sr))
    L[-960:] *= np.linspace(1, 0, 960); R[-960:] *= np.linspace(1, 0, 960)
    st = np.stack([L, R], 1); st = np.tanh(st / np.abs(st).max() * 1.4) ; st /= np.abs(st).max() * 1.12
    w = wave.open(OUT, "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes((st * 32767).astype("<i2").tobytes()); w.close(); print("wrote", OUT)


if __name__ == "__main__":
    generate(sys.argv[1], sys.argv[2])
