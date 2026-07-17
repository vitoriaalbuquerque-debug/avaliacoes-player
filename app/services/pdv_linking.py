"""
Sugere a qual comanda (PDV-lite) uma avaliação provavelmente se refere,
comparando o texto da avaliação com os itens de cada pedido em aberto.

Isso é real e útil mesmo sem integração de PDV de verdade: o restaurante
mantém as comandas manualmente (ver routers/pdv.py), e esta função só faz o
match semântico — a parte cara de construir manualmente.
"""
import json
import re

import httpx

from app.config import settings
from app.schemas import SuggestLinkCandidate

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

PROMPT_TEMPLATE = """Você recebe o texto de uma avaliação de cliente e uma lista de comandas
abertas de um restaurante brasileiro. Aponte quais comandas provavelmente têm relação com a
avaliação (ex: cita um prato/bebida da comanda, ou reclama de algo compatível com os itens).

Responda APENAS com um JSON válido, no formato exato:
{{"candidates": [{{"order_id": "id da comanda", "confidence": número de 0 a 100, "reason": "justificativa curta em português"}}]}}

Se nenhuma comanda parecer relacionada, responda {{"candidates": []}}. Liste no máximo 3 candidatos,
ordenados do mais provável para o menos provável.

Avaliação: \"\"\"{review_text}\"\"\"

Comandas abertas:
{orders_block}"""


async def suggest_link(review_text: str, orders: list[dict]) -> list[SuggestLinkCandidate]:
    """orders: lista de {"id": str, "items": [str, ...]}"""
    if not orders:
        return []

    if not settings.gemini_api_key:
        return _heuristic_link(review_text, orders)

    orders_block = "\n".join(
        f'- id: {o["id"]} | itens: {", ".join(o["items"])}' for o in orders
    )
    try:
        url = GEMINI_URL_TEMPLATE.format(model=settings.gemini_model)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"parts": [{"text": PROMPT_TEMPLATE.format(
                        review_text=review_text, orders_block=orders_block)}]}],
                    "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1},
                },
            )
            response.raise_for_status()
            data = response.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            clean = re.sub(r"```json|```", "", raw).strip()
            parsed = json.loads(clean)
            return [SuggestLinkCandidate(**c) for c in parsed.get("candidates", [])]
    except Exception:
        return _heuristic_link(review_text, orders)


def _heuristic_link(review_text: str, orders: list[dict]) -> list[SuggestLinkCandidate]:
    """Fallback simples: conta palavras do texto que aparecem nos itens do pedido."""
    text_words = set(re.findall(r"\w+", review_text.lower()))
    scored = []
    for order in orders:
        item_words = set(re.findall(r"\w+", " ".join(order["items"]).lower()))
        overlap = text_words & item_words
        if overlap:
            confidence = min(90.0, 30.0 + len(overlap) * 20.0)
            scored.append(SuggestLinkCandidate(
                order_id=order["id"],
                confidence=confidence,
                reason=f"Palavras em comum com os itens do pedido (checagem local, sem IA): {', '.join(sorted(overlap))}",
            ))
    scored.sort(key=lambda c: c.confidence, reverse=True)
    return scored[:3]
