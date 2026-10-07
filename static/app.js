const form = document.getElementById("profile-form");
const submitBtn = document.getElementById("submit-btn");
const historyEl = document.getElementById("history");
const leadsEl = document.getElementById("leads");
const minScore = document.getElementById("min-score");
const PROFILE_KEY = "modeom-lead-profile";
const STATUS_LABELS = { running: "En cours…", done: "Terminée", error: "Erreur" };

let currentId = null;
let pollTimer = null;
let currentLeads = [];

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

function el(tag, attrs = {}, text = "") {
  const node = document.createElement(tag);
  Object.assign(node, attrs);
  if (text) node.textContent = text;
  return node;
}

function safeUrl(url) {
  if (!url) return "";
  const full = /^https?:\/\//i.test(url) ? url : `https://${url}`;
  try { return new URL(full).protocol.startsWith("http") ? full : ""; } catch { return ""; }
}

// Profil par défaut, d'après modeom.fr : garages préfabriqués en béton (Chaponnay, 69).
const DEFAULT_PROFILE = {
  offer: "Modules préfabriqués monocoques en béton armé, livrés et posés clés en main : garages "
    + "(individuels, doubles, en batterie), abris vélos, locaux poubelles, locaux techniques. "
    + "25 % moins chers qu'une construction traditionnelle, pose rapide, zéro déchet sur chantier.",
  target: "Professionnels de l'immobilier qui doivent livrer des garages ou des annexes sur leurs "
    + "programmes ou leur patrimoine : promoteurs, bailleurs sociaux, investisseurs, syndics de copropriété.",
  sectors: "Promotion immobilière, bailleurs sociaux (OPH, ESH), investisseurs immobiliers, syndics, "
    + "lotisseurs, constructeurs de maisons individuelles, collectivités",
  locations: "Auvergne-Rhône-Alpes en priorité (Rhône, Isère, Ain, Loire), puis grand quart sud-est",
  company_sizes: "Toutes tailles, à partir de 5 salariés",
  decision_makers: "Directeur de programmes, responsable technique, directeur du patrimoine, "
    + "responsable maintenance, chargé d'opérations, gérant",
  signals: "Permis de construire ou programme de logements annoncé, appel d'offres pour garages, "
    + "locaux vélos ou locaux poubelles, réhabilitation de résidence, lotissement en commercialisation, "
    + "obligation de stationnement vélo",
  exclusions: "Fabricants concurrents de garages préfabriqués ou de modules béton, particuliers",
  lead_count: 15,
};

// Profil : mémorisé dans le navigateur pour ne pas le ressaisir.
function restoreProfile() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(PROFILE_KEY) || "{}"); } catch { /* stockage indisponible */ }
  for (const [key, value] of Object.entries({ ...DEFAULT_PROFILE, ...saved })) {
    if (form.elements[key]) form.elements[key].value = value;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const profile = Object.fromEntries(new FormData(form));
  profile.lead_count = Number(profile.lead_count) || 15;
  try { localStorage.setItem(PROFILE_KEY, JSON.stringify(profile)); } catch { /* ignoré */ }
  submitBtn.disabled = true;
  try {
    const { id } = await api("/api/searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    });
    await loadHistory();
    openSearch(id);
  } catch (err) {
    alert(`Impossible de lancer la recherche : ${err.message}`);
  } finally {
    submitBtn.disabled = false;
  }
});

async function loadHistory() {
  const searches = await api("/api/searches");
  historyEl.replaceChildren(...searches.map((s) => {
    const li = el("li");
    li.classList.toggle("active", s.id === currentId);
    li.append(
      el("span", { className: "h-title", title: s.profile.target }, `#${s.id} · ${s.profile.target}`),
      el("span", { className: "h-count" }, s.status === "running" ? "…" : `${s.lead_count} leads`),
    );
    li.addEventListener("click", () => openSearch(s.id));
    return li;
  }));
  if (!searches.length) historyEl.append(el("li", {}, "Aucune recherche pour l'instant."));
}

function openSearch(id) {
  currentId = id;
  clearTimeout(pollTimer);
  document.getElementById("empty").hidden = true;
  document.getElementById("search-view").hidden = false;
  document.getElementById("export-link").href = `/api/searches/${id}/leads.csv`;
  for (const li of historyEl.children) li.classList.remove("active");
  refresh();
}

async function refresh() {
  const id = currentId;
  const [search, leads] = await Promise.all([
    api(`/api/searches/${id}`),
    api(`/api/searches/${id}/leads`),
  ]);
  if (id !== currentId) return;

  document.getElementById("search-title").textContent = `#${search.id} · ${search.profile.target}`;
  const badge = document.getElementById("search-status");
  badge.textContent = `${STATUS_LABELS[search.status] || search.status} · ${leads.length} leads`;
  badge.className = `badge ${search.status}`;
  document.getElementById("summary").textContent = search.error || search.summary || "";
  document.getElementById("events").replaceChildren(
    ...search.events.map((e) => el("li", {}, `${e.created_at.slice(11, 19)} — ${e.message}`)),
  );

  currentLeads = leads;
  renderLeads();

  if (search.status === "running") {
    pollTimer = setTimeout(refresh, 3000);
  } else {
    loadHistory();
  }
}

function renderLeads() {
  const threshold = Number(minScore.value);
  const template = document.getElementById("lead-template");
  const visible = currentLeads.filter((l) => l.score >= threshold);
  leadsEl.replaceChildren(...visible.map((lead) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const score = node.querySelector(".score");
    score.textContent = lead.score;
    score.classList.add(lead.score >= 70 ? "high" : lead.score >= 50 ? "mid" : "low");
    node.querySelector(".company").textContent = lead.company_name;
    node.querySelector(".tags").textContent = [lead.sector, lead.city, lead.company_size]
      .filter(Boolean).join(" · ");
    node.querySelector(".contact").textContent = [lead.contact_name, lead.contact_role]
      .filter(Boolean).join(" — ");
    node.querySelector(".reason").textContent = lead.score_reason;
    node.querySelector(".signals").replaceChildren(...(lead.signals || []).map((s) => el("li", {}, s)));
    node.querySelector(".hook").textContent = lead.outreach_hook;

    const links = node.querySelector(".links");
    const addLink = (label, href) => {
      if (href) links.append(el("a", { href, target: "_blank", rel: "noopener" }, label));
    };
    addLink("Site web", safeUrl(lead.website));
    addLink("LinkedIn", safeUrl(lead.linkedin_url));
    if (lead.email) addLink(lead.email, `mailto:${lead.email}`);
    if (lead.phone) addLink(lead.phone, `tel:${lead.phone.replace(/\s/g, "")}`);
    if (lead.siren) addLink(`SIREN ${lead.siren}`, `https://annuaire-entreprises.data.gouv.fr/entreprise/${encodeURIComponent(lead.siren)}`);
    (lead.sources || []).slice(0, 3).forEach((src, i) => addLink(`Source ${i + 1}`, safeUrl(src)));
    return node;
  }));
  if (!visible.length) {
    leadsEl.append(el("p", { className: "empty card" },
      currentLeads.length ? "Aucun lead au-dessus de ce score." : "L'agent cherche… les premiers leads arrivent dans quelques minutes."));
  }
}

minScore.addEventListener("input", () => {
  document.getElementById("min-score-value").textContent = minScore.value;
  renderLeads();
});

async function init() {
  restoreProfile();
  try {
    const cfg = await api("/api/config");
    document.getElementById("meta").textContent =
      `Modèle ${cfg.model} · Google Maps ${cfg.google_maps ? "activé" : "désactivé"}`;
  } catch { /* non bloquant */ }
  await loadHistory();
}

init();
