"""
Cria um restaurante e uma mesa de teste para desenvolvimento local.
Rodar com: python -m scripts.seed
"""
import json

from app.database import Base, SessionLocal, engine
from app.models import PDVOrder, PDVOrderStatus, Restaurant, RestaurantTable

Base.metadata.create_all(bind=engine)
db = SessionLocal()

existing = db.query(Restaurant).filter(Restaurant.name == "Cantina do Bairro").first()
if existing:
    print(f"Restaurante já existe: {existing.id}")
else:
    restaurant = Restaurant(name="Cantina do Bairro")
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)

    table = RestaurantTable(restaurant_id=restaurant.id, number="07")
    db.add(table)
    db.commit()
    db.refresh(table)

    order = PDVOrder(
        restaurant_id=restaurant.id,
        table_id=table.id,
        ticket_value=98.50,
        status=PDVOrderStatus.esperando,
        items_json=json.dumps(["Risoto de funghi", "2x Água"]),
    )
    db.add(order)
    db.commit()

    print(f"Restaurante criado: {restaurant.id}")
    print(f"Mesa criada: {table.id} (número {table.number})")
    print(f"Comanda de teste (PDV-lite) criada: {order.id}")

db.close()
