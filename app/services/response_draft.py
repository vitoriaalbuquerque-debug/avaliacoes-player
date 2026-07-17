"""
Rascunha uma resposta ao cliente no tom escolhido pelo gerente. Isso é sempre
um RASCUNHO — o produto nunca envia mensagem sozinho (ver policy de ações
sensíveis); o gerente copia e manda pelo canal que quiser.
"""
import httpx

from app.config import settings

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

TONE_LABELS = {
    "friendly": "simpático e caloroso, com emojis moderados",
    "apologetic": "formal e claramente contrito, sem soar robótico",
    "professional": "profissional e objetivo, sem informalidade",
    "assertive": "direto e resolutivo, focado em qual ação já foi tomada",
}

FALLBACK_TEMPLATES = {
    "friendly": 'Oi! Obrigado pelo retorno sobre "{restaurant_name}". Já estamos cuidando disso pra você! 🙌',
    "apologetic": 'Lamentamos muito pela experiência em "{restaurant_name}". Já estamos revisando o ocorrido internamente.',
    "professional": 'Agradecemos o retorno sobre "{restaurant_name}". Sua avaliação foi registrada e será tratada pela equipe responsável.',
    "assertive": 'Feedback recebido sobre "{restaurant_name}". Ação corretiva já iniciada pela equipe.',
}


async def draft_response(review_text: str, sentiment: str, restaurant_name: str, tone: str) -> str:
    tone_label = TONE_LABELS.get(tone, TONE_LABELS["professional"])

    if not settings.gemini_api_key:
        return FALLBACK_TEMPLATES.get(tone, FALLBACK_TEMPLATES["professional"]).format(
            restaurant_name=restaurant_name
        )

    prompt = f"""Você escreve, em português do Brasil, uma resposta curta (máximo 3 frases) de um
restaurante chamado "{restaurant_name}" para um cliente que deixou a seguinte avaliação
(sentimento identificado: {sentiment}):

\"\"\"{review_text}\"\"\"

O tom da resposta deve ser: {tone_label}.
Responda APENAS com o texto da resposta, sem aspas, sem explicação extra."""

    try:
        url = GEMINI_URL_TEMPLATE.format(model=settings.gemini_model)
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                url,
                params={"key": settings.gemini_api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.4},
                },
            )
            response.raise_for_status()
            data = response.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return text.strip() or FALLBACK_TEMPLATES.get(tone, FALLBACK_TEMPLATES["professional"]).format(
                restaurant_name=restaurant_name
            )
    except Exception:
        return FALLBACK_TEMPLATES.get(tone, FALLBACK_TEMPLATES["professional"]).format(
            restaurant_name=restaurant_name
        )
