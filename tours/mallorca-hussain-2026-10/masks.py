#!/usr/bin/env python3
"""Person masks for every frame of base2.mp4 using u2net (onnx). Writes masks/m_%05d.png (grayscale) and person_boxes.json
(per scene: union bbox of the person over sampled frames, normalised 0..1). usage: masks.py [test N]"""
import os, sys, json, subprocess, numpy as np, cv2, onnxruntime as ort
D = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(D, "masks"); os.makedirs(OUT, exist_ok=True)
tl = json.load(open(os.path.join(D, "timeline2.json")))
so = ort.SessionOptions(); so.intra_op_num_threads = os.cpu_count() or 2; so.inter_op_num_threads = 1
sess = ort.InferenceSession(os.path.expanduser("~/.u2net/u2net.onnx"), so, providers=["CPUExecutionProvider"])
inp = sess.get_inputs()[0].name
MEAN = np.array([0.485, 0.456, 0.406], np.float32); STD = np.array([0.229, 0.224, 0.225], np.float32)
def predict(bgr):
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB); small = cv2.resize(rgb, (320, 320), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
    x = ((small - MEAN) / STD).transpose(2, 0, 1)[None]
    p = sess.run(None, {inp: x})[0][0, 0]
    p = (p - p.min()) / (p.max() - p.min() + 1e-6)
    m = cv2.resize(p, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR)
    m = np.clip((m - 0.35) / 0.3, 0, 1)  # soft threshold
    m = cv2.GaussianBlur(m, (0, 0), 2.5)
    return (m * 255).astype(np.uint8)
W, H = 1080, 1920; FPS = tl["fps"]; N = round(tl["total"] * FPS)
test = len(sys.argv) > 1 and sys.argv[1] == "test"
cap = cv2.VideoCapture(os.path.join(D, "base2.mp4"))
boxes = {s["id"]: None for s in tl["scenes"]}
i = 0
while True:
    ok, fr = cap.read()
    if not ok: break
    t = i / FPS; s = next((s for s in tl["scenes"] if s["start"] <= t < s["end"]), tl["scenes"][-1])
    if test and i % 60 != 0: i += 1; continue
    m = predict(fr)
    cv2.imwrite(os.path.join(OUT, f"m_{i:05d}.png"), m)
    ys, xs = np.where(m > 128)
    if len(xs) > 2000:
        b = [xs.min() / W, ys.min() / H, xs.max() / W, ys.max() / H]
        bb = boxes[s["id"]]; boxes[s["id"]] = b if bb is None else [min(bb[0], b[0]), min(bb[1], b[1]), max(bb[2], b[2]), max(bb[3], b[3])]
    if i % 300 == 0: print(i, "/", N, flush=True)
    i += 1
json.dump(boxes, open(os.path.join(D, "person_boxes.json"), "w"), indent=1)
print("done", i)
