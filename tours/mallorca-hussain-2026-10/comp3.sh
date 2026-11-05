#!/bin/bash
# v3 composite: base → back layer → rider cut-out (mask) → front layer; grain/vignette; SFX; loudnorm.
set -e; cd "$(dirname "$0")"
ffmpeg -nostdin -y -v error -i base2.mp4 -framerate 30 -i frames3/b_%05d.png -framerate 30 -i masks/m_%05d.png -framerate 30 -i frames3/f_%05d.png -i sfx2.wav \
  -filter_complex "[0:v]noise=alls=6:allf=t,vignette=PI/5,split[b0][b1];[b0][1:v]overlay=0:0:format=auto[s1];[2:v]format=gray[m];[b1][m]alphamerge[rider];[s1][rider]overlay=0:0:format=auto[s2];[s2][3:v]overlay=0:0:format=auto[v];[0:a]volume=-3dB[amb];[4:a]volume=-6dB,aformat=channel_layouts=stereo[sfx];[amb][sfx]amix=inputs=2:normalize=0,loudnorm=I=-15:TP=-1.5:LRA=11[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -profile:v main -preset medium -crf 23 -maxrate 8M -bufsize 16M -bf 0 -pix_fmt yuv420p -movflags +faststart -c:a aac -b:a 160k hussain_mallorca_draft_v5.mp4
ffprobe -v error -show_entries format=duration,size -of compact hussain_mallorca_draft_v5.mp4; echo COMP3DONE
