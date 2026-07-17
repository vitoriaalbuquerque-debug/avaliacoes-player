"""
Helpers pra formatar dado do nosso schema real no formato que o dashboard
React (comer-fora-dashboard-react) espera — ver src/types.ts do projeto dela.
Mantemos essa tradução isolada aqui pra não espalhar mapeamento de campo por
todos os routers.
"""
from sqlalchemy.orm import Session

from app.models import PDVOrder, Review, RestaurantTable, Sentiment

SENTIMENT_TO_STARS = {Sentiment.positivo: 5.0, Sentiment.neutro: 3.0, Sentiment.negativo: 1.0}
SENTIMENT_TO_SCORE = {Sentiment.positivo: 85, Sentiment.neutro: 55, Sentiment.negativo: 20}
SENTIMENT_TO_EMOJI = {Sentiment.positivo: "😊", Sentiment.neutro: "😐", Sentiment.negativo: "😡"}
SENTIMENT_TO_LEVEL = {Sentiment.positivo: "AVISO", Sentiment.neutro: "ALERTA", Sentiment.negativo: "CRÍTICO"}

SUGGESTION_TEMPLATES = {
    Sentiment.negativo: "Vá até a mesa agora, peça desculpas e ofereça uma cortesia.",
    Sentiment.neutro: "Monitore a mesa e pergunte se precisam de algum suporte.",
    Sentiment.positivo: "Agradeça pessoalmente e convide o cliente a voltar em breve.",
}


def sentiment_to_stars(sentiment) -> float:
    return SENTIMENT_TO_STARS.get(sentiment, 3.0)


def build_react_alert(db: Session, review: Review) -> dict:
    table = db.query(RestaurantTable).filter(RestaurantTable.id == review.table_id).first() if review.table_id else None
    linked_order = db.query(PDVOrder).filter(PDVOrder.linked_review_id == review.id).first()
    prato = linked_order.items_json if linked_order else None
    if prato:
        import json
        try:
            items = json.loads(prato)
            prato = items[0] if items else "Prato não especificado"
        except Exception:
            prato = "Prato não especificado"
    else:
        prato = "Prato não especificado"

    sentiment = review.sentiment
    return {
        "id": review.id,
        "emoji": SENTIMENT_TO_EMOJI.get(sentiment, "😐"),
        "sentiment": (sentiment.value if sentiment else "neutro"),
        "score": SENTIMENT_TO_SCORE.get(sentiment, 55),
        "mesa": table.number if table else "—",
        "garcom": review.waiter_name or "—",
        "prato": prato,
        "reviewText": review.raw_text,
        "originalText": review.raw_text,
        "level": SENTIMENT_TO_LEVEL.get(sentiment, "ALERTA"),
        "aiSuggestion": SUGGESTION_TEMPLATES.get(sentiment, SUGGESTION_TEMPLATES[Sentiment.neutro]),
        "tags": [t.label for t in review.tags] if review.tags else ([review.pillar.value] if review.pillar else []),
    }
