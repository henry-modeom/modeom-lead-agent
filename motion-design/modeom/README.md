# MODEOM — module préfabriqué, maquette de principe

Boucle de 24 s (120 BPM, 12 mesures, 48 temps), 1440×1440, 60 fps, muette.
Six scènes pilotées par une interface que le curseur manipule :

| Scène | Temps | Action du curseur |
|---|---|---|
| 1 · Structure | 1–8 | — (révélation par un plan qui monte, cotes hors tout) |
| 2 · Vue éclatée | 9–16 | clic « Éclaté », drag du slider « Écartement » au-delà du max (la pastille s'étire, revient par ressort) |
| 3 · Coupe technique | 17–24 | clic « Coupe », interrupteur « Armatures » (bords du bouton sur ressorts distincts) |
| 4 · Assemblage | 25–32 | clic « Assemblage » : plancher, voiles longitudinaux, pignons, toiture reviennent dans cet ordre |
| 5 · Vues | 33–40 | drag dans la vue → relâché, la caméra revient par ressort sur la face, puis sur le côté |
| 6 · Marque | 41–48 | conclusion, puis le module redescend pour boucler |

## ⚠️ Fidélité technique : rien n'est encore issu de vos plans

Aucun document technique n'a été fourni. **Toutes les cotes sont des hypothèses** (signalées par `*`),
regroupées dans l'objet `G` de `src/index.html` :

| Paramètre | Hypothèse | À fournir |
|---|---|---|
| Longueur × largeur × hauteur hors tout | 6,00 × 2,50 × 2,90 m | plans cotés |
| Dalle de plancher / toiture | 150 mm | coupes |
| Voiles | 120 mm | coupes |
| Enrobage, armatures | 30 mm, HA12, 2 nappes, 15 cm | plans de ferraillage |
| Décomposition en 6 éléments (plancher, 2 voiles longs, 2 pignons, toiture) | hypothèse | nomenclature, mode de fabrication (monobloc ou panneaux) |
| Ordre d'assemblage | hypothèse | procédé usine |

Volontairement **absents** car non documentés : ouvertures, inserts de levage, liaisons, joints,
réservations, finitions. Le logo est un **placeholder typographique** : à remplacer par les fichiers officiels.

## Fichiers

- `src/index.html` : scène Three.js et interface. `seek(t)` calcule tout à partir du temps seul
  (ressorts en forme fermée, pistes = somme d'un ressort par changement de cible, aucun état entre deux images).
- `src/springs.js` : ressorts, pistes périodiques, chaînes (drag → retour par ressort depuis la position et la vitesse exactes).
- `build.mjs` → `modeom.html` : **un seul fichier autonome** (Three.js, polices et ressorts intégrés).
  - ouvert tel quel : lecture en boucle (espace = pause, ←/→ = un temps)
  - `modeom.html?scroll` : le défilement de la page est la timeline (version site)
- `render.mjs` : `node render.mjs beats [décalage]` (planche des 48 temps) · `node render.mjs video` (4 sous-images/image + `ffmpeg tmix`).

Rendu Three.js temps réel (WebGL) : qualité « présentation produit », pas du photoréalisme en lancer de rayons.
