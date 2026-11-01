#!/usr/bin/env bash
# One-time setup on Ubuntu 22.04/24.04 (also fine on Debian). Re-run safely.
set -euo pipefail
cd "$(dirname "$0")"
H="${PULSE_STUDIO_HOME:-$HOME/.pulse-studio}"; mkdir -p "$H"
echo "== system packages (ffmpeg + Intel VAAPI driver for hardware 4K decode)"
if ! command -v ffmpeg >/dev/null; then sudo apt-get update && sudo apt-get install -y ffmpeg intel-media-va-driver-non-free vainfo python3-venv; fi
command -v node >/dev/null || { echo "Node 20+ is required: https://nodejs.org (or: sudo apt install nodejs npm)"; exit 1; }
echo "== python venv + package"
[ -d "$H/venv" ] || python3 -m venv "$H/venv"
"$H/venv/bin/pip" install -q --upgrade pip
"$H/venv/bin/pip" install -q -e .
echo "== fonts (@fontsource) + chrome-headless-shell"
( cd "$H" && [ -f package.json ] || echo '{"name":"pulse-studio-home","private":true}' > package.json; npm install --silent @fontsource/anton @fontsource/archivo @fontsource/noto-kufi-arabic >/dev/null )
( cd "$H" && npx --yes @puppeteer/browsers install chrome-headless-shell@stable --path "$H/browsers" | tail -1 )
echo "== whisper model (large-v3-turbo, ~1.6 GB, cached in ~/.cache/huggingface) — downloaded on first transcription"
mkdir -p "$HOME/.local/bin"; ln -sf "$H/venv/bin/pulse-reel" "$HOME/.local/bin/pulse-reel"
echo
echo "ready. make sure ~/.local/bin is on your PATH, then:  pulse-reel --help"
echo "set once in ~/.bashrc:  export PULSE_URL=https://<your pulse dashboard>  PULSE_TOKEN=<its link token>   # to pull session data"
