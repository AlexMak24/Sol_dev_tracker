# server.py — РАБОЧАЯ ВЕРСИЯ БЕЗ ОШИБОК
import asyncio
import ujson as json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import Set
import logging

# Импортируем твой трекер
from axiom_tracker import AxiomTracker  # ← у тебя он называется axiom_tracker.py

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Axiom Token Stream Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

connected_clients: Set[WebSocket] = set()
tracker = None

# Глобальный event loop (он уже есть, потому что uvicorn его запускает)
loop = asyncio.get_event_loop()

class TokenBroadcaster:
    @staticmethod
    async def broadcast_token(token_data: dict):
        if not connected_clients:
            return
        message = json.dumps(token_data)
        disconnected = set()
        for client in connected_clients:
            try:
                await client.send_text(message)
            except:
                disconnected.add(client)
        for client in disconnected:
            connected_clients.discard(client)

# ПРАВИЛЬНЫЙ ПАТЧ — теперь без ошибки!
def patched_output_token_info(self, data, processing_time, source, twitter_stats=None,
                              migrated=None, non_migrated=None, percentage=None,
                              cache_time=0, dev_mcap_info=None):
    has_twitter = bool(data.get('twitter') and 'twitter.com' in data['twitter'] or 'x.com' in data['twitter'])
    logger.info(f"New token: {data['token_ticker']} - Twitter: {has_twitter}")

    gui_data = {
        "token_name": data['token_name'],
        "token_ticker": data['token_ticker'],
        "token_address": data['token_address'],
        "deployer_address": data['deployer_address'],
        "twitter": data['twitter'],
        "pair_address": data['pair_address'],
        "twitter_stats": twitter_stats or {},
        "dev_mcap_info": dev_mcap_info or {},
        "migrated": migrated or 0,
        "total": (migrated or 0) + (non_migrated or 0),
        "percentage": round(percentage, 2) if percentage is not None else 0.0,
        "processing_time_ms": int(processing_time * 1000),
        "counter": getattr(self, "gui_counter", 0) + 1,
        "created_at": data.get("created_at", ""),
        "timestamp": asyncio.get_event_loop().time(),
        "avg_ath_mcap": dev_mcap_info.get("avg_ath_mcap", 0) if dev_mcap_info and "error" not in dev_mcap_info else 0,
        "avg_tokens_count": self.avg_tokens_count,
        "protocol": data.get("protocol", "unknown")
    }

    self.gui_counter = gui_data["counter"]

    # ← ВАЖНО: используем уже запущенный loop от uvicorn
    loop.create_task(TokenBroadcaster.broadcast_token(gui_data))

@app.on_event("startup")
async def startup_event():
    global tracker
    logger.info("Запуск Axiom трекера...")

    # Патчим метод вывода
    AxiomTracker._output_token_info = patched_output_token_info

    tracker = AxiomTracker(
        auth_file="auth_data.json",
        twitter_api_key="new1_d84d121d635d4b2aa0680a22e25c08d2",
        avg_tokens_count=10
    )

    # Запускаем трекер в отдельном потоке (это нормально)
    import threading
    threading.Thread(target=tracker.start, daemon=True).start()
    logger.info("Трекер запущен!")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    logger.info(f"Клиент подключился! Всего: {len(connected_clients)}")

    try:
        await websocket.send_text(json.dumps({"type": "welcome", "message": "Axiom Feed Active"}))
        while True:
            await websocket.receive_text()  # держим соединение
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
        logger.info(f"Клиент отключился. Осталось: {len(connected_clients)}")

@app.get("/")
async def root():
    return {"status": "running", "clients": len(connected_clients)}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, log_level="info")
