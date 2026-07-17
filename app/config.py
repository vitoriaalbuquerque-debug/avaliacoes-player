"""
Configurações da aplicação, lidas de variáveis de ambiente (.env).
Ver .env.example na raiz do projeto para a lista completa.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Banco de dados — SQLite por padrão (zero instalação, roda em qualquer
    # máquina sem compilar nada). Pra migrar pro piloto, troque só esta linha
    # por uma URL de Postgres (ex: Neon/Supabase) — o SQLAlchemy cuida do resto,
    # não precisa mudar nenhum código.
    database_url: str = "sqlite:///./comer_fora.db"

    # IA — Gemini (mais acessível que outras opções). gemini-2.5-flash-lite é o
    # modelo estável mais barato da geração atual (a família 1.5 foi descontinuada
    # pelo Google em 2026 — não usar gemini-1.5-flash, ele não responde mais).
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    openai_api_key: str = ""  # usado para transcrição via Whisper API

    # Autenticação simples do painel do gerente (trocar por auth real antes do piloto)
    manager_api_key: str = "troque-esta-chave-antes-do-piloto"

    # LGPD — salt usado para hash do CPF (nunca guardamos CPF em texto puro)
    cpf_hash_salt: str = "troque-este-salt-antes-de-qualquer-dado-real"

    # Armazenamento local de áudio (MVP). Trocar por storage de objeto (S3-like) antes do piloto.
    audio_storage_dir: str = "./storage/audio"

    # Janela de retenção de áudio em dias (política de privacidade — LGPD)
    audio_retention_days: int = 30

    # Janela de "cliente ainda no local" usada no alerta em tempo real (minutos)
    on_site_window_minutes: int = 90


settings = Settings()
