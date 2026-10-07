"""Serveur web : API JSON + interface de consultation des leads."""

import base64
import csv
import io
import secrets
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, config, db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init()
    yield


app = FastAPI(title="Modeom – Agent de recherche de leads", lifespan=lifespan)
STATIC_DIR = config.ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def require_password(request: Request, call_next):
    """Protège l'application par mot de passe quand APP_PASSWORD est défini (mise en ligne)."""
    if config.APP_PASSWORD:
        header = request.headers.get("authorization", "")
        password = ""
        if header.startswith("Basic "):
            try:
                password = base64.b64decode(header[6:]).decode().partition(":")[2]
            except ValueError:
                pass
        if not secrets.compare_digest(password.encode(), config.APP_PASSWORD.encode()):
            return Response(
                "Mot de passe requis",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="Modeom Leads", charset="UTF-8"'},
            )
    return await call_next(request)


class Profile(BaseModel):
    offer: str = Field(min_length=3, description="Ce que Modeom vend")
    target: str = Field(min_length=3, description="Description du client idéal")
    sectors: str = ""
    locations: str = ""
    company_sizes: str = ""
    decision_makers: str = ""
    signals: str = ""
    exclusions: str = ""
    lead_count: int = Field(default=15, ge=1, le=50)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def get_config() -> dict:
    return {"model": config.MODEL, "google_maps": bool(config.GOOGLE_MAPS_API_KEY)}


@app.post("/api/searches", status_code=201)
def create_search(profile: Profile) -> dict:
    data = profile.model_dump()
    search_id = db.create_search(data)
    threading.Thread(target=agent.run_search, args=(search_id, data), daemon=True).start()
    return {"id": search_id}


@app.get("/api/searches")
def list_searches() -> list[dict]:
    return db.list_searches()


@app.get("/api/searches/{search_id}")
def get_search(search_id: int) -> dict:
    search = db.get_search(search_id)
    if search is None:
        raise HTTPException(404, "Recherche introuvable")
    return search


@app.get("/api/searches/{search_id}/leads")
def get_leads(search_id: int) -> list[dict]:
    return db.list_leads(search_id)


CSV_COLUMNS = [
    ("score", "Score"), ("company_name", "Entreprise"), ("sector", "Activité"), ("city", "Ville"),
    ("company_size", "Taille"), ("siren", "SIREN"), ("website", "Site"), ("contact_name", "Contact"),
    ("contact_role", "Poste"), ("linkedin_url", "LinkedIn"), ("email", "Email"), ("phone", "Téléphone"),
    ("score_reason", "Justification"), ("signals", "Signaux"), ("outreach_hook", "Accroche"),
    ("sources", "Sources"),
]


@app.get("/api/searches/{search_id}/leads.csv")
def export_leads(search_id: int) -> StreamingResponse:
    buffer = io.StringIO()
    buffer.write("﻿")  # BOM pour qu'Excel lise correctement les accents
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([label for _, label in CSV_COLUMNS])
    for lead in db.list_leads(search_id):
        writer.writerow([
            " | ".join(lead.get(key) or []) if isinstance(lead.get(key), list) else lead.get(key, "")
            for key, _ in CSV_COLUMNS
        ])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="leads-modeom-{search_id}.csv"'},
    )
