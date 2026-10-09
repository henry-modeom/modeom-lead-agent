// Ressorts en forme fermée et pistes pures du temps.
export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, k) => a + (b - a) * k;

export const P = {
  ui:    { w: 16, z: 0.82 },   // morphs d'interface : ~1 % de dépassement
  fast:  { w: 26, z: 0.9 },
  lead:  { w: 27, z: 0.84 },   // bord avant d'un indicateur
  trail: { w: 12, z: 0.92 },   // bord arrière
  enter: { w: 24, z: 1 },
  back:  { w: 15, z: 0.8 },    // retour après un drag
  cam:   { w: 3.4, z: 1 },     // caméra : lente, sans dépassement
  cx:    { w: 12, z: 1 },
  cy:    { w: 10.5, z: 1 },
  part:  { w: 9, z: 1 },       // pièces : amorti critique, jamais d'interpénétration
  slow:  { w: 5, z: 1 },
};

// position d'un ressort parti de (x0, v0) vers x1, tau secondes après
export function spr(x0, v0, x1, p, tau) {
  const { w, z } = p, A = x0 - x1;
  if (z >= 1) return x1 + Math.exp(-w * tau) * (A + (v0 + w * A) * tau);
  const wd = w * Math.sqrt(1 - z * z), B = (v0 + z * w * A) / wd;
  return x1 + Math.exp(-z * w * tau) * (A * Math.cos(wd * tau) + B * Math.sin(wd * tau));
}
export const step = (p, tau) => (tau <= 0 ? 0 : 1 - spr(1, 0, 0, p, tau));

// Valeur qui change de cible plusieurs fois : somme d'un ressort par changement.
// Le terme en t+T reprend la queue de la boucle précédente → exactement périodique.
export function makeTrack(T) {
  return function track(v0, events, p0 = P.ui) {
    let prev = v0;
    const d = events.map(([t, v, p]) => { const e = { t, d: v - prev, p: p || p0 }; prev = v; return e; });
    if (Math.abs(prev - v0) > 1e-9) throw new Error(`piste non périodique ${v0} → ${prev}`);
    return t => {
      let s = v0;
      for (const e of d) if (e.d) s += e.d * (step(e.p, t - e.t) + step(e.p, t - e.t + T) - 1);
      return s;
    };
  };
}

// Chaîne : segments directs (f) ou ressorts (to, p) partant de la position et de la vitesse
// exactes du segment précédent. Les états aux bornes sont des constantes calculées une fois.
export function chain(f0, segs) {
  const S = [{ t: -Infinity, f: f0 }, ...segs];
  const ev = (i, t) => { const s = S[i]; return s.f ? s.f(t) : spr(s.x0, s.v0, s.to, s.p, t - s.t); };
  for (let i = 1; i < S.length; i++) {
    if (S[i].f) continue;
    const h = 1e-4, t = S[i].t;
    S[i].x0 = ev(i - 1, t);
    S[i].v0 = (ev(i - 1, t) - ev(i - 1, t - h)) / h;
  }
  return t => { let i = S.length - 1; while (i > 0 && t < S[i].t) i--; return ev(i, t); };
}

// Visibilité d'un contenu : entrée par ressort à tin, sortie courte à tout.
export function makeVis(T) {
  return function vis(t, tin, tout) {
    let best = { o: 0, p: 0, e: 1 };
    for (const tt of [t, t + T, t - T]) {
      const p = step(P.enter, tt - tin), k = clamp((tt - tout) / 0.14), e = k * k * (3 - 2 * k);
      const o = p * (1 - e);
      if (o > best.o) best = { o, p, e };
    }
    return best;
  };
}
