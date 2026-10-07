"""Outils côté client que l'agent peut appeler, en plus de la recherche web d'Anthropic."""

import json

import httpx

from . import config, db

COMPANY_API = "https://recherche-entreprises.api.gouv.fr/search"
PLACES_API = "https://places.googleapis.com/v1/places:searchText"
BOAMP_API = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records"

# Codes INSEE des tranches d'effectif salarié, pour des résultats lisibles.
EFFECTIFS = {
    "NN": "non renseigné", "00": "0 salarié", "01": "1-2", "02": "3-5", "03": "6-9",
    "11": "10-19", "12": "20-49", "21": "50-99", "22": "100-199", "31": "200-249",
    "32": "250-499", "41": "500-999", "42": "1000-1999", "51": "2000-4999",
    "52": "5000-9999", "53": "10000+",
}

SEARCH_COMPANIES = {
    "name": "search_french_companies",
    "description": (
        "Recherche des entreprises françaises actives dans l'annuaire officiel "
        "(recherche-entreprises.api.gouv.fr, données INSEE/RNE). Renvoie SIREN, adresse du siège, "
        "code NAF, tranche d'effectif, catégorie (PME/ETI/GE) et dirigeants. "
        "Utile pour trouver des entreprises par activité et zone, ou vérifier une entreprise "
        "repérée sur le web."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Mots-clés : nom, activité ou dirigeant."},
            "departement": {"type": "string", "description": "Code département, ex. '69'. Optionnel."},
            "code_postal": {"type": "string", "description": "Code postal, ex. '75011'. Optionnel."},
            "activite_principale": {
                "type": "string",
                "description": "Code NAF/APE, ex. '62.01Z'. Plusieurs codes séparés par des virgules. Optionnel.",
            },
            "tranche_effectif_salarie": {
                "type": "string",
                "description": (
                    "Codes INSEE séparés par des virgules : 01=1-2, 02=3-5, 03=6-9, 11=10-19, "
                    "12=20-49, 21=50-99, 22=100-199, 31=200-249, 32=250-499, 41=500-999. Optionnel."
                ),
            },
            "categorie_entreprise": {
                "type": "string",
                "enum": ["PME", "ETI", "GE"],
                "description": "Catégorie d'entreprise. Optionnel.",
            },
            "page": {"type": "integer", "description": "Page de résultats, à partir de 1."},
        },
        "required": ["query"],
    },
}

SEARCH_PLACES = {
    "name": "search_google_maps",
    "description": (
        "Recherche des établissements sur Google Maps (texte libre, ex. 'cabinet d'architecte Lyon'). "
        "Renvoie nom, adresse, site web, téléphone, note et nombre d'avis. "
        "Idéal pour les commerces et entreprises locales."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Recherche texte, avec la ville ou la zone."},
        },
        "required": ["query"],
    },
}

SAVE_LEAD = {
    "name": "save_lead",
    "description": (
        "Enregistre un lead qualifié dans la liste affichée à l'utilisateur. Appelle cet outil dès "
        "qu'un lead est suffisamment vérifié, un appel par entreprise. Rappeler l'outil pour la même "
        "entreprise (même SIREN ou même site) met le lead à jour."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "company_name": {"type": "string"},
            "website": {"type": "string", "description": "URL du site, ou chaîne vide."},
            "siren": {"type": "string", "description": "SIREN à 9 chiffres, ou chaîne vide."},
            "city": {"type": "string"},
            "sector": {"type": "string", "description": "Activité en quelques mots."},
            "company_size": {"type": "string", "description": "Effectif ou tranche, ou chaîne vide."},
            "contact_name": {"type": "string", "description": "Décideur identifié, ou chaîne vide."},
            "contact_role": {"type": "string", "description": "Poste du décideur, ou chaîne vide."},
            "linkedin_url": {
                "type": "string",
                "description": "Profil LinkedIn du décideur ou page entreprise trouvés via la recherche web, ou chaîne vide.",
            },
            "email": {
                "type": "string",
                "description": "Email publié publiquement par l'entreprise (jamais deviné), ou chaîne vide.",
            },
            "phone": {"type": "string", "description": "Téléphone public, ou chaîne vide."},
            "score": {
                "type": "integer",
                "description": "Pertinence 0-100 par rapport au profil cible (voir la grille de scoring).",
            },
            "score_reason": {"type": "string", "description": "Pourquoi ce score, en 1-3 phrases."},
            "signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Signaux d'achat concrets observés (recrutement, levée, ouverture, site daté…).",
            },
            "outreach_hook": {
                "type": "string",
                "description": "Accroche de premier message personnalisée, 1-2 phrases.",
            },
            "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs consultées."},
        },
        "required": [
            "company_name", "website", "siren", "city", "sector", "company_size",
            "contact_name", "contact_role", "linkedin_url", "email", "phone",
            "score", "score_reason", "signals", "outreach_hook", "sources",
        ],
    },
}


SEARCH_BOAMP = {
    "name": "search_boamp",
    "description": (
        "Recherche plein texte dans les avis de marchés publics du BOAMP (open data DILA), du plus "
        "récent au plus ancien. Renvoie pour chaque avis les champs courts disponibles (identifiant "
        "idweb, objet, acheteur, dates de parution et de limite de réponse, départements, type...). "
        "Lien d'un avis : https://www.boamp.fr/pages/avis/?q=idweb:<idweb>."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Mots-clés, ex. 'local vélos' ou 'garages préfabriqués'."},
            "offset": {"type": "integer", "description": "Décalage pour paginer (0, 20, 40...)."},
        },
        "required": ["query"],
    },
}

SAVE_TENDER = {
    "name": "save_tender",
    "description": (
        "Enregistre un appel d'offres pertinent dans la liste affichée à l'utilisateur. Un appel par "
        "avis ; rappeler l'outil pour la même référence ou URL met l'avis à jour."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string", "description": "Objet du marché."},
            "buyer": {"type": "string", "description": "Acheteur (maître d'ouvrage)."},
            "buyer_type": {"type": "string", "description": "Bailleur social, collectivité, État, entreprise, autre."},
            "location": {"type": "string", "description": "Ville et département."},
            "published": {"type": "string", "description": "Date de parution AAAA-MM-JJ, ou chaîne vide."},
            "deadline": {"type": "string", "description": "Date limite de réponse AAAA-MM-JJ, ou chaîne vide."},
            "status": {"type": "string", "enum": ["ouvert", "clos", "non vérifié"]},
            "scope": {"type": "string", "description": "Ce qui est demandé, 1-2 phrases."},
            "reference": {"type": "string", "description": "N° d'avis BOAMP ou référence, ou chaîne vide."},
            "url": {"type": "string", "description": "Lien vers l'avis."},
            "score": {"type": "integer", "description": "Pertinence 0-100 (voir la grille)."},
            "score_reason": {"type": "string", "description": "Pourquoi ce score, 1-2 phrases."},
            "sources": {"type": "array", "items": {"type": "string"}, "description": "URLs consultées."},
        },
        "required": [
            "title", "buyer", "buyer_type", "location", "published", "deadline", "status",
            "scope", "reference", "url", "score", "score_reason", "sources",
        ],
    },
}


def client_tools(kind: str = "leads") -> list[dict]:
    if kind == "tenders":
        return [SEARCH_BOAMP, SEARCH_COMPANIES, SAVE_TENDER]
    tools = [SEARCH_COMPANIES]
    if config.GOOGLE_MAPS_API_KEY:
        tools.append(SEARCH_PLACES)
    tools.append(SAVE_LEAD)
    return tools


def search_french_companies(args: dict, http: httpx.Client) -> list[dict]:
    params = {"q": args["query"], "per_page": 15, "page": args.get("page") or 1, "etat_administratif": "A"}
    for key in ("departement", "code_postal", "activite_principale", "tranche_effectif_salarie", "categorie_entreprise"):
        if args.get(key):
            params[key] = args[key]
    response = http.get(COMPANY_API, params=params, timeout=20)
    response.raise_for_status()
    results = []
    for item in response.json().get("results", []):
        siege = item.get("siege") or {}
        dirigeants = [
            " ".join(filter(None, [d.get("prenoms"), d.get("nom"), f"({d['qualite']})" if d.get("qualite") else None]))
            if d.get("type_personne") == "personne physique"
            else d.get("denomination", "")
            for d in (item.get("dirigeants") or [])[:4]
        ]
        results.append({
            "nom": item.get("nom_complet"),
            "siren": item.get("siren"),
            "adresse": siege.get("adresse"),
            "ville": siege.get("libelle_commune"),
            "naf": item.get("activite_principale"),
            "effectif": EFFECTIFS.get(item.get("tranche_effectif_salarie") or "NN", item.get("tranche_effectif_salarie")),
            "categorie": item.get("categorie_entreprise"),
            "creation": item.get("date_creation"),
            "dirigeants": dirigeants,
        })
    return results


def search_google_maps(args: dict, http: httpx.Client) -> list[dict]:
    response = http.post(
        PLACES_API,
        headers={
            "X-Goog-Api-Key": config.GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,places.websiteUri,"
                "places.nationalPhoneNumber,places.rating,places.userRatingCount,places.googleMapsUri"
            ),
        },
        json={"textQuery": args["query"], "languageCode": "fr", "regionCode": "FR", "pageSize": 20},
        timeout=20,
    )
    response.raise_for_status()
    return [
        {
            "nom": (p.get("displayName") or {}).get("text"),
            "adresse": p.get("formattedAddress"),
            "site": p.get("websiteUri"),
            "telephone": p.get("nationalPhoneNumber"),
            "note": p.get("rating"),
            "avis": p.get("userRatingCount"),
            "maps": p.get("googleMapsUri"),
        }
        for p in response.json().get("places", [])
    ]


def _short_fields(record: dict) -> dict:
    """Garde les champs courts d'un avis (les champs volumineux comme le détail JSON sont omis)."""
    kept = {}
    for key, value in record.items():
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value if isinstance(v, (str, int, float)))
        if isinstance(value, (str, int, float)) and value != "" and len(str(value)) <= 400:
            kept[key] = value
    return kept


def search_boamp(args: dict, http: httpx.Client) -> list[dict]:
    query = args["query"].replace('"', " ")
    params = {
        "where": f'search("{query}")',
        "order_by": "dateparution desc",
        "limit": 20,
        "offset": int(args.get("offset") or 0),
    }
    response = http.get(BOAMP_API, params=params, timeout=30)
    if response.status_code == 400:
        # Champ de tri inconnu selon la version du jeu de données : on retente sans tri.
        params.pop("order_by")
        response = http.get(BOAMP_API, params=params, timeout=30)
    response.raise_for_status()
    return [_short_fields(r) for r in response.json().get("results", [])]


def run_tool(name: str, args: dict, search_id: int, http: httpx.Client) -> tuple[str, bool]:
    """Exécute un outil client. Renvoie (contenu du tool_result, is_error)."""
    try:
        if name == "search_french_companies":
            results = search_french_companies(args, http)
            db.log_event(search_id, f"Annuaire entreprises : « {args['query']} » → {len(results)} résultats")
            return json.dumps(results, ensure_ascii=False), False
        if name == "search_google_maps":
            results = search_google_maps(args, http)
            db.log_event(search_id, f"Google Maps : « {args['query']} » → {len(results)} résultats")
            return json.dumps(results, ensure_ascii=False), False
        if name == "search_boamp":
            results = search_boamp(args, http)
            db.log_event(search_id, f"BOAMP : « {args['query']} » → {len(results)} avis")
            return json.dumps(results, ensure_ascii=False), False
        if name == "save_tender":
            tender = {**args, "kind": "tender", "score": max(0, min(100, int(args["score"])))}
            is_new = db.save_lead(search_id, tender)
            verb = "ajouté" if is_new else "mis à jour"
            db.log_event(search_id, f"Appel d'offres {verb} : {tender['title'][:80]} ({tender['score']}/100)")
            return f"Avis {verb}. Total : {db.count_leads(search_id)} avis.", False
        if name == "save_lead":
            lead = {**args, "score": max(0, min(100, int(args["score"])))}
            is_new = db.save_lead(search_id, lead)
            verb = "ajouté" if is_new else "mis à jour"
            db.log_event(search_id, f"Lead {verb} : {lead['company_name']} ({lead['score']}/100)")
            return f"Lead {verb}. Total : {db.count_leads(search_id)} leads.", False
        return f"Outil inconnu : {name}", True
    except httpx.HTTPError as exc:
        db.log_event(search_id, f"Erreur outil {name} : {exc}")
        return f"Erreur réseau ou API pour {name} : {exc}", True
    except (KeyError, ValueError, TypeError) as exc:
        return f"Paramètres invalides pour {name} : {exc}", True
