from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.schemas.realtime import WebSocketEvent

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/realtime")
async def realtime_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id = f"session-{int(datetime.utcnow().timestamp())}"

    accepted = WebSocketEvent(
        event="connection.accepted",
        payload={"session_id": session_id, "protocol": "ai-assistant.v1"},
    )
    await websocket.send_json(accepted.model_dump(mode="json"))

    try:
        while True:
            incoming = await websocket.receive_json()
            event_name = incoming.get("event", "heartbeat")
            payload = incoming.get("payload", {})

            response = WebSocketEvent(
                event="agent.status",
                payload={
                    "received_event": event_name,
                    "received_payload": payload,
                    "status": "acknowledged",
                },
            )
            await websocket.send_json(response.model_dump(mode="json"))
    except WebSocketDisconnect:
        return
