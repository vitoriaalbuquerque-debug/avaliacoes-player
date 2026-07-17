from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ---------- Clientes ----------

class CustomerLookupRequest(BaseModel):
    cpf: str
    table_number: str
    restaurant_id: str


class CustomerLookupResponse(BaseModel):
    customer_id: str
    name: Optional[str]
    is_new: bool
    table_id: str


# ---------- Análise de IA (compartilhado entre áudio e texto) ----------

class AIAnalysis(BaseModel):
    plausivel: bool
    motivo: str
    sentimento: str  # positivo | neutro | negativo
    pilar: str = "geral"  # comida | bebida | atendimento | tempo_espera | ambiente | geral
    temas: List[str] = []


# ---------- Fluxo de áudio (grava -> transcreve -> confirma) ----------

class AudioTranscribeResponse(BaseModel):
    review_id: str
    transcript: str


class ReviewAnalyzeRequest(BaseModel):
    edited_text: str


class ReviewAnalyzeResponse(BaseModel):
    review_id: str
    analysis: AIAnalysis
    points_estimate: int


class ReviewConfirmResponse(BaseModel):
    review_id: str
    points_awarded: int
    benefit_description: str
    redeem_by: datetime
    sentiment: str
    manager_notified: bool


# ---------- Fluxo de texto ----------

class TextReviewRequest(BaseModel):
    restaurant_id: str
    table_id: str
    customer_id: str
    text: str


class TextReviewRejected(BaseModel):
    accepted: bool = False
    motivo: str


# ---------- Painel do gerente ----------

class ReviewOut(BaseModel):
    id: str
    customer_name: Optional[str]
    channel: str
    author_label: Optional[str]
    external_url: Optional[str]
    raw_text: str
    sentiment: Optional[str]
    pillar: Optional[str]
    points_awarded: int
    status: str
    created_at: datetime
    tags: List[str] = []

    model_config = ConfigDict(from_attributes=True)


class DashboardSummary(BaseModel):
    total_reviews_today: int
    average_sentiment_score: float
    percent_actioned: float
    points_distributed_today: int
    on_site_alert: Optional[dict] = None


# ---------- Feed multi-canal (menções externas lançadas manualmente) ----------

class ExternalFeedbackRequest(BaseModel):
    restaurant_id: str
    channel: str  # instagram | google | whatsapp | ifood_pedido
    author_label: str
    text: str
    external_url: Optional[str] = None
    waiter_name: Optional[str] = None


# ---------- PDV-lite ----------

class PDVOrderIn(BaseModel):
    restaurant_id: str
    table_id: Optional[str] = None
    ticket_value: Optional[float] = None
    status: str = "em_preparo"
    items: List[str]
    waiter_name: Optional[str] = None


class PDVOrderOut(BaseModel):
    id: str
    table_id: Optional[str]
    ticket_value: Optional[float]
    status: str
    items: List[str]
    waiter_name: Optional[str]
    linked_review_id: Optional[str]
    ai_confidence: Optional[float]
    ai_link_reason: Optional[str]
    created_at: datetime


class SuggestLinkCandidate(BaseModel):
    order_id: str
    confidence: float
    reason: str


class SuggestLinkResponse(BaseModel):
    candidates: List[SuggestLinkCandidate]


# ---------- Rascunho de resposta com IA ----------

class GenerateResponseRequest(BaseModel):
    tone: str  # friendly | apologetic | professional | assertive


class GenerateResponseResponse(BaseModel):
    review_id: str
    tone: str
    draft_text: str


# ---------- Preview de IA (sem persistir — usado enquanto o cliente digita/grava) ----------

class AnalyzePreviewRequest(BaseModel):
    text: str


# ---------- Hub modular (comer_fora_experiencia_completa): múltiplos módulos,
# CPF confirmado só no final, um único fechamento ----------

class HubSubmitRequest(BaseModel):
    restaurant_id: str
    table_number: str
    cpf: Optional[str] = None  # None/omitido = anônimo (sem pontos, sem CRM)
    waiter_name: Optional[str] = None

    audio_transcript: Optional[str] = None
    audio_duration_seconds: Optional[int] = None

    stars_avg: Optional[float] = None
    stars_filled_categories: Optional[int] = None

    photos_count: Optional[int] = None

    freetext: Optional[str] = None


class HubSubmitResponse(BaseModel):
    total_points: int
    benefit_description: str
    redeem_by: Optional[datetime]
    overall_sentiment: str
    manager_notified: bool
    anonymous: bool


# ---------- Pilares e ISR ----------

class PillarScore(BaseModel):
    pillar: str
    score_pct: float
    review_count: int


class PillarsSummary(BaseModel):
    pillars: List[PillarScore]


class ISRResponse(BaseModel):
    isr: float
    components: dict


# ---------- Compatibilidade com o dashboard React (comer-fora-dashboard-react) ----------
# Formatos espelhando exatamente src/types.ts do projeto React, pra não precisar
# reescrever a UI dela — só trocar de onde o dado vem.

class WaiterScoreOut(BaseModel):
    name: str
    rating: float
    atendimentos: int
    feedbacks: int
    statusBadge: Optional[str] = None
    avatarText: str


class ReactStatsOut(BaseModel):
    restaurantName: str
    isr: float
    nps: float
    averageStars: float
    evaluationsToday: int
    averageResponseTimeMinutes: float
    channelDistribution: dict
    waiters: List[WaiterScoreOut]
    pillars: dict


class ReactOrderOut(BaseModel):
    mesa: str
    garcom: str
    pratos: List[str]
    status: str
    tempo: str


class ReactAlertOut(BaseModel):
    id: str
    emoji: str
    sentiment: str
    score: int
    mesa: str
    garcom: str
    prato: str
    reviewText: str
    originalText: str
    level: str
    aiSuggestion: str
    tags: List[str] = []


# ---------- Copiloto (perguntas livres sobre os dados do restaurante) ----------

class CopilotRequest(BaseModel):
    question: str


class CopilotResponse(BaseModel):
    answer: str
