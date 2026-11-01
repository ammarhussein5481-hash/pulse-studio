# Pulse Studio

Turns a training session into a 9:16 reel (60 s by default; `vo.budget_s` in project.json or `pulse-reel new --budget 90` for longer): your clips + your voice-over + the session's real numbers (Garmin HR second by second, ErgData splits, steps) rendered as transparent overlays in the climbday identity. Runs entirely on an Ubuntu laptop; no GPU needed.

## Install (Ubuntu 22.04 / 24.04)

```bash
git clone https://github.com/ammarhussein5481-hash/pulse-studio.git
cd pulse-studio
./setup.sh                      # ffmpeg + VAAPI driver, python venv, fonts, chrome-headless-shell (~400 MB total)
echo 'export PULSE_URL=https://<your pulse dashboard> PULSE_TOKEN=<its link token>' >> ~/.bashrc
```

## Two ways to use it

**Web app** — `pulse-reel ui` opens http://127.0.0.1:8787 : create a session, drop the camera files and voice recording (or record the voice-over in the browser), fetch the session data, transcribe, pick a clip and the transcript words for each scene, fix captions, run stills/build with a live log, play the result and publish. Everything it does is the same CLI steps underneath, so you can mix both.

**Claude Code** — open `claude` in this folder and type `/reel`; it drives the same project.json and commands conversationally ("the sled shot starts from here", "raise the music").

`pulse-reel --help` lists the commands.

## A session, end to end

```bash
pulse-reel new sessions/2026-11-08-hyrox --date 2026-11-08 --type hyrox   # add --budget 90 for a longer reel
#  → put the camera files in sessions/2026-11-08-hyrox/raw/, the voice recording in vo/
pulse-reel ingest sessions/2026-11-08-hyrox     # clips by shoot time + contact sheets
pulse-reel data   sessions/2026-11-08-hyrox     # pulls sessions/2026-11-08-hyrox.json from Pulse
pulse-reel stt    sessions/2026-11-08-hyrox     # word-timed transcript of the voice-over
#  → edit project.json: one scene per station (clip, in-point, VO word window, corrected caption)
pulse-reel timeline sessions/2026-11-08-hyrox   # timing + tempo check
pulse-reel stills   sessions/2026-11-08-hyrox   # overlay QA stills
pulse-reel build    sessions/2026-11-08-hyrox   # ~12 min → out/<name>-v1.mp4 + contact sheet
pulse-reel audio    sessions/2026-11-08-hyrox   # remix only (after changing music/sfx levels)
pulse-reel publish  sessions/2026-11-08-hyrox --to user@host:/var/www/share/   # or set PULSE_SHARE
```

On the VPS, export a session's data once per date (inside the Garmin container):

```bash
docker exec whoopdash-garmin python /work/pulse-studio-server/export_session.py 2026-11-08
```

## What a scene looks like (project.json)

```json
{"key": "skierg", "clip": "PC000383.mov", "in": 2.0, "crop": "auto", "amb_db": -9,
 "vo": {"file": "main", "from": 5.44, "to": 10.26},
 "caption": "أول حاجة سكي إيرق، ألف متر. أربع دقايق وست ثواني."}
```

`crop`: `auto` (centre 9:16 from a landscape source), `full` (vertical source as is), or `w:h:x:y` for a punch-in. `vo.windows: [[a,b],[c,d]]` skips filler words. `title` overrides the on-screen kicker/name/number/sub-line. `audio.music_db`, `sfx_db`, `amb_db` set the mix.

## Speed on an i5-7300U (4 threads, no GPU)
Whisper large-v3-turbo on a 90 s voice-over (first run downloads the 1.6 GB model) ≈ 3 min · base cut (4K, VAAPI) ≈ 2 min · 1800 overlay frames ≈ 5 min · final encode ≈ 3 min.

## Who this is for
It is built around one person's setup (a self-hosted "Pulse" dashboard for Garmin/WHOOP data, a HYROX watch app, Sudanese-Arabic voice-overs, the *climbday* visual identity). The engine is generic — any session with clips + a voice-over + a `data.json` in the shape of `examples/hyrox-2026-11-01/data.json` renders — but expect to change `IDENTITY` in `config.py` (fonts, colours, watermark) and the station titles in `overlay/overlay.html` for your own use.

## Credits
Music and SFX are code-generated (numpy), no licensing. Fonts via @fontsource (OFL). Built with Claude Code on 2026-11-01.

## License
Code: MIT (see `LICENSE`). The climbday identity (name, colours/typography combination, the `@AMMARHUSSEIN` watermark) and the example session footage/data are Ammar Hussein's and are not covered by the MIT grant — replace them in your own builds.
