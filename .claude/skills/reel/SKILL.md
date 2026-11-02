---
name: reel
description: Build or revise a 9:16 training-session reel (60 s by default, longer when Ammar asks) (HYROX, run, ride) from Ammar's clips, voice-over and Pulse data with the pulse-reel CLI. Use when Ammar says "new session", "make the reel", "the sled shot starts from here", "raise the music", "use this clip for burpees", "show me v2", or sends clips/voice notes for a session.
---

# /reel — Pulse Studio reel builder

You drive `pulse-reel` (installed by `./setup.sh`, env `PULSE_TOKEN` for Pulse data). One project = one folder under `sessions/<date>-<type>/` with `project.json`, `raw/` (clips), `vo/` (voice files), `build/` (derived), `out/` (versions).

## Flow for a new session
1. `pulse-reel sessions` (Pulse index: today / yesterday / earlier with ids) → `pulse-reel new sessions/<date>-<type> --from-pulse <id>` (no Pulse session: `--date <date> --type <type> --no-data` → titles + captions, no numbers) → ask Ammar to drop clips in `raw/` and the voice-over in `vo/` (one file with all phrases + optional extra files like `warmup.m4a`). In the web app the New-session picker does this. Google Drive link-shared files: `curl -L "https://drive.usercontent.google.com/download?id=<ID>&export=download&confirm=t" -o raw/<name>`.
2. `pulse-reel ingest <dir>` — clips sorted by **shoot time** (creation_time), motion profile per second and contact sheets `build/sheet_*.jpg`. **Look at the sheets** (Read the jpg). Rule learned: on static tripod shots the exercise is the *low-motion middle*; the handheld start/end (placing / picking up the camera) is what to cut. Selfie/handheld clips are high motion throughout.
3. `pulse-reel data <dir>` — stations with time/HR/steps/splits from the session file the VPS exporter wrote (`server/export_session.py --sync`, cron every 10 min). "not on Pulse yet" → the session hasn't been exported: wait for the cron or run it there by hand (`export_session.py <date|id>`). `session.source: "none"` → no data, skip.
4. `pulse-reel stt <dir>` — prints every word with its start time. Build `project.json → scenes` by session type (`session.type`, see *Session types* below): one per station / part / exercise in order, plus `intro`, optional `warmup`, `closing`. For each scene set `clip`, `in` (seconds), `crop` (`auto` | `full` for vertical sources | `w:h:x:y` punch-in), `amb_db`, `vo` window (`from`/`to` word times, or `windows: [[a,b],...]` to skip filler, or `{"file":"warmup"}` for a whole extra file) and the **corrected `caption`** (Whisper gets ~7 % of Sudanese words wrong — fix spelling, keep his words; station names in captions stay Arabic, on-screen titles are English).
5. `pulse-reel timeline <dir>` — check tempo. Above ×1.12: propose dropping a filler phrase (use `windows`) or raising `vo.budget_s` (e.g. 90 s for a Reel rather than a Story); Ammar decides the length.
6. `pulse-reel stills <dir>` — Read 3–4 stills before a full build; check captions don't collide with the diagram, numbers are right.
7. `pulse-reel build <dir>` (~12 min on the laptop) → `out/<name>-vN.mp4` + contact sheet jpg. Read the sheet, then tell Ammar the path and what changed.

## Session types (one workout = one reel)
- **hyrox** — scene keys = the station keys in `data._session.order` (skierg, row, farmers …); HYROX diagrams (erg splits, reps ring, distance track).
- **run / ride** — the exporter groups Garmin laps into ≤ 8 parts `part1…part8` ("KM 0–3"). Scene keys = those part keys (drop or merge parts to fit the voice-over; each needs a clip shot during that stretch). On screen: time, km, pace /km (run) or km/h + climb (ride), lap bars.
- **strength** — Garmin has no exercise sets for Ammar (checked Aug–Oct 2026), so there is no order in the data: **the scene keys are the exercises** (`squat`, `bench_press`, `deadlift` …, from the clips + what he says). Each scene's HR (avg/max + trace) comes from its clip's shoot time (`creation_time` + `in`, matched to `_session.hr5`) — so use the clip actually shot during that exercise. Sets/kg he mentions go in `title: ["EXERCISE 02","BENCH PRESS","","<b>4×8</b> · 80 KG"]`.
- **none** (`session.source: "none"`) — titles + captions only.

## Revisions (what Ammar usually asks)
- "X shot starts from here" (screenshot of the player scrubber): read the scrubber fraction × clip duration → set that scene's `in`; or match the frame with a quick contact sheet around the guess. Rebuild with `--only <key>`.
- "Use this video for X": set `clip`; `crop: "full"` if he wants the whole frame even when he's small.
- "Use my music / this track": `audio.music_file` = a file name in the music library (`~/.pulse-studio/music/`, shared by all sessions; the web app uploads there), `audio.music_in` = seconds to start from; `"generated"` = the code-made track. Then `pulse-reel audio`.
- "Replace/delete a clip": the web app does it in place (same file name keeps the scenes valid, stale cuts are dropped); from the CLI just overwrite the file in `raw/` and rebuild with `--only` the scenes that use it.
- "Raise/lower the music/SFX": `audio.music_db` / `sfx_db` ±5 then `pulse-reel audio <dir>` (audio-only remix, ~3 min).
- "Mute the clip sound at the start": that scene `amb_db: -90`. Keep wall-ball / sled scenes at −2 dB when he likes the real sound.
- Caption wording: edit `caption`; the words re-map to the transcript timings automatically.
- Title/number override: scene `title: ["KICKER","NAME","4:06","<b>2:03</b> /500M"]`.
- Effects (per scene, `fx` list): `zoomcut` (snap zoom-in on the cut, pairs with the whoosh), `storm` (the sub-line facts flash one by one before the title — "1000 M", "2:03 /500M", "34 SPM"), `glass` (frosted liquid-glass pane behind the title; breaks the no-panels rule, use sparingly), `chat` (caption as chat bubbles instead of karaoke). `inset: {"file":"assets/erg.png","label":"ERGDATA","at":1.2,"w":300,"pos":[740,980]}` = b-roll picture-in-picture (ErgData screen, watch face). `phone: {"file":"assets/pulse.png","at":0.8}` = phone mockup (the Pulse app) — on the closing it pushes the stats to the left. Closing `style: "checklist"` = stations tick off one by one with their times, then the totals. Ammar's defaults from the reference reels: storm on the erg stations, checklist closing with the phone.
- Always `pulse-reel build` or `audio` after edits, read the new contact sheet, report the version number. Never overwrite an earlier version.

## Web app
`pulse-reel ui` (http://127.0.0.1:8787) edits the same `project.json`; if Ammar is using it, re-read project.json before changing anything and tell him to refresh the page after your edits.

## Delivery
`pulse-reel publish <dir>` with `PULSE_SHARE=user@host:/path/` set (Ammar's is the Pulse VPS share folder) → link `<pulse url>/share/<file>`. Curl the link back and ffprobe it before sending; a half-written file once went out.

## Identity (don't change without asking)
climbday: transparent overlays only, Anton + Archivo + Noto Kufi Arabic, bone #F4EFE6 / orange #FF5A1E, grain + vignette, @AMMARHUSSEIN, IG safe zones (top 250 px, bottom 340 px), 1080×1920 30 fps H.264 Main no B-frames ~34 MB/60 s.
