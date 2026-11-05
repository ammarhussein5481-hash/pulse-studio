#!/bin/bash
# One-shot build of Hussain's Mallorca reel (v3: text behind the rider). Needs: ffmpeg, node 18+, python3 (+ python3-venv).
# Put the 16 files from HUSSAIN.zip in ./media first.
set -e; cd "$(dirname "$0")"
# python: Pulse Studio's venv if present, else a local one
H="${PULSE_STUDIO_HOME:-$HOME/.pulse-studio}"
if [ -x "$H/venv/bin/python" ]; then PY="$H/venv/bin/python"; else [ -d .venv ] || python3 -m venv .venv; PY=".venv/bin/python"; fi
"$PY" -m pip install -q numpy opencv-python-headless onnxruntime pillow pillow-heif
[ -d node_modules/@fontsource ] || npm install --silent
npx playwright install chromium >/dev/null 2>&1 || true
[ -f ~/.u2net/u2net.onnx ] || { mkdir -p ~/.u2net; curl -L -o ~/.u2net/u2net.onnx https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx; }
# media may have been unzipped into media/HUSSAIN/
[ -d media/HUSSAIN ] && mv -n media/HUSSAIN/* media/ && rmdir media/HUSSAIN || true
"$PY" prep_media.py
"$PY" base2.py            # base cut → base2.mp4 + timeline2.json
"$PY" masks.py            # rider masks → masks/ + person_boxes.json  (slowest step; scales with cores)
"$PY" sfx2.py             # whoosh / hits / ticks → sfx2.wav
node frames3.mjs all      # overlay frames, back + front layers → frames3/
bash comp3.sh             # composite → hussain_mallorca_draft_v3.mp4
echo "done → $(pwd)/hussain_mallorca_draft_v3.mp4"
