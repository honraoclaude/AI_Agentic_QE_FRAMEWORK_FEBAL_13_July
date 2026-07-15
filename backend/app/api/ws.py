from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..services.ws import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Client messages are ignored; the socket is server-push only.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
