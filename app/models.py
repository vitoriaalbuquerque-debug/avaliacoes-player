import enum
import uuid
from datetime import datetime

from sqlalchemy import (Boolean, Column, DateTime, Enum, Float, ForeignKey,
                         Integer, String, Text)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    tables = relationship("RestaurantTable", back_populates="restaurant")
    reviews = relationship("Review", back_populates="restaurant")
    pdv_orders = relationship("PDVOrder", back_populates="restaurant")


class RestaurantTable(Base):
    __tablename__ = "restaurant_tables"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    restaurant_id = Column(UUID(as_uuid=False), ForeignKey("restaurants.id"), nullable=False)
    number = Column(String, nullable=False)  # ex: "07"
    created_at = Column(DateTime, default=datetime.utcnow)

    restaurant = relationship("Restaurant", back_populates="tables")


class Customer(Base):
    """
    NUNCA guardamos o CPF em texto puro — só o hash (ver services/security.py).
    ifood_customer_id fica pronto para quando a autenticação real (QR logado
    no app iFood) substituir a entrada manual de CPF.
    """
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    cpf_hash = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    ifood_customer_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    reviews = relationship("Review", back_populates="customer")


class Channel(str, enum.Enum):
    """
    De onde a avaliação veio. voz_local/texto_local/estrelas_local/fotos_local
    nascem do nosso próprio app (QR na mesa). Os demais são registrados
    MANUALMENTE pelo gerente por enquanto — sem scraping/integração externa
    (decisão do time). A IA por trás (sentimento, pilar, resposta) é a mesma
    para todos os canais; só a fonte do dado muda.
    """
    voz_local = "voz_local"
    texto_local = "texto_local"
    estrelas_local = "estrelas_local"
    fotos_local = "fotos_local"
    instagram = "instagram"
    google = "google"
    whatsapp = "whatsapp"
    ifood_pedido = "ifood_pedido"


class Pillar(str, enum.Enum):
    comida = "comida"
    bebida = "bebida"
    atendimento = "atendimento"
    tempo_espera = "tempo_espera"
    ambiente = "ambiente"
    geral = "geral"


class Sentiment(str, enum.Enum):
    positivo = "positivo"
    neutro = "neutro"
    negativo = "negativo"


class ReviewStatus(str, enum.Enum):
    draft = "draft"          # gravado/escrito, ainda não confirmado pelo cliente
    received = "received"    # confirmado e contabilizado
    manager_notified = "manager_notified"
    actioned = "actioned"    # gerente marcou que tomou uma ação (métrica-norte)


class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    restaurant_id = Column(UUID(as_uuid=False), ForeignKey("restaurants.id"), nullable=False)
    table_id = Column(UUID(as_uuid=False), ForeignKey("restaurant_tables.id"), nullable=True)
    # Nulo para menções externas (ex: comentário no Instagram) sem CPF vinculado.
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id"), nullable=True)

    channel = Column(Enum(Channel), nullable=False)
    author_label = Column(String, nullable=True)  # ex: "@marina_gourmet", "Pedido #48291"
    external_url = Column(String, nullable=True)   # link pro post/pedido original, se houver
    waiter_name = Column(String, nullable=True)    # garçom associado, se souber (pro placar por garçom)

    raw_text = Column(Text, nullable=False)          # transcrição (editada) ou texto digitado
    audio_path = Column(String, nullable=True)        # caminho do arquivo de áudio, se houver
    duration_seconds = Column(Integer, nullable=True)  # duração real da fala, se áudio
    char_count = Column(Integer, nullable=True)

    sentiment = Column(Enum(Sentiment), nullable=True)
    pillar = Column(Enum(Pillar), nullable=True)
    plausible = Column(Boolean, nullable=True)
    ai_reason = Column(Text, nullable=True)

    points_awarded = Column(Integer, default=0)
    status = Column(Enum(ReviewStatus), default=ReviewStatus.draft)

    created_at = Column(DateTime, default=datetime.utcnow)
    confirmed_at = Column(DateTime, nullable=True)
    actioned_at = Column(DateTime, nullable=True)

    restaurant = relationship("Restaurant", back_populates="reviews")
    customer = relationship("Customer", back_populates="reviews")
    tags = relationship("ReviewTag", back_populates="review")


class ReviewTag(Base):
    __tablename__ = "review_tags"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    review_id = Column(UUID(as_uuid=False), ForeignKey("reviews.id"), nullable=False)
    label = Column(String, nullable=False)

    review = relationship("Review", back_populates="tags")


class RewardRedemption(Base):
    __tablename__ = "reward_redemptions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    customer_id = Column(UUID(as_uuid=False), ForeignKey("customers.id"), nullable=False)
    review_id = Column(UUID(as_uuid=False), ForeignKey("reviews.id"), nullable=False)
    benefit_description = Column(String, nullable=False)
    points_awarded = Column(Integer, nullable=False)
    redeem_by = Column(DateTime, nullable=False)
    redeemed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PDVOrderStatus(str, enum.Enum):
    em_preparo = "em_preparo"
    servido = "servido"
    esperando = "esperando"
    finalizado = "finalizado"


class PDVOrder(Base):
    """
    'PDV-lite': comanda mantida manualmente pelo restaurante (sem integração
    com sistema de PDV real ainda). Existe pra permitir a IA linkar uma
    reclamação a um prato específico — a funcionalidade é real, só a fonte do
    dado é manual até termos uma integração de verdade (Omie/Linx/Totvs/etc).
    """
    __tablename__ = "pdv_orders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    restaurant_id = Column(UUID(as_uuid=False), ForeignKey("restaurants.id"), nullable=False)
    table_id = Column(UUID(as_uuid=False), ForeignKey("restaurant_tables.id"), nullable=True)
    ticket_value = Column(Float, nullable=True)
    status = Column(Enum(PDVOrderStatus), default=PDVOrderStatus.em_preparo)
    items_json = Column(Text, nullable=False)  # lista de itens, serializada como JSON
    waiter_name = Column(String, nullable=True)

    linked_review_id = Column(UUID(as_uuid=False), ForeignKey("reviews.id"), nullable=True)
    ai_confidence = Column(Float, nullable=True)
    ai_link_reason = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    restaurant = relationship("Restaurant", back_populates="pdv_orders")
    linked_review = relationship("Review")


class ReviewResponseDraft(Base):
    """Histórico de respostas que a IA rascunhou para o gerente — nunca enviadas
    automaticamente (ação de enviar mensagem sempre é manual, do gerente)."""
    __tablename__ = "review_response_drafts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    review_id = Column(UUID(as_uuid=False), ForeignKey("reviews.id"), nullable=False)
    tone = Column(String, nullable=False)
    draft_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
