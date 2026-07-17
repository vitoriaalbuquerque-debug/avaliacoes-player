import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PDVOrder, PDVOrderStatus, Review
from app.schemas import (PDVOrderIn, PDVOrderOut, SuggestLinkResponse)
from app.services.pdv_linking import suggest_link

router = APIRouter(prefix="/pdv", tags=["pdv"])


def _to_out(order: PDVOrder) -> PDVOrderOut:
    return PDVOrderOut(
        id=order.id,
        table_id=order.table_id,
        ticket_value=order.ticket_value,
        status=order.status.value,
        items=json.loads(order.items_json),
        waiter_name=order.waiter_name,
        linked_review_id=order.linked_review_id,
        ai_confidence=order.ai_confidence,
        ai_link_reason=order.ai_link_reason,
        created_at=order.created_at,
    )


@router.post("/orders", response_model=PDVOrderOut)
def create_order(payload: PDVOrderIn, db: Session = Depends(get_db)):
    """
    'PDV-lite': o restaurante lança a comanda manualmente (sem integração com
    sistema de PDV real ainda). Ver services/pdv_linking.py para a parte de
    IA que usa esses dados.
    """
    order = PDVOrder(
        restaurant_id=payload.restaurant_id,
        table_id=payload.table_id,
        ticket_value=payload.ticket_value,
        status=PDVOrderStatus(payload.status),
        items_json=json.dumps(payload.items),
        waiter_name=payload.waiter_name,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return _to_out(order)


@router.get("/orders", response_model=list[PDVOrderOut])
def list_orders(restaurant_id: str, db: Session = Depends(get_db)):
    orders = (
        db.query(PDVOrder)
        .filter(PDVOrder.restaurant_id == restaurant_id)
        .order_by(PDVOrder.created_at.desc())
        .all()
    )
    return [_to_out(o) for o in orders]


@router.post("/reviews/{review_id}/suggest-link", response_model=SuggestLinkResponse)
async def suggest_order_link(review_id: str, restaurant_id: str, db: Session = Depends(get_db)):
    """IA sugere quais comandas abertas provavelmente se relacionam com esta avaliação."""
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    open_orders = (
        db.query(PDVOrder)
        .filter(PDVOrder.restaurant_id == restaurant_id, PDVOrder.linked_review_id.is_(None))
        .all()
    )
    orders_payload = [{"id": o.id, "items": json.loads(o.items_json)} for o in open_orders]
    candidates = await suggest_link(review.raw_text, orders_payload)
    return SuggestLinkResponse(candidates=candidates)


@router.post("/orders/{order_id}/link/{review_id}", response_model=PDVOrderOut)
def confirm_link(order_id: str, review_id: str, confidence: float = 0.0, reason: str = "", db: Session = Depends(get_db)):
    """Gerente confirma o link sugerido pela IA (ou faz manualmente)."""
    order = db.query(PDVOrder).filter(PDVOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Comanda não encontrada.")
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    order.linked_review_id = review.id
    order.ai_confidence = confidence
    order.ai_link_reason = reason
    db.commit()
    db.refresh(order)
    return _to_out(order)
