from tests.test_pipeline import MANAGER_HEADERS, TestingSessionLocal, _seed_restaurant, client


def test_hub_submit_full_flow():
    restaurant_id, table_id = _seed_restaurant()

    # cliente preenche 3 dos 4 módulos e informa CPF no final
    resp = client.post("/ai/analyze-preview", json={"text": "Atendimento rápido e comida deliciosa!"})
    assert resp.status_code == 200
    assert resp.json()["sentimento"] in ("positivo", "neutro", "negativo")

    resp = client.post("/reviews/hub-submit", json={
        "restaurant_id": restaurant_id,
        "table_number": "07",
        "cpf": "123.456.789-00",
        "audio_transcript": "Atendimento rápido e comida deliciosa, adorei!",
        "audio_duration_seconds": 30,
        "stars_avg": 4.5,
        "stars_filled_categories": 3,
        "freetext": "Voltaria com certeza, ambiente muito agradável.",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_points"] > 0
    assert body["anonymous"] is False

    resp = client.get(f"/dashboard/{restaurant_id}/reviews", headers=MANAGER_HEADERS)
    assert resp.status_code == 200
    # 3 módulos preenchidos = 3 registros de avaliação (voz, estrelas, texto)
    assert len(resp.json()) == 3


def test_hub_submit_anonymous_gets_no_points():
    restaurant_id, table_id = _seed_restaurant()

    resp = client.post("/reviews/hub-submit", json={
        "restaurant_id": restaurant_id,
        "table_number": "07",
        "freetext": "Foi bom, sem reclamações.",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["anonymous"] is True
    assert body["total_points"] == 0
