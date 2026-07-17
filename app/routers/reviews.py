import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import (Channel, Pillar, Review, ReviewStatus, ReviewTag,
                         RewardRedemption, Sentiment)
from app.schemas import (AudioTranscribeResponse, ExternalFeedbackRequest,
                          GenerateResponseRequest, GenerateResponseResponse,
                          ReviewAnalyzeRequest, ReviewAnalyzeResponse,
                          ReviewConfirmResponse, TextReviewRejected,
                          TextReviewRequest)
from app.services.ai_analysis import analyze_review
from app.services.broadcast import publish
from app.services.points import benefit_for_points, points_for_audio, points_for_text
from app.services.react_format import build_react_alert
from app.services.response_draft import draft_response
from app.services.transcription import transcribe_audio

router = APIRouter(prefix="/reviews", tags=["reviews"])


# ---------- Fluxo de ÁUDIO: gravar -> transcrever (rascunho) ----------

@router.post("/audio/transcribe", response_model=AudioTranscribeResponse)
async def transcribe_audio_review(
    restaurant_id: str,
    table_id: str,
    customer_id: str,
    duration_seconds: int,
    file: UploadFile,
    db: Session = Depends(get_db),
):
    """
    Recebe o áudio gravado no navegador, transcreve, e salva como RASCUNHO
    (status=draft) — ainda não conta ponto nem aparece pro gerente. O cliente
    confirma ou descarta na tela seguinte (ver /reviews/{id}/analyze e /confirm).
    """
    os.makedirs(settings.audio_storage_dir, exist_ok=True)
    file_bytes = await file.read()
    filename = f"{uuid.uuid4()}.webm"
    audio_path = os.path.join(settings.audio_storage_dir, filename)
    with open(audio_path, "wb") as f:
        f.write(file_bytes)

    transcript = await transcribe_audio(file_bytes, filename=file.filename or "audio.webm")

    review = Review(
        restaurant_id=restaurant_id,
        table_id=table_id,
        customer_id=customer_id,
        channel=Channel.voz_local,
        raw_text=transcript,
        audio_path=audio_path,
        duration_seconds=duration_seconds,
        status=ReviewStatus.draft,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    return AudioTranscribeResponse(review_id=review.id, transcript=transcript)


# ---------- Analisar (usado por áudio, após edição da transcrição) ----------

@router.post("/{review_id}/analyze", response_model=ReviewAnalyzeResponse)
async def analyze_draft_review(review_id: str, payload: ReviewAnalyzeRequest, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    review.raw_text = payload.edited_text
    review.char_count = len(payload.edited_text)
    analysis = await analyze_review(payload.edited_text)

    review.sentiment = Sentiment(analysis.sentimento)
    review.pillar = Pillar(analysis.pilar)
    review.plausible = analysis.plausivel
    review.ai_reason = analysis.motivo
    db.query(ReviewTag).filter(ReviewTag.review_id == review.id).delete()
    for tema in analysis.temas:
        db.add(ReviewTag(review_id=review.id, label=tema))
    db.commit()

    points_estimate = points_for_audio(review.duration_seconds or 0, review.char_count)
    return ReviewAnalyzeResponse(review_id=review.id, analysis=analysis, points_estimate=points_estimate)


# ---------- Confirmar (fecha a avaliação de áudio) ----------

@router.post("/{review_id}/confirm", response_model=ReviewConfirmResponse)
async def confirm_review(review_id: str, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    points = points_for_audio(review.duration_seconds or 0, review.char_count)
    return _finalize_review(db, review, points)


# ---------- Fluxo de TEXTO (sem rascunho — analisa e já decide) ----------

@router.post("/text")
async def submit_text_review(payload: TextReviewRequest, db: Session = Depends(get_db)):
    text = payload.text.strip()
    if len(text) < 3:
        return TextReviewRejected(motivo="Escreva um pouco sobre sua experiência antes de enviar.")

    analysis = await analyze_review(text)
    if not analysis.plausivel:
        return TextReviewRejected(motivo=analysis.motivo)

    review = Review(
        restaurant_id=payload.restaurant_id,
        table_id=payload.table_id,
        customer_id=payload.customer_id,
        channel=Channel.texto_local,
        raw_text=text,
        char_count=len(text),
        sentiment=Sentiment(analysis.sentimento),
        pillar=Pillar(analysis.pilar),
        plausible=analysis.plausivel,
        ai_reason=analysis.motivo,
        status=ReviewStatus.draft,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    for tema in analysis.temas:
        db.add(ReviewTag(review_id=review.id, label=tema))
    db.commit()

    points = points_for_text(len(text))
    return _finalize_review(db, review, points)


# ---------- Feed multi-canal: menção externa lançada manualmente pelo gerente ----------
# Sem scraping/integração — o gerente cola o que viu no Instagram/Google/WhatsApp/
# pedido iFood, e passa pelo MESMO pipeline de IA (sentimento, pilar, temas).

@router.post("/external")
async def log_external_feedback(payload: ExternalFeedbackRequest, db: Session = Depends(get_db)):
    text = payload.text.strip()
    if len(text) < 3:
        raise HTTPException(status_code=400, detail="Texto da menção não pode ser vazio.")

    analysis = await analyze_review(text)

    review = Review(
        restaurant_id=payload.restaurant_id,
        customer_id=None,
        channel=Channel(payload.channel),
        author_label=payload.author_label,
        external_url=payload.external_url,
        waiter_name=payload.waiter_name,
        raw_text=text,
        char_count=len(text),
        sentiment=Sentiment(analysis.sentimento),
        pillar=Pillar(analysis.pilar),
        plausible=analysis.plausivel,
        ai_reason=analysis.motivo,
        status=ReviewStatus.received,
        confirmed_at=datetime.utcnow(),
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    for tema in analysis.temas:
        db.add(ReviewTag(review_id=review.id, label=tema))
    db.commit()

    await publish(payload.restaurant_id, build_react_alert(db, review))

    return {"review_id": review.id, "sentiment": analysis.sentimento, "pillar": analysis.pilar}


# ---------- IA rascunha uma resposta pro cliente, no tom escolhido ----------
# Nunca envia nada sozinha — o gerente copia e manda pelo canal que preferir.

@router.post("/{review_id}/generate-response", response_model=GenerateResponseResponse)
async def generate_response(review_id: str, payload: GenerateResponseRequest, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    draft_text = await draft_response(
        review_text=review.raw_text,
        sentiment=review.sentiment.value if review.sentiment else "neutro",
        restaurant_name=review.restaurant.name if review.restaurant else "o restaurante",
        tone=payload.tone,
    )
    return GenerateResponseResponse(review_id=review.id, tone=payload.tone, draft_text=draft_text)


# ---------- Gerente marca que tomou uma ação (métrica-norte) ----------

@router.patch("/{review_id}/mark-actioned")
def mark_actioned(review_id: str, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")
    review.status = ReviewStatus.actioned
    review.actioned_at = datetime.utcnow()
    db.commit()
    return {"review_id": review.id, "status": review.status}


# ---------- Interno ----------

def _finalize_review(db: Session, review: Review, points: int) -> ReviewConfirmResponse:
    review.points_awarded = points
    review.confirmed_at = datetime.utcnow()

    manager_notified = review.sentiment == Sentiment.negativo
    review.status = ReviewStatus.manager_notified if manager_notified else ReviewStatus.received

    benefit_description, redeem_by = benefit_for_points(points)
    db.add(RewardRedemption(
        customer_id=review.customer_id,
        review_id=review.id,
        benefit_description=benefit_description,
        points_awarded=points,
        redeem_by=redeem_by,
    ))
    db.commit()

    return ReviewConfirmResponse(
        review_id=review.id,
        points_awarded=points,
        benefit_description=benefit_description,
        redeem_by=redeem_by,
        sentiment=review.sentiment.value if review.sentiment else "neutro",
        manager_notified=manager_notified,
    )
