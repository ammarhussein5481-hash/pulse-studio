#!/usr/bin/env python3
"""Rider masks for every frame of base2.mp4 (u2net, onnx) → masks/m_%05d.png + person_boxes.json.

Flicker-free by construction:
  * photo scenes: ONE mask computed on the photo canvas, then moved with the scene's own Ken Burns matrices
    (seg2/<sid>.kb.json from base2.py) — identical motion, no frame-to-frame jitter;
  * clip scenes: per-frame masks, smoothed with a 5-frame temporal median; a clip whose rider still can't be
    tracked steadily (mask popping on/off) gets no cut-out at all — the big text just sits on top instead of flickering.
usage: masks.py            (REUSE=1 keeps existing raw clip masks in masks/raw/ and only re-does smoothing)"""
import os, sys, json, numpy as np, cv2, onnxruntime as ort
D = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(D, "masks"); RAW = os.path.join(OUT, "raw")
os.makedirs(RAW, exist_ok=True)
tl = json.load(open(os.path.join(D, "timeline2.json"))); FPS = tl["fps"]; W, H = 1080, 1920
REUSE = os.environ.get("REUSE") == "1"
_sess = None
def sess():
    global _sess
    if _sess is None:
        so = ort.SessionOptions(); so.intra_op_num_threads = os.cpu_count() or 2; so.inter_op_num_threads = 1
        _sess = ort.InferenceSession(os.path.expanduser("~/.u2net/u2net.onnx"), so, providers=["CPUExecutionProvider"])
    return _sess
MEAN = np.array([0.485, 0.456, 0.406], np.float32); STD = np.array([0.229, 0.224, 0.225], np.float32)
def predict(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB); small = cv2.resize(rgb, (320, 320), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    x = ((small - MEAN) / STD).transpose(2, 0, 1)[None]
    p = sess().run(None, {sess().get_inputs()[0].name: x})[0][0, 0]
    p = (p - p.min()) / (p.max() - p.min() + 1e-6)
    m = cv2.resize(p, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
    m = np.clip((m - 0.35) / 0.3, 0, 1)  # soft threshold
    # drop blobs that touch the top edge (cliffs, ceilings, trees) or cover >45% of the frame — a rider never does
    bw = (m > 0.5).astype(np.uint8); n, lab, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    hh_, ww_ = bw.shape
    for k in range(1, n):
        x0, y0, w, hh, area = stats[k]
        if y0 == 0 or area > 0.45 * hh_ * ww_: m[lab == k] = 0
    m = cv2.GaussianBlur(m, (0, 0), 2.5 * bw.shape[1] / W)
    return (m * 255).astype(np.uint8)

def iou(a, b):
    a = a > 128; b = b > 128; u = (a | b).sum(); return 1.0 if u == 0 else (a & b).sum() / u

boxes = {}
cap = cv2.VideoCapture(os.path.join(D, "base2.mp4")); fi = 0
def write(i, m, sid):
    cv2.imwrite(os.path.join(OUT, f"m_{i:05d}.png"), m)
    ys, xs = np.where(m > 128)
    if len(xs) > 2000:
        b = [xs.min() / W, ys.min() / H, xs.max() / W, ys.max() / H]; bb = boxes.get(sid)
        boxes[sid] = b if bb is None else [min(bb[0], b[0]), min(bb[1], b[1]), max(bb[2], b[2]), max(bb[3], b[3])]

for s in tl["scenes"]:
    a, z = round(s["start"] * FPS), round(s["end"] * FPS); n = z - a; sid = s["id"]
    kb = os.path.join(D, "seg2", sid + ".kb.json")
    if os.path.exists(kb):   # photo: one mask, same motion as the picture
        K = json.load(open(kb)); canvas = cv2.imread(K["canvas"]); cm = predict(canvas)
        for k in range(n):
            M = np.array(K["M"][min(k, len(K["M"]) - 1)], np.float64)
            write(a + k, cv2.warpAffine(cm, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0), sid)
        for _ in range(n): cap.grab(); fi += 1
        print(f"{sid:6s} photo  mask once, moved with the Ken Burns", flush=True); continue
    # clip: raw per-frame masks at half size (they're soft; full size is restored on write)
    raw = []
    for k in range(n):
        ok, fr = cap.read(); fi += 1; rp = os.path.join(RAW, f"r_{a + k:05d}.png")
        if REUSE and os.path.exists(rp): m = cv2.imread(rp, 0)
        else:
            m = predict(fr) if ok else np.zeros((H, W), np.uint8); cv2.imwrite(rp, m)
        raw.append(cv2.resize(m, (W // 2, H // 2), interpolation=cv2.INTER_AREA))
    st = np.stack(raw)
    sm = np.stack([np.median(st[max(0, k - 2):min(n, k + 3)], axis=0).astype(np.uint8) for k in range(n)])   # 5-frame temporal median
    present = np.array([(m > 128).sum() > 0.004 * m.size for m in sm])
    unstable = sum(1 for k in range(1, n) if (present[k] or present[k - 1]) and iou(sm[k], sm[k - 1]) < 0.85)
    keep = present.mean() >= 0.7 and unstable <= 0.08 * n
    for k in range(n):
        m = cv2.resize(sm[k], (W, H), interpolation=cv2.INTER_LINEAR) if keep else np.zeros((H, W), np.uint8)
        write(a + k, m, sid)
    print(f"{sid:6s} clip   rider in {present.mean():.0%} of frames, {unstable} unstable → {'cut-out ON' if keep else 'cut-out OFF (text on top)'}", flush=True)
json.dump(boxes, open(os.path.join(D, "person_boxes.json"), "w"), indent=1)
print("done", fi)
