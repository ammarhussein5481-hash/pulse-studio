#!/bin/bash
# One-shot build of Hussain's Mallorca reel (v3: text behind the rider). Needs: ffmpeg, node 18+, python3.
# Put the 16 files from HUSSAIN.zip in ./media first.
set -e; cd "$(dirname "$0")"
[ -d node_modules/@fontsource ] || npm install --silent
npx playwright install chromium >/dev/null 2>&1 || true
pip install -q numpy opencv-python-headless onnxruntime pillow pillow-heif 2>/dev/null || pip install --break-system-packages -q numpy opencv-python-headless onnxruntime pillow pillow-heif
[ -f ~/.u2net/u2net.onnx ] || { mkdir -p ~/.u2net; curl -L -o ~/.u2net/u2net.onnx https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx; }
python3 prep_media.py
python3 base2.py            # base cut → base2.mp4 + timeline2.json
python3 masks.py            # rider masks → masks/ + person_boxes.json  (slowest step; scales with cores)
python3 sfx2.py             # whoosh / hits / ticks → sfx2.wav
node frames3.mjs all        # overlay frames, back + front layers → frames3/
bash comp3.sh               # composite → hussain_mallorca_draft_v3.mp4
