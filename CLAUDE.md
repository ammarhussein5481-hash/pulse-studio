# Pulse Studio

Local reel builder for Ammar's training sessions: clips (4K camera + phone) + a voice-over he records + live session data from Pulse (Garmin / ErgData / WHOOP) → one 9:16 reel in the climbday identity (60 s by default, `vo.budget_s` per project; the timeline fits the voice-over to that length). Ubuntu laptop first; everything is CPU-only Python/Node/ffmpeg. Built on 2026-11-01 from the HYROX reel pipeline that ran on the VPS.

## Layout
- `pulse_studio/` — the engine. `cli.py` (`pulse-reel`), `ingest.py` (clip inventory by shoot time + motion + contact sheets), `data.py` (Pulse session data, or none), `pulse.py` (Pulse index for the session picker), `stt.py` (faster-whisper word timestamps), `timeline.py` (VO-driven scene timing, pause compression, tempo), `media.py` (cut/crop/concat/grain, VAAPI decode when available), `overlay/` (HTML overlay rendered per frame with chrome-headless-shell over CDP), `sfx.py` + `music.py` (code-generated audio), `mix.py` (composite + loudness), `ui/` (FastAPI single-page web app `pulse-reel ui`; runs the CLI steps as subprocesses and streams their logs — never re-implement a step there; its Claude panel runs headless `claude -p "/reel …"` on the session, resumed per session via `build/claude_session`, English replies, project saves from the page locked while it works).
- `server/export_session.py` — runs on the Pulse VPS (cron `--sync` every 10 min), writes `site/sessions/<date>-<type>.json` (the data the laptop pulls) and `sessions/index.json` (the picker list).
- `.claude/skills/reel/SKILL.md` — the `/reel` skill: how to turn Ammar's instructions into project.json edits and CLI calls. Read it before touching a session.
- `examples/hyrox-2026-11-01/` — the real first session (project.json + data.json) as the reference shape.
- `sessions/` (git-ignored) — working projects.

## Rules
- `project.json` is the source of truth; never hand-edit `build/`.
- Keep the climbday identity (see SKILL.md). Station names on screen are English; captions are Ammar's Arabic, corrected but not rewritten.
- Every build is a new `out/<name>-vN.mp4`; check the contact sheet before reporting; verify a published link by downloading it.
- Work on the laptop; don't push heavy media to git (gitignored).

## Test
`PULSE_STUDIO_HOME=/tmp/psh ./setup.sh` once, then on a project folder: `pulse-reel ingest`, `data`, `stt`, `timeline`, `stills`, `build`. Synthetic smoke test: generate a few `testsrc2` clips into `raw/`, copy `examples/.../data.json` with `session.source = "file"`.
