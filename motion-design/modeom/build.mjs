// Assemble un seul fichier HTML autonome : Three.js, ressorts et polices intégrés en data: URL.
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const D = path.dirname(fileURLToPath(import.meta.url));
const b64 = (f, type) => `data:${type};base64,${readFileSync(path.join(D, f)).toString('base64')}`;
let html = readFileSync(path.join(D, 'src/index.html'), 'utf8');
const map = {
  __THREE__: b64('vendor/three.module.js', 'text/javascript'),
  __ROOM__: b64('vendor/RoomEnvironment.js', 'text/javascript'),
  __SPRINGS__: b64('src/springs.js', 'text/javascript'),
  __GEIST__: b64('../motion/fonts/Geist-Variable.woff2', 'font/woff2'),
  __MONO__: b64('../motion/fonts/GeistMono-Regular.woff2', 'font/woff2'),
};
for (const [k, v] of Object.entries(map)) html = html.split(k).join(v);
writeFileSync(path.join(D, 'modeom.html'), html);
console.log(`modeom.html · ${(html.length / 1e6).toFixed(2)} Mo`);
