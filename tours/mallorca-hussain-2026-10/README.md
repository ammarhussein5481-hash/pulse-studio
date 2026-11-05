# Mallorca reel — Hussain, Oct 20–25 2026 (pipeline v3)

Same pipeline that built the drafts in chat; runs locally in Pulse Studio or any Linux box.

## Requirements
ffmpeg ≥ 6, node ≥ 18, python3 ≥ 3.10. Internet on first run only (npm fonts + playwright chromium + u2net model, 176 MB, from GitHub).

## Run
1. Unzip `HUSSAIN.zip` → put all 16 files in `./media/`
2. `./run.sh` (uses the Pulse Studio venv at ~/.pulse-studio/venv, or creates ./.venv)  → `hussain_mallorca_draft_v3.mp4` (60 s, 1080×1920, 30 fps, no music — add in Instagram)

Steps can be re-run individually (see run.sh). After editing text/layout in `ov3.html`, only `node frames3.mjs all && bash comp3.sh` is needed (masks and base are reused).
QA a single moment without rendering everything: `node frames3.mjs stills 12,30,57` → `stills3/`.

## What each file does
- `base2.py` — scene list (clip, in-point, duration, speed/Ken-Burns) → `base2.mp4`, `timeline2.json`. Edit SCENES to re-cut.
- `masks.py` — u2net person segmentation per frame → `masks/`, `person_boxes.json` (used to keep maps off the rider).
- `ov3.html` — the overlay. `render(t, "back"|"front")`: back = hook slams, MALLORCA, day titles, closing totals (behind the rider); front = labels, stats, climb cards, elevation profiles, island map, Arabic captions, CTA. Day text/captions are in the `days` array at the top.
- `frames3.mjs` — Playwright renderer → `frames3/b_*.png` (back) and `f_*.png` (front).
- `sfx2.py` — numpy sound design (whoosh on cuts, hits on slams, ticks on count-ups) → `sfx2.wav`.
- `comp3.sh` — ffmpeg: base → grain+vignette → back layer → rider cut-out (mask) → front layer; ambience −3 dB + SFX −6 dB, loudnorm −15 LUFS; H.264 8 Mbps.
- `rides.json` — Hussain's 7 Strava rides (daily totals + simplified route). `streams.json` — altitude/HR streams for Oct 21/23/24. `island.json` — Mallorca coastline (OSM).

## Identity
climbday rules: transparent overlays, Anton + Archivo (+ Noto Kufi Arabic), bone #F4EFE6 / orange #FF5A1E, grain + vignette, IG safe zones (top 250 px, bottom 340 px).
