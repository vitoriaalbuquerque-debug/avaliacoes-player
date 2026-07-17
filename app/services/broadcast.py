"""
Broadcast em memória pra alimentar o SSE (Server-Sent Events) do dashboard —
mesma ideia que a Vitória's parceira usou no backend Node dela. Cada
restaurante tem sua própria lista de "ouvintes" (filas asyncio); toda vez que
uma avaliação nova é fechada, a gente publica nela e todo dashboard conectado
recebe na hora, sem precisar recarregar a página.

Limitação conhecida (ok pro MVP): isso é em memória, então só funciona com um
processo do backend rodando. Múltiplas réplicas em produção vão precisar de
um broker de verdade (Redis pub/sub, por exemplo) — não é o caso agora.
"""
import asyncio
from typing import Dict, List

_listeners: Dict[str, List[asyncio.Queue]] = {}


def subscribe(restaurant_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue()
    _listeners.setdefault(restaurant_id, []).append(queue)
    return queue


def unsubscribe(restaurant_id: str, queue: asyncio.Queue):
    if restaurant_id in _listeners and queue in _listeners[restaurant_id]:
        _listeners[restaurant_id].remove(queue)


async def publish(restaurant_id: str, payload: dict):
    for queue in _listeners.get(restaurant_id, []):
        await queue.put(payload)
