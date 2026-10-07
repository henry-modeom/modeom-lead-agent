"""Boucle de l'agent de recherche de leads (API Claude + outils)."""

from datetime import date

import anthropic
import httpx

from . import config, db, tools

SYSTEM_PROMPT = """Tu es l'agent de prospection B2B de Modeom. Ta mission : trouver des entreprises \
réelles qui correspondent au profil cible fourni, identifier pour chacune le bon décideur, \
puis enregistrer chaque lead avec l'outil save_lead, avec un score de pertinence justifié.

Méthode :
1. Pars du profil cible et varie les angles : recherche web (annuaires sectoriels, articles de \
presse locale, offres d'emploi, salons, classements, appels d'offres publics comme le BOAMP, \
annonces de permis de construire et de programmes immobiliers), annuaire officiel des entreprises \
françaises, et Google Maps s'il est disponible pour les entreprises locales.
2. Vérifie chaque entreprise : qu'elle existe et est active (SIREN via l'annuaire quand c'est une \
entreprise française), son site, sa taille, son activité réelle.
3. Trouve le décideur correspondant aux postes visés. Pour LinkedIn, utilise la recherche web \
(ex. « site:linkedin.com/in directeur marketing NomEntreprise » ou \
« site:linkedin.com/company NomEntreprise ») et reporte l'URL trouvée dans les résultats. \
Ne tente jamais d'ouvrir ou d'extraire des pages LinkedIn. Les dirigeants listés par \
l'annuaire officiel sont une bonne piste pour les petites structures.
4. Repère des signaux d'achat concrets et datés : recrutement en cours, levée de fonds, \
ouverture d'un site, nouveau dirigeant, site web vieillissant, avis clients, actualité récente.
5. Enregistre le lead avec save_lead dès qu'il est vérifié, sans attendre la fin de la recherche.

Grille de scoring (0-100) :
- Adéquation au profil (secteur, taille, zone) : jusqu'à 40 points.
- Décideur identifié avec nom et poste : jusqu'à 20 points.
- Signaux d'achat récents et concrets : jusqu'à 30 points.
- Facilité de contact (site, téléphone, LinkedIn, email public) : jusqu'à 10 points.
Sois exigeant : un lead moyen tourne autour de 50. N'enregistre pas les entreprises sous 30 \
ni celles qui correspondent à une exclusion.

Règles :
- N'invente jamais une entreprise, une personne, un email ou une URL. Un champ inconnu reste vide.
- Ne note que des emails publiés par l'entreprise elle-même (page contact, mentions légales) ; \
ne devine pas d'adresse nominative.
- Une entreprise = un lead. Pas de doublons.
- L'accroche (outreach_hook) s'appuie sur un fait précis concernant l'entreprise et relie ce \
fait à l'offre de Modeom.
- Quand tu as atteint le nombre de leads demandé ou épuisé les pistes sérieuses, termine par \
un court bilan en français : nombre de leads, angles explorés, pistes à creuser ensuite."""


TENDER_PROMPT = """Tu es l'agent de veille marchés publics de Modeom. Ta mission : recenser les \
appels d'offres et consultations qui correspondent à l'offre de Modeom, puis enregistrer chacun \
avec l'outil save_tender, avec un score de pertinence justifié.

Méthode :
1. Interroge le BOAMP avec search_boamp en variant les mots-clés : produits de Modeom, synonymes \
(« abri vélos », « stationnement vélos », « local ordures ménagères », « abri conteneurs », \
« garages », « boxes », « construction modulaire », « résidentialisation »...) et lots de marchés \
plus larges (réhabilitation, VRD, aménagements extérieurs) qui peuvent inclure ces ouvrages.
2. Complète par la recherche web : plateformes de marchés publics des bailleurs et collectivités, \
marches-publics.info, achatpublic.com, e-marchespublics.com, marchesonline.com, TED. \
Si search_boamp échoue, passe entièrement par la recherche web.
3. Pour chaque avis, vérifie l'objet, l'acheteur, la localisation, la date limite de réponse et si \
l'avis est encore ouvert à la date du jour. L'annuaire officiel des entreprises peut aider à \
qualifier l'acheteur.
4. Enregistre chaque avis pertinent avec save_tender dès qu'il est vérifié.

Grille de scoring (0-100) :
- Adéquation directe avec les produits de Modeom : jusqu'à 50 points.
- Zone prioritaire du profil : jusqu'à 20 points.
- Délai de réponse encore ouvert, avec assez de temps pour répondre : jusqu'à 20 points.
- Clarté de l'avis (montant, lots, documents accessibles) : jusqu'à 10 points.
N'enregistre pas les avis sous 30, ni les avis clos depuis plus de 3 mois.

Règles :
- N'invente jamais un avis, une date, une référence ou une URL. Un champ inconnu reste vide et le \
statut est « non vérifié ».
- Un avis = une entrée. Pas de doublons entre BOAMP et les autres plateformes.
- Quand tu as atteint le nombre d'avis demandé ou épuisé les pistes, termine par un court bilan \
en français : nombre d'avis, avis à traiter en priorité, mots-clés à surveiller ensuite."""


def build_brief(profile: dict) -> str:
    if profile.get("kind") == "tenders":
        labels = [
            ("offer", "Ce que Modeom vend"),
            ("target", "Acheteurs visés"),
            ("locations", "Zones géographiques"),
            ("keywords", "Mots-clés à surveiller"),
            ("exclusions", "Exclusions"),
        ]
        lines = [f"- {label} : {profile[key].strip()}" for key, label in labels if (profile.get(key) or "").strip()]
        count = int(profile.get("lead_count") or 15)
        return (
            f"Date du jour : {date.today().isoformat()}.\n"
            "Profil de veille pour cette recherche :\n"
            + "\n".join(lines)
            + f"\n\nObjectif : recenser jusqu'à {count} appels d'offres pertinents, enregistrés avec save_tender."
        )

    labels = [
        ("offer", "Ce que Modeom vend"),
        ("target", "Client idéal"),
        ("sectors", "Secteurs visés"),
        ("locations", "Zones géographiques"),
        ("company_sizes", "Taille d'entreprise"),
        ("decision_makers", "Décideurs à identifier"),
        ("signals", "Signaux d'achat à privilégier"),
        ("exclusions", "Exclusions"),
    ]
    lines = [f"- {label} : {profile[key].strip()}" for key, label in labels if (profile.get(key) or "").strip()]
    count = int(profile.get("lead_count") or 15)
    return (
        "Profil cible pour cette recherche :\n"
        + "\n".join(lines)
        + f"\n\nObjectif : {count} leads qualifiés, enregistrés avec save_lead."
    )


def web_search_tool() -> dict:
    return {
        "type": "web_search_20260209",
        "name": "web_search",
        "max_uses": config.MAX_WEB_SEARCHES,
        "user_location": {"type": "approximate", "country": "FR"},
    }


def run_search(search_id: int, profile: dict, client: anthropic.Anthropic | None = None,
               http: httpx.Client | None = None) -> None:
    """Exécute une recherche complète et enregistre son statut final en base."""
    client = client or anthropic.Anthropic()
    owns_http = http is None
    http = http or httpx.Client()
    target = int(profile.get("lead_count") or 15)
    kind = profile.get("kind") or "leads"
    system = TENDER_PROMPT if kind == "tenders" else SYSTEM_PROMPT
    noun = "appels d'offres" if kind == "tenders" else "leads"
    messages: list = [{"role": "user", "content": build_brief(profile)}]
    all_tools = [web_search_tool(), *tools.client_tools(kind)]
    nudged = False
    db.log_event(search_id, "Recherche démarrée")
    try:
        for _ in range(config.MAX_TURNS):
            response = client.beta.messages.create(
                model=config.MODEL,
                max_tokens=16000,
                system=system,
                tools=all_tools,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": config.EFFORT},
                cache_control={"type": "ephemeral"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            if response.stop_reason == "refusal":
                raise RuntimeError("Le modèle a refusé la requête. Reformulez le profil cible.")

            messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if block.type == "server_tool_use" and block.name == "web_search":
                    db.log_event(search_id, f"Recherche web : « {block.input.get('query', '')} »")

            if response.stop_reason == "pause_turn":
                # Boucle de recherche web côté serveur interrompue : on renvoie tel quel pour reprendre.
                continue

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if tool_uses:
                results = []
                for block in tool_uses:
                    content, is_error = tools.run_tool(block.name, block.input, search_id, http)
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                        "is_error": is_error,
                    })
                messages.append({"role": "user", "content": results})
                continue

            if response.stop_reason == "max_tokens":
                messages.append({"role": "user", "content": "Poursuis là où tu t'es arrêté."})
                continue

            found = db.count_leads(search_id)
            if found < target and not nudged:
                nudged = True
                messages.append({
                    "role": "user",
                    "content": (
                        f"Tu as enregistré {found} {noun} sur les {target} demandés. Explore d'autres "
                        "angles (autres mots-clés, autres départements de la zone, autres sources) "
                        "avant de conclure, sauf si les pistes sérieuses sont vraiment épuisées."
                    ),
                })
                continue

            summary = "\n".join(b.text for b in response.content if b.type == "text").strip()
            db.finish_search(search_id, "done", summary=summary)
            db.log_event(search_id, f"Recherche terminée : {found} {noun}")
            return

        found = db.count_leads(search_id)
        db.finish_search(search_id, "done", summary=f"Limite de {config.MAX_TURNS} tours atteinte ({found} {noun}).")
        db.log_event(search_id, "Limite de tours atteinte")
    except Exception as exc:  # noqa: BLE001 - toute erreur doit être visible dans l'interface
        db.finish_search(search_id, "error", error=str(exc))
        db.log_event(search_id, f"Erreur : {exc}")
    finally:
        if owns_http:
            http.close()
