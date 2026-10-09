// Rendu image par image avec Playwright.
//   node render.mjs beats   → une image par temps (28) + planche contact
//   node render.mjs video   → 60 fps, 4 sous-images par image, flou de bougé via ffmpeg tmix
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import os from 'node:os';

const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch { pw = require('/opt/node-tools/node_modules/playwright'); }

const DIR = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(DIR, 'out');
const URL = pathToFileURL(path.join(DIR, 'index.html')).href + '?render';
const mode = process.argv[2] || 'beats';
const FPS = 60, SUB = 4, SHUTTER = 0.5;   // obturateur 180°

async function pages(n) {
  const browser = await pw.chromium.launch();
  const list = [];
  for (let i = 0; i < n; i++) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1440 }, deviceScaleFactor: 1 });
    await page.goto(URL);
    await page.evaluate(() => window.ready);
    list.push(page);
  }
  return { browser, list };
}
async function shoot(page, t, file) {
  await page.evaluate(t => window.seek(t), t);
  await page.screenshot({ path: file, clip: { x: 0, y: 0, width: 1440, height: 1440 } });
}
async function pool(jobs, workers) {
  const { browser, list } = await pages(workers);
  let next = 0, done = 0;
  await Promise.all(list.map(async page => {
    while (next < jobs.length) {
      const [t, file] = jobs[next++];
      await shoot(page, t, file);
      if (++done % 200 === 0) console.log(`${done}/${jobs.length}`);
    }
  }));
  await browser.close();
}

const T = 14, BEAT = 0.5;
if (mode === 'beats' || mode === 'at') {
  const dir = path.join(OUT, 'beats'); rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
  const times = mode === 'at' ? process.argv.slice(3).map(Number) : Array.from({ length: 28 }, (_, i) => i * BEAT + (Number(process.argv[3]) || 0));
  await pool(times.map((t, i) => [t, path.join(dir, `b${String(i + 1).padStart(2, '0')}.png`)]), 4);
  if (mode === 'beats') {
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', path.join(dir, 'b%02d.png'),
      '-vf', 'scale=360:360,drawtext=text=\'%{eif\\:n+1\\:d}\':x=10:y=10:fontsize=22:fontcolor=black,tile=7x4:padding=4:color=white',
      '-frames:v', '1', path.join(OUT, 'beats.png')]);
    console.log('→ out/beats.png');
  }
} else if (mode === 'video') {
  const dir = path.join(OUT, 'sub'); rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
  const frames = T * FPS, jobs = [];
  for (let k = 0; k < frames; k++)
    for (let j = 0; j < SUB; j++) {
      const t = (k + (j - (SUB - 1) / 2) / SUB * SHUTTER) / FPS;
      jobs.push([((t % T) + T) % T, path.join(dir, `${String(k * SUB + j).padStart(5, '0')}.png`)]);
    }
  console.time('capture');
  await pool(jobs, Math.max(2, os.cpus().length));
  console.timeEnd('capture');
  // tmix fait la moyenne des 4 sous-images ; on garde la dernière de chaque groupe
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(FPS * SUB), '-i', path.join(dir, '%05d.png'),
    '-vf', `tmix=frames=${SUB},select='eq(mod(n\\,${SUB})\\,${SUB - 1})',setpts=N/(${FPS}*TB)`,
    '-r', String(FPS), '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    path.join(OUT, 'one-shape.mp4')]);
  console.log('→ out/one-shape.mp4');
}
