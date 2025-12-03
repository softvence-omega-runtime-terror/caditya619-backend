# app/routes/websocket_endpoints.py
"""
Production-grade WebSocket endpoints
Separate endpoints for 3 purposes and 4 client types
"""

from fastapi import APIRouter, WebSocket, Depends
from starlette.websockets import WebSocketDisconnect
from app.utils.websocket_manager import manager, ConnectionPurpose, ClientType
from app.redis import get_redis
import json
import logging
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter(tags=['WebSocket'])


# ============================================================================
# PURPOSE 1: LOCATION_SEND
# ============================================================================


@router.get("/test/")
async def test(customer_id: str, rider_id: str, order_id: str):
    await manager.send_notification(
        to_type="customers",
        to_id=str(customer_id),
        title="Order Accepted!",
        body=f"Rider with ID {rider_id} has accepted your order",
        data={"order_id": str(order_id), "rider_id": str(rider_id)},
        urgency="high"
    )
    return {"message": "Test successful!"}

@router.websocket("/ws/location/{client_type}/{user_id}")
async def location_endpoint(
    websocket: WebSocket,
    client_type: str,
    user_id: str,
    redis = Depends(get_redis)
):
    """
    Location tracking endpoint
    
    Riders broadcast location, customers receive updates
    
    ws://localhost:8000/ws/location/riders/123         # Rider sending location
    ws://localhost:8000/ws/location/customers/456      # Customer receiving location
    
    Message format (from rider):
    {"lat": 40.7128, "lng": -74.0060}
    
    Message sent to customers:
    {
        "type": "location_send",
        "rider_id": "123",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "timestamp": "2025-12-03T...",
        "accuracy": 10.5,
        "speed": 25.3
    }
    """
    
    # Validate client type
    valid_types = {ClientType.RIDERS.value, ClientType.CUSTOMERS.value}
    if client_type not in valid_types:
        await websocket.close(code=4000, reason="Invalid client type for location")
        return
    
    # Connect to manager
    connected = await manager.connect(
        websocket,
        client_type,
        user_id,
        ConnectionPurpose.LOCATION_SEND.value
    )
    
    if not connected:
        return
    
    try:
        if client_type == ClientType.RIDERS.value:
            # === RIDER: Send location ===
            while True:
                data = await websocket.receive_json()
                
                lat = data.get("latitude") or data.get("lat")
                lng = data.get("longitude") or data.get("lng")
                
                if lat is None or lng is None:
                    await websocket.send_json({"error": "Missing latitude/longitude"})
                    continue
                
                # Broadcast to customers tracking this rider
                results = await manager.send_location_update(
                    user_id,
                    lat,
                    lng,
                    additional_data={
                        "accuracy": data.get("accuracy"),
                        "speed": data.get("speed"),
                        "heading": data.get("heading")
                    }
                )
                
                # Publish to Redis for analytics/persistence
                await redis.publish("rider_locations", json.dumps({
                    "rider_id": user_id,
                    "lat": lat,
                    "lng": lng,
                    "timestamp": data.get("timestamp")
                }))
                
                logger.debug(f"Location update from rider {user_id}: {len(results)} customers notified")
        
        else:
            # === CUSTOMER: Receive location ===
            # Extract rider_id from message or keep connection alive
            while True:
                try:
                    data = await websocket.receive_json()
                    
                    # Customer can subscribe/unsubscribe to rider location
                    action = data.get("action")  # "subscribe" or "unsubscribe"
                    rider_id = data.get("rider_id")
                    
                    if action == "subscribe" and rider_id:
                        manager.add_location_subscriber(rider_id, user_id)
                        await websocket.send_json({
                            "type": "subscription",
                            "status": "subscribed",
                            "rider_id": rider_id
                        })
                    
                    elif action == "unsubscribe" and rider_id:
                        manager.remove_location_subscriber(rider_id, user_id)
                        await websocket.send_json({
                            "type": "subscription",
                            "status": "unsubscribed",
                            "rider_id": rider_id
                        })
                except asyncio.TimeoutError:
                    continue
    
    except WebSocketDisconnect:
        manager.disconnect(client_type, user_id, ConnectionPurpose.LOCATION_SEND.value)
        logger.info(f"Location connection closed: {client_type}:{user_id}")
    
    except Exception as e:
        logger.error(f"Location error: {str(e)}")
        manager.disconnect(client_type, user_id, ConnectionPurpose.LOCATION_SEND.value)


# ============================================================================
# PURPOSE 2: MESSAGING
# ============================================================================

@router.websocket("/ws/chat/{client_type}/{user_id}")
async def chat_endpoint(
    websocket: WebSocket,
    client_type: str,
    user_id: str,
    redis = Depends(get_redis)
):
    """
    Direct messaging between users
    
    All 4 client types can message each other
    
    ws://localhost:8000/ws/chat/riders/123
    ws://localhost:8000/ws/chat/customers/456
    ws://localhost:8000/ws/chat/vendors/789
    ws://localhost:8000/ws/chat/admins/999
    
    Message format:
    {
        "to_type": "customers",
        "to_id": "456",
        "text": "Hello!"
    }
    
    Received message:
    {
        "type": "messaging",
        "from_type": "riders",
        "from_id": "123",
        "from_name": "John Rider",
        "text": "Hello!",
        "timestamp": "2025-12-03T...",
        "message_id": "uuid"
    }
    """
    
    # Validate client type
    valid_types = {
        ClientType.RIDERS.value,
        ClientType.CUSTOMERS.value,
        ClientType.VENDORS.value,
        ClientType.ADMINS.value
    }
    if client_type not in valid_types:
        await websocket.close(code=4000, reason="Invalid client type")
        return
    
    # Connect to manager
    connected = await manager.connect(
        websocket,
        client_type,
        user_id,
        ConnectionPurpose.MESSAGING.value
    )
    
    if not connected:
        return
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # Extract message details
            to_type = data.get("to_type")
            to_id = data.get("to_id")
            text = data.get("text", "").strip()
            from_name = data.get("from_name", str(user_id))
            
            # Validate input
            if not text or not to_type or not to_id:
                await websocket.send_json({
                    "error": "Missing required fields",
                    "required": ["to_type", "to_id", "text"]
                })
                continue
            
            to_id = str(to_id)
            
            # Check if active chat exists
            if not manager.is_chatting_with(client_type, user_id, to_type, to_id):
                await websocket.send_json({
                    "error": "No active chat with this user",
                    "hint": "Start a chat first using the API endpoint"
                })
                continue
            
            # Send message
            success = await manager.send_message(
                client_type,
                user_id,
                to_type,
                to_id,
                text,
                from_name
            )
            
            if success:
                # Publish to Redis for analytics
                await redis.publish(f"chat:{to_type}:{to_id}", json.dumps({
                    "from_type": client_type,
                    "from_id": user_id,
                    "text": text
                }))
                
                await websocket.send_json({"status": "sent"})
            else:
                await websocket.send_json({"error": "Failed to send message"})
    
    except WebSocketDisconnect:
        manager.disconnect(client_type, user_id, ConnectionPurpose.MESSAGING.value)
        logger.info(f"Chat connection closed: {client_type}:{user_id}")
    
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        manager.disconnect(client_type, user_id, ConnectionPurpose.MESSAGING.value)


# ============================================================================
# PURPOSE 3: NOTIFICATIONS
# ============================================================================

@router.websocket("/ws/notifications/{client_type}/{user_id}")
async def notifications_endpoint(
    websocket: WebSocket,
    client_type: str,
    user_id: str,
    redis = Depends(get_redis)
):
    """
    Real-time notifications
    
    All client types receive notifications
    
    ws://localhost:8000/ws/notifications/riders/123
    ws://localhost:8000/ws/notifications/customers/456
    ws://localhost:8000/ws/notifications/vendors/789
    ws://localhost:8000/ws/notifications/admins/999
    
    Notification message:
    {
        "type": "notifications",
        "title": "Order Update",
        "body": "Your order has been accepted",
        "data": {"order_id": "12345"},
        "urgency": "normal",
        "timestamp": "2025-12-03T...",
        "notification_id": "uuid"
    }
    """
    
    # Validate client type
    valid_types = {
        ClientType.RIDERS.value,
        ClientType.CUSTOMERS.value,
        ClientType.VENDORS.value,
        ClientType.ADMINS.value
    }
    if client_type not in valid_types:
        await websocket.close(code=4000, reason="Invalid client type")
        return
    
    # Connect to manager
    connected = await manager.connect(
        websocket,
        client_type,
        user_id,
        ConnectionPurpose.NOTIFICATIONS.value
    )
    
    if not connected:
        return
    
    try:
        # Notification connections are mostly receive-only
        # Keep alive while receiving
        while True:
            try:
                # Timeout to detect disconnects
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=300.0  # 5 minute timeout
                )
                
                # Optionally handle ping/pong
                if data:
                    try:
                        msg = json.loads(data)
                        if msg.get("type") == "pong":
                            logger.debug(f"Pong from {client_type}:{user_id}")
                    except json.JSONDecodeError:
                        pass
            
            except asyncio.TimeoutError:
                # Periodically send ping
                try:
                    await websocket.send_json({
                        "type": "ping",
                        "timestamp": json.dumps({"__datetime": "now"})
                    })
                except:
                    break
    
    except WebSocketDisconnect:
        manager.disconnect(client_type, user_id, ConnectionPurpose.NOTIFICATIONS.value)
        logger.info(f"Notification connection closed: {client_type}:{user_id}")
    
    except Exception as e:
        logger.error(f"Notification error: {str(e)}")
        manager.disconnect(client_type, user_id, ConnectionPurpose.NOTIFICATIONS.value)


# ============================================================================
# MANAGEMENT ENDPOINTS (HTTP)
# ============================================================================

@router.post("/chat/start/{from_type}/{from_id}/{to_type}/{to_id}")
async def start_chat(from_type: str, from_id: str, to_type: str, to_id: str):
    """Start a new chat between two users"""
    success = manager.start_chat(from_type, from_id, to_type, to_id)
    if success:
        return {"status": "chat_started"}
    return {"error": "Failed to start chat"}


@router.post("/chat/end/{from_type}/{from_id}/{to_type}/{to_id}")
async def end_chat(from_type: str, from_id: str, to_type: str, to_id: str):
    """End a chat between two users"""
    success = manager.end_chat(from_type, from_id, to_type, to_id)
    if success:
        return {"status": "chat_ended"}
    return {"error": "Failed to end chat"}


@router.get("/chat/partners/{client_type}/{user_id}")
async def get_chat_partners(client_type: str, user_id: str):
    """Get all active chat partners for a user"""
    partners = manager.get_chat_partners(client_type, user_id)
    return {"partners": [{"type": t, "id": id} for t, id in partners]}


@router.get("/location/subscribers/{rider_id}")
async def get_location_subscribers(rider_id: str):
    """Get all customers tracking a rider"""
    subscribers = manager.get_location_subscribers(rider_id)
    return {"rider_id": rider_id, "subscribers": list(subscribers)}


@router.get("/stats")
async def get_stats():
    """Get connection statistics"""
    return manager.get_stats()


@router.get("/active-users")
async def get_active_users(client_type: str = None, purpose: str = None):
    """Get list of active users"""
    return manager.get_active_users(client_type, purpose)


@router.post("/notifications/send/{to_type}/{to_id}")
async def send_notification(
    to_type: str,
    to_id: str,
    title: str,
    body: str,
    data: dict = None,
    urgency: str = "normal"
):
    """Send a notification to a user"""
    success = await manager.send_notification(
        to_type,
        to_id,
        title,
        body,
        data,
        urgency
    )
    if success:
        return {"status": "notification_sent"}
    return {"error": "Failed to send notification"}


@router.post("/notifications/broadcast/{to_type}")
async def broadcast_notification(
    to_type: str,
    title: str,
    body: str,
    data: dict = None,
    urgency: str = "normal"
):
    """Broadcast a notification to all users of a type"""
    results = await manager.broadcast_notification(
        to_type,
        title,
        body,
        data,
        urgency
    )
    return {
        "status": "broadcast_sent",
        "total": len(results),
        "successful": sum(1 for v in results.values() if v)
    }