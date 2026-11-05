// Two-layer overlay renderer: back (behind rider) + front.  node frames3.mjs all | stills 1,2,3
import { chromium } from "playwright"; import fs from "fs"; import path from "path";
const dir = path.dirname(new URL(import.meta.url).pathname);
const tl = JSON.parse(fs.readFileSync(path.join(dir, "timeline2.json"), "utf8"));
const rd = f => fs.readFileSync(path.join(dir, f), "utf8");
const html = rd("ov3.html").replace("__RIDES__", rd("rides.json")).replace("__TL__", JSON.stringify(tl)).replace("__ISLAND__", rd("island.json")).replace("__STREAMS__", rd("streams.json")).replace("__BOXES__", rd("person_boxes.json"));
fs.writeFileSync(path.join(dir, "ov3.built.html"), html);
const mode = process.argv[2] || "all";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1080, height: 1920 }, deviceScaleFactor: 1 });
await page.goto("file://" + path.join(dir, "ov3.built.html"));
await page.evaluate(() => document.fonts.ready); await page.evaluate(() => render(0.5, "front")); await page.waitForTimeout(300);
async function shot(t, file, layer){ await page.evaluate(([t,l]) => render(t,l), [t,layer]); await page.screenshot({ path: file, omitBackground: true }); }
if (mode === "stills") {
  const out = path.join(dir, "stills3"); fs.mkdirSync(out, { recursive: true });
  for (const t of process.argv[3].split(",").map(Number)) { await shot(t, path.join(out, `b_${t}.png`), "back"); await shot(t, path.join(out, `f_${t}.png`), "front"); }
} else {
  const out = path.join(dir, "frames3"); fs.rmSync(out, { recursive: true, force: true }); fs.mkdirSync(out);
  const n = Math.round(tl.total * tl.fps); const t0 = Date.now();
  for (let i = 0; i < n; i++) { const t = i / tl.fps, id = String(i).padStart(5, "0");
    await shot(t, path.join(out, `b_${id}.png`), "back"); await shot(t, path.join(out, `f_${id}.png`), "front");
    if (i % 300 === 0) console.log(i, "/", n, ((Date.now() - t0) / 1000).toFixed(0) + "s"); }
  console.log("done", n);
}
await browser.close();
