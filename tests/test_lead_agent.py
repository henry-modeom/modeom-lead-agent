from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from app import agent, config, db, main, tools


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "")
    monkeypatch.setattr(config, "APP_PASSWORD", "")
    db.init()


PROFILE = {"offer": "Sites web pour PME", "target": "PME du BTP à Lyon", "lead_count": 1}

LEAD = {
    "company_name": "Bâti Rhône", "website": "https://batirhone.fr", "siren": "123456789",
    "city": "Lyon", "sector": "BTP", "company_size": "20-49", "contact_name": "Jeanne Martin",
    "contact_role": "Gérante", "linkedin_url": "", "email": "", "phone": "", "score": 82,
    "score_reason": "Cible exacte", "signals": ["Recrute 2 chefs de chantier"],
    "outreach_hook": "Bravo pour les recrutements !", "sources": ["https://batirhone.fr"],
}


def company_api(request: httpx.Request) -> httpx.Response:
    assert request.url.params["departement"] == "69"
    return httpx.Response(200, json={"results": [{
        "nom_complet": "BATI RHONE", "siren": "123456789", "activite_principale": "41.20A",
        "tranche_effectif_salarie": "12", "categorie_entreprise": "PME", "date_creation": "2010-01-01",
        "siege": {"adresse": "1 rue X 69001 LYON", "libelle_commune": "LYON"},
        "dirigeants": [{"type_personne": "personne physique", "prenoms": "Jeanne", "nom": "MARTIN", "qualite": "Gérant"}],
    }]})


def test_search_companies_formats_results():
    http = httpx.Client(transport=httpx.MockTransport(company_api))
    results = tools.search_french_companies({"query": "btp", "departement": "69"}, http)
    assert results[0]["siren"] == "123456789"
    assert results[0]["effectif"] == "20-49"
    assert results[0]["dirigeants"] == ["Jeanne MARTIN (Gérant)"]


def test_save_lead_dedupes_and_updates():
    sid = db.create_search(PROFILE)
    assert db.save_lead(sid, LEAD) is True
    assert db.save_lead(sid, {**LEAD, "score": 90}) is False
    leads = db.list_leads(sid)
    assert len(leads) == 1 and leads[0]["score"] == 90


def test_run_tool_reports_http_errors():
    sid = db.create_search(PROFILE)
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    content, is_error = tools.run_tool("search_french_companies", {"query": "x"}, sid, http)
    assert is_error and "search_french_companies" in content


def test_google_maps_tool_only_when_key_set(monkeypatch):
    assert "search_google_maps" not in [t["name"] for t in tools.client_tools()]
    monkeypatch.setattr(config, "GOOGLE_MAPS_API_KEY", "k")
    assert "search_google_maps" in [t["name"] for t in tools.client_tools()]


class FakeClient:
    """Rejoue une suite de réponses de l'API Messages."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def block(**kw):
    return SimpleNamespace(**kw)


def test_agent_loop_saves_lead_and_finishes():
    sid = db.create_search(PROFILE)
    client = FakeClient([
        SimpleNamespace(stop_reason="pause_turn", content=[
            block(type="server_tool_use", name="web_search", input={"query": "BTP Lyon"}),
        ]),
        SimpleNamespace(stop_reason="tool_use", content=[
            block(type="tool_use", id="t1", name="save_lead", input=LEAD),
        ]),
        SimpleNamespace(stop_reason="end_turn", content=[block(type="text", text="1 lead trouvé.")]),
    ])
    agent.run_search(sid, PROFILE, client=client, http=httpx.Client())

    search = db.get_search(sid)
    assert search["status"] == "done" and search["summary"] == "1 lead trouvé."
    assert [l["company_name"] for l in db.list_leads(sid)] == ["Bâti Rhône"]
    assert any("BTP Lyon" in e["message"] for e in search["events"])
    # L'historique est partagé entre les appels : messages[3] = résultats d'outils.
    tool_result = client.calls[2]["messages"][3]["content"][0]
    assert tool_result["tool_use_id"] == "t1" and not tool_result["is_error"]
    assert client.calls[0]["fallbacks"] == "default"


def test_agent_nudges_once_when_short_of_target():
    profile = {**PROFILE, "lead_count": 5}
    sid = db.create_search(profile)
    done = SimpleNamespace(stop_reason="end_turn", content=[block(type="text", text="Fini.")])
    client = FakeClient([done, done])
    agent.run_search(sid, profile, client=client, http=httpx.Client())
    assert len(client.calls) == 2
    assert "0 leads sur les 5" in client.calls[1]["messages"][2]["content"]
    assert db.get_search(sid)["status"] == "done"


def test_agent_records_errors():
    sid = db.create_search(PROFILE)
    client = FakeClient([SimpleNamespace(stop_reason="refusal", content=[])])
    agent.run_search(sid, PROFILE, client=client, http=httpx.Client())
    assert db.get_search(sid)["status"] == "error"


def test_api_create_search_and_export(monkeypatch):
    def fake_run(search_id, profile):
        db.save_lead(search_id, LEAD)
        db.finish_search(search_id, "done", summary="ok")

    monkeypatch.setattr(agent, "run_search", fake_run)
    with TestClient(main.app) as http:
        assert http.post("/api/searches", json={"offer": "x"}).status_code == 422
        sid = http.post("/api/searches", json=PROFILE).json()["id"]
        for _ in range(50):
            if http.get(f"/api/searches/{sid}").json()["status"] == "done":
                break
        assert http.get(f"/api/searches/{sid}/leads").json()[0]["score"] == 82
        csv_text = http.get(f"/api/searches/{sid}/leads.csv").text
        assert "Bâti Rhône" in csv_text and "Recrute 2 chefs de chantier" in csv_text
        assert http.get("/").status_code == 200


def test_password_protects_app(monkeypatch):
    monkeypatch.setattr(config, "APP_PASSWORD", "secret")
    with TestClient(main.app) as http:
        assert http.get("/api/searches").status_code == 401
        assert http.get("/api/searches", auth=("x", "faux")).status_code == 401
        assert http.get("/api/searches", auth=("modeom", "secret")).status_code == 200


TENDER = {
    "title": "Création de locaux vélos", "buyer": "Bailleur Exemple", "buyer_type": "Bailleur social",
    "location": "Lyon (69)", "published": "2026-09-20", "deadline": "2026-10-30", "status": "ouvert",
    "scope": "Fourniture et pose de 3 abris vélos.", "reference": "26-123456",
    "url": "https://www.boamp.fr/pages/avis/?q=idweb:26-123456", "score": 85,
    "score_reason": "Produit Modeom, zone prioritaire.", "sources": [],
}


def test_search_boamp_retries_without_sort_and_trims_fields():
    calls = []

    def boamp(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        if "order_by" in request.url.params:
            return httpx.Response(400, json={"error": "unknown field"})
        return httpx.Response(200, json={"results": [
            {"idweb": "26-1", "objet": "Abris vélos", "descripteur_libelle": ["Abri", "Vélo"], "donnees": "x" * 5000},
        ]})

    http = httpx.Client(transport=httpx.MockTransport(boamp))
    results = tools.search_boamp({"query": 'local "vélos"'}, http)
    assert calls[0]["where"] == 'search("local  vélos ")'
    assert "order_by" not in calls[1]
    assert results == [{"idweb": "26-1", "objet": "Abris vélos", "descripteur_libelle": "Abri, Vélo"}]


def test_save_tender_dedupes_by_reference_and_exports_csv(monkeypatch):
    sid = db.create_search({**PROFILE, "kind": "tenders"})
    http = httpx.Client()
    tools.run_tool("save_tender", TENDER, sid, http)
    content, is_error = tools.run_tool("save_tender", {**TENDER, "score": 90, "url": ""}, sid, http)
    assert not is_error and "mis à jour" in content
    assert [t["score"] for t in db.list_leads(sid)] == [90]
    assert tools.client_tools("tenders")[0]["name"] == "search_boamp"
    with TestClient(main.app) as client:
        response = client.get(f"/api/searches/{sid}/leads.csv")
    assert "appels-offres-modeom" in response.headers["content-disposition"]
    assert "Création de locaux vélos" in response.text and "Date limite" in response.text


def test_tender_brief_includes_date_and_keywords():
    brief = agent.build_brief({**PROFILE, "kind": "tenders", "keywords": "abri vélos"})
    assert "Date du jour" in brief and "abri vélos" in brief and "save_tender" in brief
