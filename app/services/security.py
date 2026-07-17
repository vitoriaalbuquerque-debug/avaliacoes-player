"""
LGPD: o CPF nunca é armazenado em texto puro. Guardamos apenas um hash
determinístico (com salt do servidor) para conseguir reconhecer o mesmo
cliente em visitas futuras, sem guardar o dado sensível em si.

Isso é adequado para o MVP. Antes do piloto com restaurantes reais, validar
esta abordagem com o time jurídico (task da Semana 1 do roadmap).
"""
import hashlib
import re

from app.config import settings


def normalize_cpf(cpf: str) -> str:
    return re.sub(r"\D", "", cpf)


def hash_cpf(cpf: str) -> str:
    digits = normalize_cpf(cpf)
    salted = f"{settings.cpf_hash_salt}:{digits}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()


def is_valid_cpf_format(cpf: str) -> bool:
    """Checagem de formato (11 dígitos), não o dígito verificador real do CPF.
    Suficiente para o MVP — trocar por validação completa antes do piloto."""
    return len(normalize_cpf(cpf)) == 11
