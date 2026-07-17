"""
Transcrição de áudio via Whisper API (OpenAI).

Trocar de provedor é só trocar esta função — o resto do app não precisa saber
qual serviço de STT está por trás.
"""
import httpx

from app.config import settings

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


async def transcribe_audio(file_bytes: bytes, filename: str = "audio.webm") -> str:
    if not settings.openai_api_key:
        # Sem chave configurada: não quebra o fluxo, mas deixa claro que é um placeholder.
        return (
            "[transcrição indisponível — configure OPENAI_API_KEY no .env para "
            "ativar a transcrição real via Whisper]"
        )

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            WHISPER_URL,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            files={"file": (filename, file_bytes, "audio/webm")},
            data={"model": "whisper-1", "language": "pt"},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("text", "").strip()
