"""
Teste de ponta a ponta usando SQLite em memória (sem precisar de Postgres nem
de chaves de API reais — a IA cai no heurístico local, o que já é suficiente
para provar que o pipeline inteiro funciona).
"""
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Restaurant, RestaurantTable

engine = sqlalchemy.create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

MANAGER_HEADERS = {"x-manager-key": "troque-esta-chave-antes-do-piloto"}


def _seed_restaurant():
    db = TestingSessionLocal()
    restaurant = Restaurant(name="Cantina de Teste")
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)
    restaurant_id = restaurant.id

    table = RestaurantTable(restaurant_id=restaurant_id, number="07")
    db.add(table)
    db.commit()
    db.refresh(table)
    table_id = table.id

    db.close()
    return restaurant_id, table_id


def test_full_pipeline():
    restaurant_id, table_id = _seed_restaurant()

    # 1. cliente confirma CPF
    resp = client.post("/customers/lookup", json={
        "cpf": "123.456.789-00", "table_number": "07", "restaurant_id": restaurant_id,
    })
    assert resp.status_code == 200
    customer_id = resp.json()["customer_id"]

    # 2. avaliação de texto (cai no heurístico local, sem chave de IA configurada)
    resp = client.post("/reviews/text", json={
        "restaurant_id": restaurant_id, "table_id": table_id, "customer_id": customer_id,
        "text": "O atendimento foi excelente e a comida chegou rápido, adorei o risoto!",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["points_awarded"] > 0
    review_id = body["review_id"]

    # 3. gerente marca ação tomada (métrica-norte)
    resp = client.patch(f"/reviews/{review_id}/mark-actioned")
    assert resp.status_code == 200

    # 4. feed do gerente reflete a avaliação
    resp = client.get(f"/dashboard/{restaurant_id}/reviews", headers=MANAGER_HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # 5. menção externa manual (Instagram) entra no mesmo pipeline
    resp = client.post("/reviews/external", json={
        "restaurant_id": restaurant_id, "channel": "instagram",
        "author_label": "@cliente_feliz", "text": "Comida maravilhosa, ambiente ótimo!",
    })
    assert resp.status_code == 200

    # 6. PDV-lite: cria comanda e pede sugestão de link da IA (heurístico local)
    resp = client.post("/pdv/orders", json={
        "restaurant_id": restaurant_id, "table_id": table_id,
        "ticket_value": 98.5, "items": ["Risoto de funghi", "Água"],
    })
    assert resp.status_code == 200

    resp = client.post(f"/pdv/reviews/{review_id}/suggest-link?restaurant_id={restaurant_id}")
    assert resp.status_code == 200

    # 7. rascunho de resposta com IA (heurístico local, já que sem chave)
    resp = client.post(f"/reviews/{review_id}/generate-response", json={"tone": "friendly"})
    assert resp.status_code == 200
    assert len(resp.json()["draft_text"]) > 0

    # 8. resumo e pilares do dashboard
    resp = client.get(f"/dashboard/{restaurant_id}/summary", headers=MANAGER_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["total_reviews_today"] == 2

    resp = client.get(f"/dashboard/{restaurant_id}/pillars", headers=MANAGER_HEADERS)
    assert resp.status_code == 200

    resp = client.get(f"/dashboard/{restaurant_id}/isr", headers=MANAGER_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["isr"] >= 0
