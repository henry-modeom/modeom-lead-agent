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
let currentKind = "leads";

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

// Profils par défaut, d'après modeom.fr : modules préfabriqués en béton (Chaponnay, 69).
const OFFER = "Modules préfabriqués monocoques en béton armé, livrés et posés clés en main : garages "
  + "(individuels, doubles, en batterie), boxes, abris vélos, locaux poubelles, locaux techniques. "
  + "25 % moins chers qu'une construction traditionnelle, pose rapide, zéro déchet sur chantier.";
const DEFAULT_PROFILES = {
  leads: {
    offer: OFFER,
    target: "Maîtres d'ouvrage et acteurs de la construction qui doivent livrer des garages ou des annexes : "
      + "bailleurs sociaux, promoteurs, entreprises de construction, architectes et autres maîtres d'ouvrage.",
    sectors: "Bailleurs sociaux (OPH, ESH, SEM), promoteurs immobiliers, entreprises générales et de gros œuvre, "
      + "cabinets d'architectes, maîtres d'ouvrage publics et privés (collectivités, syndics, investisseurs), "
      + "lotisseurs, constructeurs de maisons individuelles",
    locations: "Auvergne-Rhône-Alpes en priorité (Rhône, Isère, Ain, Loire), puis grand quart sud-est",
    company_sizes: "Toutes tailles, à partir de 5 salariés",
    decision_makers: "Directeur du patrimoine, directeur de programmes, chargé d'opérations, directeur "
      + "technique, conducteur de travaux principal, responsable achats, architecte associé, gérant",
    signals: "Programme de logements ou permis de construire annoncé, chantier remporté, appel d'offres "
      + "pour garages, locaux vélos ou locaux poubelles, réhabilitation ou résidentialisation, "
      + "lotissement en commercialisation, concours d'architecture gagné",
    exclusions: "Fabricants concurrents de garages préfabriqués ou de modules béton, particuliers",
    lead_count: 15,
  },
  tenders: {
    offer: OFFER,
    target: "Bailleurs sociaux, collectivités, établissements publics, maîtres d'ouvrage publics et privés",
    locations: "Auvergne-Rhône-Alpes en priorité, puis toute la France",
    keywords: "garages préfabriqués, boxes, local vélos, abri vélos, stationnement vélos, local poubelles, "
      + "local ordures ménagères, abri conteneurs, local technique préfabriqué, construction modulaire, "
      + "résidentialisation",
    exclusions: "Avis clos depuis plus de 3 mois",
    lead_count: 20,
  },
};
const MODE_TEXT = {
  leads: { title: "Profil cible", target: "Client idéal", count: "Nombre de leads", noun: "leads" },
  tenders: { title: "Veille appels d'offres", target: "Acheteurs visés", count: "Nombre d'avis", noun: "avis" },
};

function profileKey(kind) { return `${PROFILE_KEY}-${kind}`; }

// Profil : mémorisé dans le navigateur, un par type de recherche, pour ne pas le ressaisir.
function setMode(kind) {
  form.elements.kind.value = kind;
  for (const tab of form.querySelectorAll(".mode-switch button")) {
    tab.setAttribute("aria-selected", String(tab.dataset.kind === kind));
  }
  for (const field of form.querySelectorAll("[data-mode]")) field.hidden = field.dataset.mode !== kind;
  document.getElementById("form-title").textContent = MODE_TEXT[kind].title;
  document.getElementById("target-label").textContent = MODE_TEXT[kind].target;
  document.getElementById("count-label").textContent = MODE_TEXT[kind].count;
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(profileKey(kind)) || "{}"); } catch { /* stockage indisponible */ }
  for (const [key, value] of Object.entries({ ...DEFAULT_PROFILES[kind], ...saved })) {
    if (form.elements[key] && key !== "kind") form.elements[key].value = value;
  }
  try { localStorage.setItem(`${PROFILE_KEY}-mode`, kind); } catch { /* ignoré */ }
}

for (const tab of form.querySelectorAll(".mode-switch button")) {
  tab.addEventListener("click", () => setMode(tab.dataset.kind));
}

function restoreProfile() {
  let kind = "leads";
  try { kind = localStorage.getItem(`${PROFILE_KEY}-mode`) === "tenders" ? "tenders" : "leads"; } catch { /* ignoré */ }
  setMode(kind);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const kind = form.elements.kind.value;
  const profile = {};
  for (const [key, value] of new FormData(form)) {
    const field = form.elements[key].closest("[data-mode]");
    if (!field || field.dataset.mode === kind) profile[key] = value;
  }
  profile.lead_count = Number(profile.lead_count) || 15;
  try { localStorage.setItem(profileKey(kind), JSON.stringify(profile)); } catch { /* ignoré */ }
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
    document.getElementById("empty").hidden = false;
    document.getElementById("empty").querySelector("p").textContent =
      `Impossible de lancer la recherche : ${err.message}. Vérifiez que le serveur tourne et que la clé API est renseignée.`;
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
      el("span", { className: "h-title", title: s.profile.target }, `#${s.id} · ${s.profile.kind === "tenders" ? "AO · " : ""}${s.profile.target}`),
      el("span", { className: "h-count" }, s.status === "running" ? "…" : `${s.lead_count} ${MODE_TEXT[s.profile.kind || "leads"].noun}`),
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

  currentKind = search.profile.kind || "leads";
  const kindLabel = currentKind === "tenders" ? "Appels d'offres · " : "";
  document.getElementById("search-title").textContent = `#${search.id} · ${kindLabel}${search.profile.target}`;
  const badge = document.getElementById("search-status");
  badge.textContent = `${STATUS_LABELS[search.status] || search.status} · ${leads.length} ${MODE_TEXT[currentKind].noun}`;
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
    if (currentKind === "tenders") return renderTender(lead, template);
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
      currentLeads.length ? "Aucun résultat au-dessus de ce score." : "L'agent cherche… les premiers résultats arrivent dans quelques minutes."));
  }
}

function daysUntil(isoDate) {
  const deadline = new Date(`${isoDate}T23:59:59`);
  if (Number.isNaN(deadline.getTime())) return null;
  return Math.ceil((deadline - new Date()) / 86400000);
}

function renderTender(tender, template) {
  const node = template.content.firstElementChild.cloneNode(true);
  const score = node.querySelector(".score");
  score.textContent = tender.score;
  score.classList.add(tender.score >= 70 ? "high" : tender.score >= 50 ? "mid" : "low");
  node.querySelector(".company").textContent = tender.title;
  node.querySelector(".tags").textContent = [tender.buyer, tender.buyer_type, tender.location]
    .filter(Boolean).join(" · ");

  const contact = node.querySelector(".contact");
  const days = tender.deadline ? daysUntil(tender.deadline) : null;
  const deadline = el("span", { className: "deadline" });
  if (tender.deadline) {
    const date = new Date(`${tender.deadline}T12:00:00`).toLocaleDateString("fr-FR");
    deadline.textContent = days === null ? `Date limite : ${tender.deadline}`
      : days < 0 ? `Date limite passée : ${date}` : `Date limite : ${date} (J-${days})`;
    if (days !== null && days < 0) deadline.classList.add("closed");
    else if (days !== null && days <= 10) deadline.classList.add("soon");
  } else {
    deadline.textContent = "Date limite non trouvée";
  }
  contact.append(deadline, el("span", { className: `status-pill ${tender.status === "ouvert" ? "ouvert" : tender.status === "clos" ? "clos" : ""}` }, tender.status));
  if (tender.published) {
    contact.append(` · publié le ${new Date(`${tender.published}T12:00:00`).toLocaleDateString("fr-FR")}`);
  }

  node.querySelector(".reason").textContent = tender.score_reason;
  node.querySelector(".hook").textContent = tender.scope;
  const links = node.querySelector(".links");
  const addLink = (label, href) => {
    if (href) links.append(el("a", { href, target: "_blank", rel: "noopener" }, label));
  };
  addLink("Voir l'avis", safeUrl(tender.url));
  if (tender.reference) links.append(el("span", {}, `Réf. ${tender.reference}`));
  (tender.sources || []).filter((src) => src !== tender.url).slice(0, 2)
    .forEach((src, i) => addLink(`Source ${i + 1}`, safeUrl(src)));
  return node;
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
