"""
Análise de avaliações com IA: plausibilidade, sentimento, pilar e temas —
sempre com justificativa em texto, pra nunca virar uma "caixa preta" no
painel do gerente.

Chama a API do Gemini de verdade quando GEMINI_API_KEY está configurada.
Se a chamada falhar (sem internet, sem chave, rate limit), cai automaticamente
num heurístico local por palavras-chave — o fluxo do cliente nunca quebra,
mas o eval set (Semana 2-3 do roadmap) deve medir a diferença de qualidade
entre os dois caminhos.
"""
import json
import re

import httpx

from app.config import settings
from app.schemas import AIAnalysis

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

SYSTEM_PROMPT = """Você classifica avaliações de restaurante em português do Brasil.
Responda APENAS com um JSON válido, sem markdown e sem texto fora do JSON, no formato exato:
{"plausivel": true ou false, "motivo": "string curta em português", "sentimento": "positivo" ou "neutro" ou "negativo", "pilar": "comida" ou "bebida" ou "atendimento" ou "tempo_espera" ou "ambiente" ou "geral", "temas": ["até 3 temas curtos, ex: Atendimento, Comida, Tempo de espera, Ambiente"]}

Considere implausível apenas texto claramente aleatório, spam, ou sem qualquer relação
com uma experiência em restaurante. Textos curtos porém coerentes (ex: "foi bom, gostei")
são plausíveis. O campo "pilar" deve ser o assunto PRINCIPAL do texto — use "geral" só se
não der pra identificar um assunto dominante."""

GOOD_WORDS = ["bom", "ótimo", "otimo", "excelente", "adorei", "gostei", "recomendo",
              "delicioso", "rápido", "rapido", "atencioso", "maravilhoso", "quentinha"]
BAD_WORDS = ["ruim", "péssimo", "pessimo", "demorou", "demora", "frio", "fria",
             "atraso", "reclama", "horrível", "horrivel", "sujo", "grosseiro", "salgado"]

PILLAR_KEYWORDS = {
    "comida": ["comida", "prato", "risoto", "hambúrguer", "hamburguer", "sabor", "salgado", "frio", "fria", "cardápio", "cardapio"],
    "bebida": ["bebida", "cerveja", "vinho", "drink", "suco", "refrigerante"],
    "atendimento": ["atendimento", "garçom", "garcom", "atencioso", "grosseiro", "equipe", "funcionário", "funcionario"],
    "tempo_espera": ["demora", "demorou", "espera", "atraso", "rápido", "rapido", "fila"],
    "ambiente": ["ambiente", "barulho", "música", "musica", "decoração", "decoracao", "sujo", "limpo"],
}


async def analyze_review(text: str) -> AIAnalysis:
    if settings.gemini_api_key:
        try:
            return await _analyze_with_gemini(text)
        except Exception:
            # Não deixa uma falha de rede/API derrubar a avaliação do cliente.
            pass
    return _heuristic_analyze(text)


async def _analyze_with_gemini(text: str) -> AIAnalysis:
    url = GEMINI_URL_TEMPLATE.format(model=settings.gemini_model)
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            params={"key": settings.gemini_api_key},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": [{"parts": [{"text": f'Texto da avaliação: """{text}"""'}]}],
                "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1},
            },
        )
        response.raise_for_status()
        data = response.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        clean = re.sub(r"```json|```", "", raw).strip()
        parsed = json.loads(clean)
        return AIAnalysis(**parsed)


def _heuristic_analyze(text: str) -> AIAnalysis:
    t = (text or "").lower().strip()
    words = [w for w in t.split() if w]
    unique_ratio = len(set(words)) / max(len(words), 1)
    score = sum(1 for w in GOOD_WORDS if w in t) - sum(1 for w in BAD_WORDS if w in t)
    no_repeat = not re.match(r"^(.)\1+$", t.replace(" ", ""))
    plausivel = len(words) >= 2 and unique_ratio > 0.4 and no_repeat

    pilar = "geral"
    best_hits = 0
    for candidate, keywords in PILLAR_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in t)
        if hits > best_hits:
            best_hits = hits
            pilar = candidate

    return AIAnalysis(
        plausivel=plausivel,
        motivo=(
            "Texto reconhecido como avaliação coerente (checagem local, sem IA)."
            if plausivel else
            "Texto parece aleatório ou curto demais (checagem local, sem IA)."
        ),
        sentimento="positivo" if score > 0 else "negativo" if score < 0 else "neutro",
        pilar=pilar,
        temas=[],
    )
