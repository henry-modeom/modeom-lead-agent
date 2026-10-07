# Modeom · Agent de recherche de leads

Agent IA (API Claude) qui trouve des entreprises correspondant à votre profil cible, identifie le
décideur, repère des signaux d'achat et attribue à chaque lead un score de pertinence sur 100.
Les résultats s'affichent dans une interface web, classés par score, et s'exportent en CSV.

## Sources utilisées

| Source | Usage | Configuration |
|---|---|---|
| Recherche web (outil `web_search` de Claude) | Presse, annuaires sectoriels, offres d'emploi, sites des entreprises | Incluse avec la clé Anthropic |
| LinkedIn | URLs des profils et pages entreprises trouvées **via la recherche web** (`site:linkedin.com/in …`) | Rien à configurer |
| Annuaire officiel des entreprises (recherche-entreprises.api.gouv.fr) | SIREN, effectif, code NAF, dirigeants | API publique, sans clé |
| Google Maps (Places API) | Entreprises et commerces locaux, téléphone, avis | `GOOGLE_MAPS_API_KEY` (optionnel) |

L'agent ne se connecte pas à LinkedIn et n'en extrait pas les pages : les conditions d'utilisation
de LinkedIn l'interdisent et les comptes concernés risquent d'être bannis. Il relève seulement les
URLs publiques qui apparaissent dans les résultats de recherche.

## Installation

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis renseignez ANTHROPIC_API_KEY (et GOOGLE_MAPS_API_KEY si besoin)
uvicorn app.main:app --reload
```

Ouvrez ensuite <http://localhost:8000>.

## Mise en ligne (sans rien installer)

L'application peut tourner sur [Render](https://render.com), et s'ouvre alors depuis n'importe quel
navigateur, téléphone compris.

1. Créez un compte Render et connectez-le à GitHub, avec accès au dépôt `modeom-lead-agent`.
2. Dans Render : **New → Blueprint**, choisissez ce dépôt. Render lit `render.yaml`.
3. Renseignez les variables demandées :
   - `ANTHROPIC_API_KEY` : votre clé Claude ;
   - `APP_PASSWORD` : le mot de passe de l'interface (obligatoire, sinon n'importe qui pourrait
     lancer des recherches à vos frais) ;
   - `GOOGLE_MAPS_API_KEY` : facultatif, laissez vide sinon.
4. Validez. Après quelques minutes, Render affiche l'adresse du site (`https://modeom-leads-….onrender.com`).
   À l'ouverture, le navigateur demande un identifiant (n'importe lequel) et le mot de passe.

Le plan « Starter » de Render (environ 7 $/mois) est nécessaire pour le disque qui conserve les leads
entre deux redémarrages.

## Utilisation

Le formulaire est pré-rempli avec le profil de Modeom, établi d'après modeom.fr : modules préfabriqués en
béton (garages, abris vélos, locaux poubelles, locaux techniques) pour promoteurs, bailleurs sociaux,
investisseurs et syndics, avec Auvergne-Rhône-Alpes en priorité. Modifiez-le librement : le profil
saisi est mémorisé par le navigateur. Le profil par défaut se trouve dans `static/app.js`
(`DEFAULT_PROFILE`).

1. Décrivez à gauche ce que Modeom vend et votre client idéal. Secteurs, zones, taille, décideurs,
   signaux et exclusions sont facultatifs mais affinent nettement les résultats. Le navigateur
   mémorise le profil saisi.
2. Lancez la recherche. Elle dure en général 5 à 15 minutes pour 15 leads. Les leads apparaissent
   au fil de l'eau et le journal de l'agent montre les requêtes effectuées.
3. Filtrez par score minimum, puis exportez en CSV (séparateur `;`, s'ouvre directement dans Excel).

### Grille de scoring

- Adéquation au profil (secteur, taille, zone) : 40 points
- Décideur identifié : 20 points
- Signaux d'achat récents et concrets : 30 points
- Facilité de contact : 10 points

Les leads sous 30 ne sont pas enregistrés. La grille se modifie dans `SYSTEM_PROMPT`
(`app/agent.py`).

## Coût

Une recherche de 15 leads consomme typiquement quelques dizaines d'appels au modèle et de
recherches web. Comptez de l'ordre de 1 à 4 € par recherche avec le réglage par défaut
(`LEAD_AGENT_EFFORT=medium`). Pour réduire le coût, baissez `LEAD_AGENT_MAX_WEB_SEARCHES`,
`LEAD_AGENT_MAX_TURNS` ou le nombre de leads demandés. Suivez la consommation réelle dans la
console Anthropic.

## Architecture

```
app/agent.py   boucle de l'agent : appels à l'API Claude, outils, reprise, relance si objectif non atteint
app/tools.py   outils clients : annuaire entreprises, Google Maps, enregistrement des leads
app/db.py      stockage SQLite (recherches, journal, leads dédoublonnés par SIREN / site)
app/main.py    API FastAPI + export CSV ; chaque recherche tourne dans un thread
static/        interface web (HTML/CSS/JS sans dépendance)
```

## Tests

```bash
pytest
```

Les tests simulent l'API Claude et les API externes : ils ne consomment rien.

## Conformité (RGPD)

La prospection B2B par email est autorisée en France si le message concerne l'activité
professionnelle du destinataire et propose un moyen simple de se désinscrire. Conservez la source
de chaque donnée (colonne « Sources ») et supprimez les leads qui le demandent.
