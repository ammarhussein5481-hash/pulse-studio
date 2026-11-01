"""pulse-reel ui — local web app over the same pipeline (FastAPI, single page).

Everything the page does goes through the CLI steps as subprocesses, so the UI and `pulse-reel` never diverge.
"""
from __future__ import annotations
import json, os, re, shutil, subprocess, sys, threading, time, uuid, webbrowser
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from .. import project, config, pulse, data as datamod
from ..config import ffmpeg

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("PULSE_SESSIONS", "sessions")).resolve()
STEPS = {"ingest", "data", "stt", "timeline", "stills", "build", "audio", "publish"}
RAW_EXT = {".mov", ".mp4", ".m4v", ".mkv"}; VO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".ogg", ".webm", ".opus"}

app = FastAPI(title="Pulse Studio")

# ---------- jobs (one at a time; log lines streamed over SSE) ----------
class Job:
    def __init__(self, cmd: list[str], cwd: Path, fmt=None, kind: str = "step", env: dict | None = None):
        self.id = uuid.uuid4().hex[:8]; self.cmd = cmd; self.lines: list[str] = []; self.rc: int | None = None; self.started = time.time()
        self.fmt = fmt or (lambda l: [l]); self.kind = kind
        self.proc = subprocess.Popen(cmd, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
                                     env={**os.environ, "PYTHONUNBUFFERED": "1", **(env or {})})
        threading.Thread(target=self._pump, daemon=True).start()
    def _pump(self):
        for line in self.proc.stdout:
            self.lines.extend(self.fmt(line.rstrip("\n")))
        self.rc = self.proc.wait()
    @property
    def running(self): return self.rc is None

JOBS: dict[str, Job] = {}
CURRENT: Job | None = None

def _sid(sid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", sid) or sid.startswith("."):
        raise HTTPException(400, "bad session id")
    d = ROOT / sid
    if not (d / "project.json").exists():
        raise HTTPException(404, f"no session {sid}")
    return d

def _latest(outdir: Path, name: str) -> list[dict]:
    vs = []
    for p in sorted(outdir.glob(f"{name}-v*.mp4"), key=lambda p: p.stat().st_mtime):
        v = p.stem.rsplit("-v", 1)[1]
        vs.append({"v": int(v) if v.isdigit() else v, "file": p.name, "mb": round(p.stat().st_size / 1e6, 1),
                   "sheet": p.with_suffix(".jpg").name if p.with_suffix(".jpg").exists() else None, "mtime": p.stat().st_mtime})
    return vs

def _jload(p: Path):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return None

def _state(d: Path) -> dict:
    proj = project.load(d); b = d / "build"
    raw = sorted(f.name for f in (d / "raw").glob("*") if f.suffix.lower() in RAW_EXT)
    vo = sorted(f.name for f in (d / "vo").glob("*") if f.suffix.lower() in VO_EXT)
    stt = {f.stem[4:]: _jload(f) for f in b.glob("stt_*.json")}
    stills = sorted(f.name for f in (b / "stills").glob("*.png")) if (b / "stills").exists() else []
    data = datamod.empty(proj) if proj["session"].get("source") == "none" else _jload(b / "data.json")
    return {"id": d.name, "project": proj, "raw": raw, "vo": vo, "clips": _jload(b / "clips.json") or [],
            "stt": stt, "timeline": _jload(b / "timeline.json"), "data": data, "stills": stills,
            "outs": _latest(d / "out", proj["name"]), "frames": (b / "frames").exists(),
            "env": {"token": bool(os.environ.get("PULSE_TOKEN")), "share": os.environ.get("PULSE_SHARE", "")}}

# ---------- routes ----------
@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "index.html").read_text(encoding="utf-8")

@app.get("/fonts/{path:path}")
def fonts(path: str):
    p = (config.fonts_dir() / path).resolve()
    if not str(p).startswith(str(config.fonts_dir().resolve())) or not p.is_file(): raise HTTPException(404)
    return FileResponse(p)

@app.get("/api/sessions")
def sessions():
    ROOT.mkdir(parents=True, exist_ok=True); out = []
    for d in sorted(ROOT.iterdir(), reverse=True):
        if (d / "project.json").exists():
            pj = _jload(d / "project.json") or {}
            out.append({"id": d.name, "date": pj.get("session", {}).get("date"), "type": pj.get("session", {}).get("type"),
                        "scenes": len(pj.get("scenes", [])), "outs": len(list((d / "out").glob("*.mp4")))})
    return {"root": str(ROOT), "sessions": out, "job": CURRENT.id if CURRENT and CURRENT.running else None}

@app.get("/api/pulse/sessions")
def pulse_sessions(refresh: bool = False):
    try: return pulse.sessions(ROOT, refresh=refresh)
    except SystemExit as e: raise HTTPException(502, str(e))
    except Exception as e: raise HTTPException(502, f"Pulse unreachable: {e}")

def _free_sid(base: str, alt: str) -> str:
    if not (ROOT / base).exists(): return base
    for sid in (f"{base}-{alt}", *(f"{base}-{i}" for i in range(2, 50))):
        if not (ROOT / sid).exists(): return sid
    raise HTTPException(409, f"{base} exists")

@app.post("/api/sessions")
async def new_session(req: Request):
    j = await req.json(); budget = j.get("budget")
    if j.get("pulse_id"):
        try: s = pulse.find(str(j["pulse_id"]))
        except SystemExit as e: raise HTTPException(404, str(e))
        sid = _free_sid(f"{s['date']}-{s['type']}", (str(s.get("start") or "")[11:16].replace(":", "") or s["id"]))
        project.new_from_pulse(ROOT / sid, sid, s)
    else:
        date = j.get("date", ""); kind = j.get("type", "hyrox")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date): raise HTTPException(400, "date must be YYYY-MM-DD")
        base = f"{date}-{re.sub(r'[^a-z0-9]+', '-', kind.lower())}"
        if (ROOT / base / "project.json").exists() and not j.get("another"): raise HTTPException(409, f"{base} exists")
        sid = _free_sid(base, "2"); project.new(ROOT / sid, sid, date, kind)
    pj = project.load(ROOT / sid)
    if budget: pj["vo"]["budget_s"] = float(budget)
    if j.get("no_data"): pj["session"]["source"] = "none"
    project.save(ROOT / sid, pj)
    return {"id": sid}

@app.get("/api/s/{sid}")
def get_session(sid: str):
    return _state(_sid(sid))

@app.put("/api/s/{sid}/project")
async def put_project(sid: str, req: Request):
    d = _sid(sid); pj = await req.json()
    if not isinstance(pj, dict) or "scenes" not in pj: raise HTTPException(400, "not a project")
    if CURRENT and CURRENT.running and CURRENT.kind == "claude":
        raise HTTPException(409, "the assistant is editing this project — wait for it to finish")
    project.save(d, pj); return {"ok": True}

@app.post("/api/s/{sid}/upload")
async def upload(sid: str, kind: str = Form(...), files: list[UploadFile] = File(...)):
    d = _sid(sid); sub = {"raw": "raw", "vo": "vo"}.get(kind)
    if not sub: raise HTTPException(400, "kind must be raw|vo")
    names = []
    for f in files:
        name = Path(f.filename or "file").name
        if not re.fullmatch(r"[\w .()-]+", name): raise HTTPException(400, f"bad name {name}")
        dest = d / sub / name
        with dest.open("wb") as w:
            while chunk := await f.read(1 << 20): w.write(chunk)
        names.append(name)
    return {"saved": names}

@app.post("/api/s/{sid}/record")
async def record(sid: str, name: str = Form(...), file: UploadFile = File(...)):
    """Browser recording (webm/opus) → vo/<name>.m4a via ffmpeg; also registers it in project.vo if new."""
    d = _sid(sid); name = re.sub(r"[^A-Za-z0-9_-]", "", name) or "main"
    tmp = d / "vo" / f".rec_{name}.webm"; out = d / "vo" / f"{name}.m4a"
    with tmp.open("wb") as w:
        while chunk := await file.read(1 << 20): w.write(chunk)
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-i", str(tmp), "-ac", "1", "-ar", "48000", "-c:a", "aac", "-b:a", "128k", str(out)], check=True)
    tmp.unlink(missing_ok=True)
    pj = project.load(d); rel = f"vo/{name}.m4a"
    if name == "main": pj["vo"]["main"] = rel
    elif rel not in pj["vo"].get("extra", {}).values(): pj["vo"].setdefault("extra", {})[name] = rel
    project.save(d, pj)
    for s in (d / "build").glob(f"stt_{name}.json"): s.unlink()
    return {"file": out.name}

@app.delete("/api/s/{sid}/file")
def delete_file(sid: str, kind: str, name: str):
    d = _sid(sid); sub = {"raw": "raw", "vo": "vo"}.get(kind)
    p = d / sub / Path(name).name
    if not sub or not p.exists(): raise HTTPException(404)
    p.unlink(); return {"ok": True}

@app.delete("/api/s/{sid}")
def delete_session(sid: str):
    d = _sid(sid)
    if CURRENT and CURRENT.running: raise HTTPException(409, "a job is running — stop it first")
    shutil.rmtree(d); return {"ok": True}

@app.post("/api/s/{sid}/run/{step}")
async def run_step(sid: str, step: str, req: Request):
    global CURRENT
    d = _sid(sid)
    if step not in STEPS: raise HTTPException(400, "unknown step")
    if CURRENT and CURRENT.running: raise HTTPException(409, "a job is already running")
    j = await req.json() if (await req.body()) else {}
    cmd = [sys.executable, "-m", "pulse_studio.cli", step, str(d)]
    if j.get("force") and step in ("data", "stt"): cmd.append("--force")
    if j.get("only") and step == "build": cmd += ["--only", j["only"]]
    if j.get("no_frames") and step == "build": cmd.append("--no-frames")
    if j.get("times") and step == "stills": cmd.append(j["times"])
    if j.get("to") and step == "publish": cmd += ["--to", j["to"]]
    CURRENT = Job(cmd, d.parent); JOBS[CURRENT.id] = CURRENT
    return {"job": CURRENT.id}

# ---------- Claude (headless Claude Code driving the /reel skill on this session) ----------
REPO = HERE.parents[1]
CLAUDE_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Skill",
                "Bash(pulse-reel:*)", "Bash(ffprobe:*)", "Bash(ffmpeg:*)", "Bash(python3:*)", "Bash(ls:*)", "Bash(cat:*)",
                "Bash(unzip:*)", "Bash(cp:*)", "Bash(mv:*)", "Bash(curl:*)", "Bash(ssh:*)", "Bash(scp:*)"]
CLAUDE_SYS = ("You are running headless from the Pulse Studio web UI; Ammar reads your log there and replies in the next message. "
              "You cannot ask interactive questions: when a decision is his (reel length, which shot, publishing), stop and end with "
              "the question. Work only on the session folder you are given. Run long steps (ingest, build ~12 min) in the FOREGROUND "
              "and wait for them — never in the background: this run ends when you stop, nothing wakes you later. Then read the "
              "contact sheet and report the out/ version and what changed at the end. Ammar asked for English in this app: always reply in English, short, "
              "even if other settings say otherwise (captions stay his Arabic).")

def _claude_fmt(sess_file: Path):
    def fmt(line: str) -> list[str]:
        try: ev = json.loads(line)
        except ValueError: return [line] if line.strip() else []
        if ev.get("session_id"): sess_file.write_text(ev["session_id"])
        t = ev.get("type")
        if t == "assistant":
            out = []
            for c in ev.get("message", {}).get("content", []):
                if c.get("type") == "text" and c["text"].strip(): out.append(c["text"].strip())
                elif c.get("type") == "tool_use":
                    i = c.get("input", {})
                    what = i.get("description") or i.get("command") or i.get("file_path") or i.get("skill") or i.get("pattern") or ""
                    out.append(f"  → {c['name']}: {str(what)[:160]}")
            return out
        if t == "user":
            return [f"  ! {str(c.get('content'))[:200]}" for c in ev.get("message", {}).get("content", [])
                    if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("is_error")]
        if t == "result":
            return [f"— {ev.get('num_turns', '?')} turns · {round(ev.get('duration_ms', 0) / 60000, 1)} min —"]
        return []
    return fmt

@app.post("/api/s/{sid}/claude")
async def ask_claude(sid: str, req: Request):
    global CURRENT
    d = _sid(sid); j = await req.json(); text = (j.get("prompt") or "").strip()
    if not text: raise HTTPException(400, "empty instruction")
    if CURRENT and CURRENT.running: raise HTTPException(409, "a job is already running")
    claude = shutil.which("claude")
    if not claude: raise HTTPException(500, "claude CLI not found on PATH")
    sess_file = d / "build" / "claude_session"; sess_file.parent.mkdir(exist_ok=True)
    if j.get("new"): sess_file.unlink(missing_ok=True)
    rel = d.relative_to(REPO) if d.is_relative_to(REPO) else d
    cmd = [claude, "-p", f"/reel {text}\n\n(session folder: {rel})", "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits", "--allowedTools", *CLAUDE_TOOLS, "--add-dir", str(d), "--settings", json.dumps({"language": "english"}), "--append-system-prompt", CLAUDE_SYS]
    if sess_file.exists() and sess_file.read_text().strip(): cmd += ["--resume", sess_file.read_text().strip()]
    long = {"BASH_DEFAULT_TIMEOUT_MS": "2700000", "BASH_MAX_TIMEOUT_MS": "2700000"}   # a build must fit in one foreground command
    CURRENT = Job(cmd, REPO, fmt=_claude_fmt(sess_file), kind="claude", env=long); JOBS[CURRENT.id] = CURRENT
    return {"job": CURRENT.id}

@app.get("/api/jobs/{jid}")
def job(jid: str):
    j = JOBS.get(jid)
    if not j: raise HTTPException(404)
    return {"id": j.id, "cmd": j.cmd[2:], "rc": j.rc, "running": j.running, "lines": j.lines}

@app.get("/api/jobs/{jid}/stream")
def job_stream(jid: str):
    j = JOBS.get(jid)
    if not j: raise HTTPException(404)
    def gen():
        i = 0
        while True:
            while i < len(j.lines):
                yield f"data: {json.dumps(j.lines[i])}\n\n"; i += 1
            if not j.running and i >= len(j.lines):
                yield f"event: done\ndata: {j.rc}\n\n"; return
            time.sleep(0.3)
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

@app.post("/api/jobs/{jid}/stop")
def job_stop(jid: str):
    j = JOBS.get(jid)
    if j and j.running: j.proc.terminate()
    return {"ok": True}

@app.get("/files/{sid}/{path:path}")
def files(sid: str, path: str):
    d = _sid(sid); p = (d / path).resolve()
    if not str(p).startswith(str(d.resolve())) or not p.is_file(): raise HTTPException(404)
    return FileResponse(p)

def main(argv=None):
    import argparse, uvicorn
    ap = argparse.ArgumentParser(prog="pulse-reel ui"); ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--root", default=None, help="sessions folder (default ./sessions or $PULSE_SESSIONS)"); ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args(argv)
    global ROOT
    if a.root: ROOT = Path(a.root).resolve()
    ROOT.mkdir(parents=True, exist_ok=True)
    url = f"http://127.0.0.1:{a.port}"; print(f"Pulse Studio UI → {url}   (sessions in {ROOT})")
    if not a.no_open: threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")

if __name__ == "__main__":
    main()
