"""
Cálculo de pontos: sempre proporcional ao DETALHE da avaliação, nunca ao
sentimento — uma avaliação negativa bem detalhada vale tanto quanto uma
positiva igualmente detalhada. Isso evita incentivar só review bonzinho.
"""
from datetime import datetime, timedelta
from typing import Optional


def points_for_audio(duration_seconds: int, char_count: Optional[int] = None) -> int:
    points = round(duration_seconds * 1.8)
    if char_count and char_count > 80:
        points += 10
    return min(100, points)


def points_for_text(char_count: int) -> int:
    return min(100, round(char_count * 0.45))


# ---------- Hub modular (comer_fora_experiencia_completa) ----------
# Escala própria, combinável entre módulos (áudio + notas + fotos + texto no
# mesmo atendimento) — por isso os tetos por módulo são mais altos que o
# fluxo único de áudio/texto acima.

def hub_points_audio(duration_seconds: int) -> int:
    return min(200, duration_seconds * 2)


def hub_points_stars(filled_categories: int) -> int:
    return filled_categories * 10


def hub_points_photos(photo_count: int) -> int:
    return min(150, photo_count * 30)


def hub_points_freetext(char_count: int) -> int:
    return min(100, round(char_count * 0.5))


def benefit_for_points(points: int) -> tuple[str, datetime]:
    """Retorna (descrição do benefício, prazo de resgate)."""
    now = datetime.utcnow()
    if points >= 70:
        return "20% de desconto no próximo pedido iFood", now + timedelta(days=7)
    if points >= 40:
        return "Frete grátis no próximo pedido iFood", now + timedelta(days=7)
    return "50 pontos de bônus por participar", now + timedelta(days=30)
