from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Pillar, Review, ReviewStatus, Sentiment
from app.schemas import (DashboardSummary, ISRResponse, PillarScore,
                          PillarsSummary, ReviewOut)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

SENTIMENT_SCORE = {Sentiment.positivo: 1.0, Sentiment.neutro: 0.6, Sentiment.negativo: 0.2}


def require_manager_key(x_manager_key: str = Header(default="")):
    """
    Autenticação mínima do painel do gerente. TROCAR por autenticação real
    (login por restaurante) antes do piloto — isto é só um placeholder de MVP.
    """
    if x_manager_key != settings.manager_api_key:
        raise HTTPException(status_code=401, detail="Chave de gerente inválida.")


@router.get("/{restaurant_id}/reviews", response_model=list[ReviewOut], dependencies=[Depends(require_manager_key)])
def list_reviews(
    restaurant_id: str,
    limit: int = 20,
    channel: str | None = Query(default=None),
    sentiment: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Feed unificado do gerente — todos os canais (voz/texto local, Instagram,
    Google, WhatsApp, pedido iFood) na mesma timeline, com filtro opcional.
    """
    q = db.query(Review).filter(Review.restaurant_id == restaurant_id, Review.status != ReviewStatus.draft)
    if channel:
        q = q.filter(Review.channel == channel)
    if sentiment:
        q = q.filter(Review.sentiment == sentiment)
    reviews = q.order_by(Review.created_at.desc()).limit(limit).all()

    return [
        ReviewOut(
            id=r.id,
            customer_name=r.customer.name if r.customer else r.author_label,
            channel=r.channel.value,
            author_label=r.author_label,
            external_url=r.external_url,
            raw_text=r.raw_text,
            sentiment=r.sentiment.value if r.sentiment else None,
            pillar=r.pillar.value if r.pillar else None,
            points_awarded=r.points_awarded,
            status=r.status.value,
            created_at=r.created_at,
            tags=[t.label for t in r.tags],
        )
        for r in reviews
    ]


@router.get("/{restaurant_id}/summary", response_model=DashboardSummary, dependencies=[Depends(require_manager_key)])
def summary(restaurant_id: str, db: Session = Depends(get_db)):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    today_reviews = (
        db.query(Review)
        .filter(
            Review.restaurant_id == restaurant_id,
            Review.status != ReviewStatus.draft,
            Review.created_at >= today_start,
        )
        .all()
    )

    total = len(today_reviews)
    avg_score = (
        sum(SENTIMENT_SCORE.get(r.sentiment, 0.6) for r in today_reviews) / total
        if total else 0.0
    )
    actioned = sum(1 for r in today_reviews if r.status == ReviewStatus.actioned)
    percent_actioned = (actioned / total * 100) if total else 0.0
    points_today = sum(r.points_awarded for r in today_reviews)

    # Alerta "cliente ainda no local": última avaliação negativa dentro da janela configurada
    window_start = datetime.utcnow() - timedelta(minutes=settings.on_site_window_minutes)
    recent_negative = (
        db.query(Review)
        .filter(
            Review.restaurant_id == restaurant_id,
            Review.sentiment == Sentiment.negativo,
            Review.status == ReviewStatus.manager_notified,
            Review.created_at >= window_start,
        )
        .order_by(Review.created_at.desc())
        .first()
    )
    on_site_alert = None
    if recent_negative:
        on_site_alert = {
            "review_id": recent_negative.id,
            "table_id": recent_negative.table_id,
            "created_at": recent_negative.created_at.isoformat(),
        }

    return DashboardSummary(
        total_reviews_today=total,
        average_sentiment_score=round(avg_score, 2),
        percent_actioned=round(percent_actioned, 1),
        points_distributed_today=points_today,
        on_site_alert=on_site_alert,
    )


@router.get("/{restaurant_id}/pillars", response_model=PillarsSummary, dependencies=[Depends(require_manager_key)])
def pillars_summary(restaurant_id: str, days: int = 7, db: Session = Depends(get_db)):
    """Quebra de sentimento por pilar (Comida, Bebida, Atendimento, Tempo de Espera, Ambiente)."""
    window_start = datetime.utcnow() - timedelta(days=days)
    reviews = (
        db.query(Review)
        .filter(
            Review.restaurant_id == restaurant_id,
            Review.status != ReviewStatus.draft,
            Review.created_at >= window_start,
            Review.pillar.isnot(None),
        )
        .all()
    )

    scores = []
    for pillar in Pillar:
        pillar_reviews = [r for r in reviews if r.pillar == pillar]
        if not pillar_reviews:
            continue
        avg = sum(SENTIMENT_SCORE.get(r.sentiment, 0.6) for r in pillar_reviews) / len(pillar_reviews)
        scores.append(PillarScore(pillar=pillar.value, score_pct=round(avg * 100, 1), review_count=len(pillar_reviews)))

    return PillarsSummary(pillars=scores)


@router.get("/{restaurant_id}/isr", response_model=ISRResponse, dependencies=[Depends(require_manager_key)])
def isr_score(restaurant_id: str, days: int = 7, db: Session = Depends(get_db)):
    """
    ISR (Índice de Satisfação em tempo Real): combinação simples e transparente
    de (a) sentimento médio recente e (b) % de avaliações negativas já com ação
    tomada. Fórmula deliberadamente simples no MVP — documentar qualquer
    mudança de peso aqui, já que vira uma métrica que o gerente vai acompanhar.
    """
    window_start = datetime.utcnow() - timedelta(days=days)
    reviews = (
        db.query(Review)
        .filter(
            Review.restaurant_id == restaurant_id,
            Review.status != ReviewStatus.draft,
            Review.created_at >= window_start,
        )
        .all()
    )
    if not reviews:
        return ISRResponse(isr=0.0, components={"sentiment_medio": 0.0, "percent_negativas_com_acao": 0.0})

    sentiment_medio = sum(SENTIMENT_SCORE.get(r.sentiment, 0.6) for r in reviews) / len(reviews)

    negativas = [r for r in reviews if r.sentiment == Sentiment.negativo]
    percent_negativas_com_acao = (
        sum(1 for r in negativas if r.status == ReviewStatus.actioned) / len(negativas)
        if negativas else 1.0  # sem negativas para agir = não penaliza
    )

    isr = round((0.7 * sentiment_medio + 0.3 * percent_negativas_com_acao) * 100, 1)
    return ISRResponse(
        isr=isr,
        components={
            "sentimento_medio_pct": round(sentiment_medio * 100, 1),
            "percent_negativas_com_acao": round(percent_negativas_com_acao * 100, 1),
        },
    )
