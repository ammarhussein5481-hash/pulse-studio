"""Final composite: base video + overlay PNG sequence; VO placed on the timeline, music ducked under VO, SFX, ambience; loudnorm."""
from __future__ import annotations
import subprocess, json
from pathlib import Path
from .config import venc, vaapi_tail, vaapi_dev, ffmpeg, ffprobe, FPS, BITRATE

def vo_track(dir: Path, tl: dict, out: Path) -> Path | None:
    """Concatenates the per-scene VO segments at their timeline positions (atempo applied)."""
    dir = Path(dir); segs = [s for s in tl["scenes"] if s.get("vo")]
    if not segs: return None
    ins, fl, names = [], "", ""
    for i, s in enumerate(segs):
        ins += ["-i", str(dir / s["vo"])]
        fl += f"[{i}:a]atempo={tl['tempo']},aresample=48000,adelay={int(s['vo_at'] * 1000)}:all=1[v{i}];"; names += f"[v{i}]"
    fl += f"{names}amix=inputs={len(segs)}:duration=longest:normalize=0,apad=whole_dur={tl['budget']},loudnorm=I=-16:TP=-1.5:LRA=9[vo]"
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", *ins, "-filter_complex", fl, "-map", "[vo]", "-ac", "1", "-ar", "48000", "-t", str(tl["budget"]), str(out)], check=True)
    return out

def composite(dir: Path, proj: dict, tl: dict, out: Path, frames: Path | None = None) -> Path:
    dir = Path(dir); b = dir / "build"; frames = frames or (b / "frames")
    a = proj["audio"]; T = tl["budget"]
    inputs = ["-i", str(b / "base_v.mp4"), "-framerate", str(FPS), "-i", str(frames / "%05d.png"), "-i", str(b / "base_a.m4a")]
    vo = b / "vo_full.wav"; mus = b / "music.wav"; fx = b / "sfx.wav"
    have_vo, have_mus, have_fx = vo.exists(), a.get("music", True) and mus.exists(), a.get("sfx", True) and fx.exists()
    idx = 3; af = f"[2:a]apad,volume={a.get('amb_db', -4)}dB[amb];"; mix = ["[amb]"]
    if have_vo:
        inputs += ["-i", str(vo)]; af += f"[{idx}:a]asplit[vo1][vo2];"; vo_i = idx; idx += 1
    if have_mus:
        inputs += ["-i", str(mus)]
        if have_vo: af += f"[{idx}:a]volume={a.get('music_db', -5)}dB[m0];[m0][vo1]sidechaincompress=threshold={a.get('duck_threshold', 0.02)}:ratio={a.get('duck_ratio', 6)}:attack=15:release=500:makeup=1[mus];"
        else: af += f"[{idx}:a]volume={a.get('music_db', -5)}dB[mus];"
        mix.append("[mus]"); idx += 1
    if have_fx:
        inputs += ["-i", str(fx)]; af += f"[{idx}:a]volume={a.get('sfx_db', -7)}dB[fx];"; mix.append("[fx]"); idx += 1
    if have_vo: mix.append("[vo2]")
    af += "".join(mix) + f"amix=inputs={len(mix)}:duration=longest:normalize=0,loudnorm=I=-15:TP=-1.5:LRA=11[a]"
    vf = "[0:v]tpad=stop_mode=clone:stop_duration=1.5[bv];[bv][1:v]overlay=0:0:format=auto" + (",format=yuv420p" + vaapi_tail() if vaapi_tail() else ",format=yuv420p") + "[v]"
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", *vaapi_dev(), *inputs, "-filter_complex", vf + ";" + af, "-map", "[v]", "-map", "[a]",
                    *venc("final", BITRATE), "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", str(T), str(out)], check=True)
    return out

def verify(path: Path) -> dict:
    j = json.loads(subprocess.run([ffprobe(), "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height", "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in j["streams"] if s["codec_name"] != "aac")
    return {"duration": float(j["format"]["duration"]), "mb": round(int(j["format"]["size"]) / 1e6, 1), "size": f"{v['width']}x{v['height']}"}

def contact_sheet(src: Path, out: Path, every: float = 5.0) -> Path:
    subprocess.run([ffmpeg(), "-nostdin", "-y", "-v", "error", "-i", str(src), "-vf", f"fps=1/{every},scale=216:-1,tile=6x2", "-frames:v", "1", "-q:v", "8", str(out)], check=True)
    return out
