from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import customers, dashboard, health, hub, pdv, reviews


@asynccontextmanager
async def lifespan(app: FastAPI):
    # MVP: cria as tabelas direto do modelo. Antes do piloto, trocar por
    # migrations de verdade (Alembic) para poder evoluir o schema com segurança.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Comer Fora — Avaliação por Voz",
    description="Backend do MVP: coleta de avaliação por áudio/texto, análise de IA e painel do gerente.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restringir ao domínio real do app do cliente antes do piloto
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(customers.router)
app.include_router(reviews.router)
app.include_router(dashboard.router)
app.include_router(pdv.router)
app.include_router(hub.router)
