# Une forme, douze états

Boucle de 14 s (120 BPM, 7 mesures, 28 temps), 1440×1440, 60 fps, muette.
Une seule forme qui se transforme : bouton → loader → check → dynamic island → lecteur → scrub →
volume (s'étire au-delà du max) → toggle → onglets → graphique → ⌘K → toast → bouton.

- `index.html` : toute l'animation. `seek(t)` calcule chaque style à partir du temps uniquement
  (ressorts en forme fermée, aucune transition CSS, aucun timer, aucun état entre deux images).
  Ouvert directement dans un navigateur : aperçu en boucle (espace = pause, ←/→ = un temps).
- `render.mjs` : rendu Playwright.
  - `node render.mjs beats [décalage]` → une image par temps + planche contact `out/beats.png`
  - `node render.mjs video` → 4 sous-images par image, fusionnées par `ffmpeg tmix` (flou de bougé) → `out/one-shape.mp4`
- `fonts/` : Geist (SIL Open Font License).
