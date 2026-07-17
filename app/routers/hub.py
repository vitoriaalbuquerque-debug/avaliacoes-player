from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (Channel, Customer, Pillar, Restaurant,
                         RestaurantTable, Review, ReviewStatus, ReviewTag,
                         RewardRedemption, Sentiment)
from app.schemas import (AIAnalysis, AnalyzePreviewRequest, HubSubmitRequest,
                          HubSubmitResponse)
from app.services.ai_analysis import analyze_review
from app.services.points import (benefit_for_points, hub_points_audio,
                                  hub_points_freetext, hub_points_photos,
                                  hub_points_stars)
from app.services.security import hash_cpf, is_valid_cpf_format

router = APIRouter(tags=["hub"])


# ---------- Preview de IA sem persistir — usado enquanto o cliente digita/fala ----------

@router.post("/ai/analyze-preview", response_model=AIAnalysis)
async def analyze_preview(payload: AnalyzePreviewRequest):
    """
    Mesma IA do backend real, só que sem salvar nada — usada pelas telas de
    'Texto Livre' (preview ao digitar) e 'Confirmar Áudio' (preview do que foi
    transcrito) do hub modular, antes do cliente decidir se confirma o módulo.
    """
    return await analyze_review(payload.text)


# ---------- Fechamento do hub: todos os módulos preenchidos + CPF por último ----------

@router.post("/reviews/hub-submit", response_model=HubSubmitResponse)
async def submit_hub(payload: HubSubmitRequest, db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(Restaurant.id == payload.restaurant_id).first()
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurante não encontrado.")
    table = (
        db.query(RestaurantTable)
        .filter(RestaurantTable.restaurant_id == payload.restaurant_id, RestaurantTable.number == payload.table_number)
        .first()
    )
    if not table:
        raise HTTPException(status_code=404, detail="Mesa não encontrada.")

    anonymous = not payload.cpf
    customer_id = None
    if not anonymous:
        if not is_valid_cpf_format(payload.cpf):
            raise HTTPException(status_code=400, detail="CPF inválido — precisa ter 11 dígitos.")
        cpf_hash = hash_cpf(payload.cpf)
        customer = db.query(Customer).filter(Customer.cpf_hash == cpf_hash).first()
        if not customer:
            customer = Customer(cpf_hash=cpf_hash)
            db.add(customer)
            db.commit()
            db.refresh(customer)
        customer_id = customer.id

    total_points = 0
    created_reviews = []
    review_temas = {}  # id(review) -> list[str], já que o id do banco só existe após commit

    # --- módulo áudio ---
    if payload.audio_transcript and payload.audio_duration_seconds:
        analysis = await analyze_review(payload.audio_transcript)
        points = hub_points_audio(payload.audio_duration_seconds)
        total_points += points
        review = _build_review(
            restaurant.id, table.id, customer_id, Channel.voz_local,
            payload.audio_transcript, analysis, points,
            duration_seconds=payload.audio_duration_seconds,
            waiter_name=payload.waiter_name,
        )
        review_temas[id(review)] = analysis.temas
        created_reviews.append(review)

    # --- módulo notas por estrela (sem texto — sentimento vem da média) ---
    if payload.stars_filled_categories:
        points = hub_points_stars(payload.stars_filled_categories)
        total_points += points
        stars_sentiment = (
            "positivo" if (payload.stars_avg or 0) >= 4
            else "negativo" if (payload.stars_avg or 0) <= 2
            else "neutro"
        )
        analysis = AIAnalysis(
            plausivel=True,
            motivo="Sentimento derivado da média das notas (sem texto para IA analisar).",
            sentimento=stars_sentiment,
            pilar="geral",
            temas=[],
        )
        created_reviews.append(_build_review(
            restaurant.id, table.id, customer_id, Channel.estrelas_local,
            f"Notas médias: {payload.stars_avg}", analysis, points,
            waiter_name=payload.waiter_name,
        ))

    # --- módulo fotos (sem texto — sentimento neutro por padrão) ---
    if payload.photos_count:
        points = hub_points_photos(payload.photos_count)
        total_points += points
        analysis = AIAnalysis(
            plausivel=True, motivo="Módulo de fotos não tem texto para IA analisar.",
            sentimento="neutro", pilar="geral", temas=[],
        )
        created_reviews.append(_build_review(
            restaurant.id, table.id, customer_id, Channel.fotos_local,
            f"{payload.photos_count} foto(s) enviada(s)", analysis, points,
            waiter_name=payload.waiter_name,
        ))

    # --- módulo texto livre ---
    if payload.freetext:
        analysis = await analyze_review(payload.freetext)
        points = hub_points_freetext(len(payload.freetext))
        total_points += points
        review = _build_review(
            restaurant.id, table.id, customer_id, Channel.texto_local,
            payload.freetext, analysis, points,
            waiter_name=payload.waiter_name,
        )
        review_temas[id(review)] = analysis.temas
        created_reviews.append(review)

    if not created_reviews:
        raise HTTPException(status_code=400, detail="Nenhum módulo preenchido.")

    # Sentimento geral do atendimento: pior sentimento entre os módulos com texto
    # (mesma lógica do protótipo — não deixa uma nota 5 estrelas escondida
    # "abafar" uma reclamação séria no texto livre).
    sentiments = [r.sentiment for r in created_reviews if r.sentiment]
    if Sentiment.negativo in sentiments:
        overall = Sentiment.negativo
    elif Sentiment.positivo in sentiments:
        overall = Sentiment.positivo
    else:
        overall = Sentiment.neutro

    manager_notified = overall == Sentiment.negativo
    status = ReviewStatus.manager_notified if manager_notified else ReviewStatus.received

    for review in created_reviews:
        review.status = status
        review.confirmed_at = datetime.utcnow()
        db.add(review)
    db.commit()
    for review in created_reviews:
        db.refresh(review)
        for tema in review_temas.get(id(review), []):
            db.add(ReviewTag(review_id=review.id, label=tema))
    db.commit()

    benefit_description = "Obrigado pela participação!"
    redeem_by = None
    if not anonymous:
        benefit_description, redeem_by = benefit_for_points(total_points)
        for review in created_reviews:
            db.add(RewardRedemption(
                customer_id=customer_id,
                review_id=review.id,
                benefit_description=benefit_description,
                points_awarded=review.points_awarded,
                redeem_by=redeem_by,
            ))
        db.commit()

    return HubSubmitResponse(
        total_points=total_points if not anonymous else 0,
        benefit_description=benefit_description,
        redeem_by=redeem_by,
        overall_sentiment=overall.value,
        manager_notified=manager_notified,
        anonymous=anonymous,
    )


def _build_review(restaurant_id, table_id, customer_id, channel, text, analysis: AIAnalysis, points, duration_seconds=None, waiter_name=None) -> Review:
    review = Review(
        restaurant_id=restaurant_id,
        table_id=table_id,
        customer_id=customer_id,
        channel=channel,
        raw_text=text,
        char_count=len(text),
        duration_seconds=duration_seconds,
        waiter_name=waiter_name,
        sentiment=Sentiment(analysis.sentimento),
        pillar=Pillar(analysis.pilar),
        plausible=analysis.plausivel,
        ai_reason=analysis.motivo,
        points_awarded=points,
        status=ReviewStatus.draft,
    )
    return review
