"""WebSocket handler for real-time events."""

import json
import logging
from typing import Dict, Set
from datetime import datetime
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from app.core.auth import JWTManager
from app.core.config import settings
from app.cache.config import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


class WebSocketConnectionManager:
    """Manage WebSocket connections and broadcast events."""
    
    def __init__(self):
        """Initialize connection manager."""
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.sequence_counters: Dict[str, int] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Register a new WebSocket connection."""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
            self.sequence_counters[user_id] = 0
        
        self.active_connections[user_id].add(websocket)
        
        logger.info(
            f"WebSocket connected",
            extra={
                "user_id": user_id,
                "total_connections": len(self.active_connections[user_id]),
            },
        )
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Unregister a WebSocket connection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                if user_id in self.sequence_counters:
                    del self.sequence_counters[user_id]
        
        logger.info(
            f"WebSocket disconnected",
            extra={"user_id": user_id},
        )
    
    def get_next_sequence(self, user_id: str) -> int:
        """Get next sequence number for user."""
        if user_id not in self.sequence_counters:
            self.sequence_counters[user_id] = 0
        
        self.sequence_counters[user_id] += 1
        return self.sequence_counters[user_id]
    
    async def broadcast_to_user(
        self,
        user_id: str,
        event_type: str,
        data: dict,
        trace_id: str = None,
    ):
        """Broadcast event to all connections for a user."""
        if user_id not in self.active_connections:
            return
        
        sequence = self.get_next_sequence(user_id)
        
        event_payload = {
            "type": event_type,
            "sequence": sequence,
            "timestamp": datetime.utcnow().isoformat(),
            "trace_id": trace_id or "N/A",
            "user_id": user_id,
            "data": data,
        }
        
        message = json.dumps(event_payload)
        
        # Send to all connected clients for this user
        disconnected = []
        for websocket in self.active_connections[user_id]:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.warning(
                    f"Failed to send WebSocket message",
                    extra={
                        "user_id": user_id,
                        "event_type": event_type,
                        "error": str(e),
                    },
                )
                disconnected.append(websocket)
        
        # Clean up disconnected sockets
        for websocket in disconnected:
            self.disconnect(websocket, user_id)
        
        logger.debug(
            f"Broadcast event to user",
            extra={
                "user_id": user_id,
                "event_type": event_type,
                "sequence": sequence,
                "recipients": len(self.active_connections.get(user_id, set())),
            },
        )


# Global connection manager
connection_manager = WebSocketConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
):
    """
    WebSocket endpoint for real-time events.
    
    Requires JWT token in query parameter: /ws?token=<jwt>
    
    Events received (user can listen to):
    - approvals:requested - New approval needed
    - approvals:approved - Approval was approved
    - approvals:rejected - Approval was rejected
    - approvals:modified - Approval was modified
    - approvals:expired - Approval timed out
    - tasks:created - Task was created
    - tasks:updated - Task was updated
    - tasks:deleted - Task was deleted
    - tasks:completed - Task was completed
    - chat:message_complete - Chat response ready
    - session:heartbeat - Server heartbeat
    """
    
    # Authenticate token
    try:
        token_payload = JWTManager.verify_token(token)
        user_id = token_payload.sub
    except Exception as e:
        logger.warning(
            f"WebSocket auth failed",
            extra={"error": str(e)},
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return
    
    # Connect
    await connection_manager.connect(websocket, user_id)
    redis_client = get_redis()

    await websocket.send_json(
        {
            "type": "connection:ready",
            "sequence": connection_manager.get_next_sequence(user_id),
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "data": {
                "heartbeat_interval_seconds": settings.websocket_heartbeat_interval_seconds,
                "client_timeout_seconds": settings.websocket_client_timeout_seconds,
                "recommended_reconnect_delay_ms": settings.websocket_reconnect_delay_ms,
            },
        }
    )
    
    # Subscribe to approval events in background
    pub_sub = redis_client.pubsub()
    approval_channel = f"ws:approvals:{user_id}"
    pub_sub.subscribe(approval_channel)
    
    async def listen_for_events():
        """Listen for Redis pub/sub events and forward to WebSocket."""
        try:
            while True:
                # Run blocking Redis read off the event loop.
                message = await asyncio.to_thread(
                    pub_sub.get_message,
                    True,
                    1.0,
                )
                
                if message:
                    try:
                        message_type = message.get("type")
                        if message_type != "message":
                            continue

                        payload = message.get("data")
                        if isinstance(payload, bytes):
                            payload = payload.decode("utf-8")

                        event_data = json.loads(payload)
                        await websocket.send_json(
                            {
                                "type": event_data.get("type", "unknown"),
                                "sequence": connection_manager.get_next_sequence(user_id),
                                "timestamp": datetime.utcnow().isoformat(),
                                "trace_id": event_data.get("trace_id", "N/A"),
                                "user_id": user_id,
                                "data": event_data.get("data", {}),
                            }
                        )
                    except json.JSONDecodeError:
                        logger.error("Failed to parse pub/sub message")
                    except Exception as exc:
                        logger.warning(
                            "Failed to relay websocket pub/sub event",
                            extra={"user_id": user_id, "error": str(exc)},
                        )
        except asyncio.CancelledError:
            pass
        finally:
            await asyncio.to_thread(pub_sub.unsubscribe, approval_channel)
            await asyncio.to_thread(pub_sub.close)

    async def emit_heartbeat():
        """Emit server heartbeats so clients can detect stale sockets and reconnect."""
        interval = max(5, int(settings.websocket_heartbeat_interval_seconds))
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json(
                {
                    "type": "session:heartbeat",
                    "sequence": connection_manager.get_next_sequence(user_id),
                    "timestamp": datetime.utcnow().isoformat(),
                    "user_id": user_id,
                    "data": {
                        "interval_seconds": interval,
                        "recommended_reconnect_delay_ms": settings.websocket_reconnect_delay_ms,
                    },
                }
            )
    
    # Start event listener task
    event_task = asyncio.create_task(listen_for_events())
    heartbeat_task = asyncio.create_task(emit_heartbeat())
    
    try:
        while True:
            # Receive messages from client
            timeout_seconds = max(10, int(settings.websocket_client_timeout_seconds))
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                logger.info(
                    "WebSocket client timed out due to heartbeat inactivity",
                    extra={"user_id": user_id, "timeout_seconds": timeout_seconds},
                )
                await websocket.send_json(
                    {
                        "type": "connection:closing",
                        "sequence": connection_manager.get_next_sequence(user_id),
                        "timestamp": datetime.utcnow().isoformat(),
                        "user_id": user_id,
                        "data": {
                            "reason": "heartbeat_timeout",
                            "recommended_reconnect_delay_ms": settings.websocket_reconnect_delay_ms,
                        },
                    }
                )
                await websocket.close(code=status.WS_1001_GOING_AWAY, reason="Heartbeat timeout")
                break
            
            try:
                message = json.loads(data)
                message_type = message.get("type")
                
                if message_type in {"ping", "heartbeat"}:
                    # Respond to heartbeat
                    await websocket.send_json({
                        "type": "pong",
                        "sequence": connection_manager.get_next_sequence(user_id),
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                else:
                    logger.warning(
                        f"Unknown WebSocket message type",
                        extra={
                            "user_id": user_id,
                            "message_type": message_type,
                        },
                    )
            
            except json.JSONDecodeError:
                logger.warning(
                    f"Invalid JSON in WebSocket message",
                    extra={"user_id": user_id},
                )
    
    except WebSocketDisconnect:
        pass
    
    finally:
        event_task.cancel()
        heartbeat_task.cancel()
        await asyncio.gather(event_task, heartbeat_task, return_exceptions=True)
        connection_manager.disconnect(websocket, user_id)
