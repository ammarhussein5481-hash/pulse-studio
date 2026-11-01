// Renders the overlay page frame by frame (transparent PNG) or a few stills (JPEG on dark) with chrome-headless-shell over raw CDP.
//   node render.mjs <chrome> <page.html> frames <outdir> <from> <to> [fps]
//   node render.mjs <chrome> <page.html> stills <outdir> "2,6.5,12"
import { spawn } from "node:child_process"; import fs from "node:fs"; import path from "node:path";
const [CH, PAGE, MODE, OUT, A, B, FPSARG] = process.argv.slice(2);
const FPS = Number(FPSARG || 30); const port = 9400 + Math.floor(Math.random() * 400);
fs.mkdirSync(OUT, { recursive: true });
const p = spawn(CH, [`--remote-debugging-port=${port}`, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", "--allow-file-access-from-files", "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let tabs = null; for (let k = 0; k < 20 && !tabs; k++) { await sleep(300); try { tabs = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { } }
if (!tabs) { console.error("chrome did not start"); p.kill(); process.exit(2); }
const ws = new WebSocket(tabs.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => ws.onopen = r); let n = 0; const pend = {};
ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pend[m.id]) { pend[m.id](m); delete pend[m.id]; } };
const cdp = (method, params = {}, ms = 20000) => new Promise(r => { const id = ++n; pend[id] = r; ws.send(JSON.stringify({ id, method, params })); setTimeout(() => { if (pend[id]) { delete pend[id]; r({}); } }, ms); });
const ev = async (x, aw = false) => (await cdp("Runtime.evaluate", { expression: x, returnByValue: true, awaitPromise: aw })).result?.result;
await cdp("Page.enable"); await cdp("Runtime.enable");
await cdp("Emulation.setDeviceMetricsOverride", { width: 1080, height: 1920, deviceScaleFactor: 1, mobile: false });
const stills = MODE === "stills";
await cdp("Emulation.setDefaultBackgroundColorOverride", { color: stills ? { r: 40, g: 40, b: 40, a: 255 } : { r: 0, g: 0, b: 0, a: 0 } });
await cdp("Page.navigate", { url: "file://" + path.resolve(PAGE) }); await sleep(2000);
const ready = await ev("window.ready()", true); if (!ready || ready.value !== true) { console.error("page not ready:", JSON.stringify(ready)); p.kill(); process.exit(3); }
async function shot(t, file, fmt) {
  const r = await ev(`(()=>{try{render(${t});return "ok"}catch(e){return "ERR "+e.message}})()`); if (r?.value !== "ok") throw new Error(`render(${t}): ${r?.value}`);
  await sleep(8);
  for (let k = 0; k < 4; k++) { const s = await cdp("Page.captureScreenshot", fmt === "png" ? { format: "png" } : { format: "jpeg", quality: 82 }); if (s.result?.data) { fs.writeFileSync(file, Buffer.from(s.result.data, "base64")); return; } await sleep(300); }
  throw new Error("capture failed at " + t);
}
const t0 = Date.now();
if (stills) { for (const t of A.split(",").map(Number)) await shot(t, path.join(OUT, `still_${t}.jpg`), "jpeg"); console.log("stills done"); }
else { const from = +A, to = +B; for (let f = from; f < to; f++) { await shot(f / FPS, path.join(OUT, String(f).padStart(5, "0") + ".png"), "png"); if (f % 150 === 0) console.log(f, ((Date.now() - t0) / 1000).toFixed(0) + "s"); } console.log("frames done", to - from); }
p.kill(); process.exit(0);
