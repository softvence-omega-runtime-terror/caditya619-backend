# from typing import Dict, Set, Optional
# from fastapi import WebSocket
# from collections import defaultdict


# # app/utils/websocket_manager.py


# class ConnectionManager:
#     def __init__(self):
#         self.connections: Dict[str, Dict[str, WebSocket]] = {
#             "riders": {}, "customers": {}, "vendors": {}
#         }

#         # NEW: Which customers are tracking which rider
#         # Format: rider_id -> set(customer_id)
#         self.rider_to_customers: Dict[str, Set[str]] = defaultdict(set)
        
#         # Reverse: customer_id -> rider_id (for cleanup)
#         self.customer_to_rider: Dict[str, str] = {}
#         self.active_chats: Dict[str, Set[str]] = {}

#     async def connect(self, websocket: WebSocket, client_type: str, user_id: str):
#         await websocket.accept()
#         if client_type not in self.connections:
#             raise ValueError("Invalid client_type")
#         self.connections[client_type][user_id] = websocket
#         print(f"Connected {client_type} {user_id}")
#         print(f"Current connections: {self.connections}")

#     def disconnect(self, client_type: str, user_id: str):
#         if client_type in self.connections and user_id in self.connections[client_type]:
#             del self.connections[client_type][user_id]

#         # If customer disconnects → remove from tracking
#         if client_type == "customers" and user_id in self.customer_to_rider:
#             rider_id = self.customer_to_rider.pop(user_id)
#             self.rider_to_customers[rider_id].discard(user_id)

#         # If rider disconnects → clear all tracking
#         if client_type == "riders":
#             if user_id in self.rider_to_customers:
#                 del self.rider_to_customers[user_id]
#             # Remove reverse mappings
#             to_remove = [cid for cid, rid in self.customer_to_rider.items() if rid == user_id]
#             for cid in to_remove:
#                 self.customer_to_rider.pop(cid, None)

#     def get_socket(self, client_type: str, user_id: str) -> Optional[WebSocket]:
#         print(f"Getting socket for {client_type} {user_id}")
#         connetions = self.connections.get(client_type, {}).get(user_id)
#         print(f"Connections found: {connetions}")
#         return connetions                  #self.connections.get(client_type, {}).get(user_id)

#     async def send_to(self, message: dict, client_type: str, user_id: str):
#         print(f"Attempting to send to {client_type} {user_id}")
#         ws = self.get_socket(client_type, user_id)
#         if ws:
#             print(f"Found websocket for {client_type} {user_id}, sending message.")
#             try:
#                 print(f"Sending message to {client_type} {user_id}: {message}")
#                 await ws.send_json(message)
#             except:
#                 self.disconnect(client_type, user_id)

#     async def broadcast_to_type(self, message: dict, client_type: str):
#         for user_id, ws in self.connections.get(client_type, {}).items():
#             try:
#                 await ws.send_json(message)
#             except:
#                 self.disconnect(client_type, user_id)

#     # NEW: Add customer to rider's tracking list
#     def add_tracking(self, rider_id: str, customer_id: str):
#         print(f"Customer {customer_id} is now tracking Rider {rider_id}")
#         self.rider_to_customers[rider_id].add(customer_id)
#         self.customer_to_rider[customer_id] = rider_id

#     # NEW: Send location only to customers tracking this rider
#     async def send_location_to_tracking_customers(self, rider_id: str, location_data: dict):
#         customer_ids = self.rider_to_customers.get(rider_id, set())
#         for customer_id in customer_ids:
#             await self.send_to(location_data, "customers", customer_id)


#     def start_chat(self, from_type: str, from_id: str, to_type: str, to_id: str):
#         from_key = f"{from_type}:{from_id}"
#         to_key = f"{to_type}:{to_id}"

#         # Initialize sets
#         self.active_chats.setdefault(from_key, set())
#         self.active_chats.setdefault(to_key, set())

#         # Add bidirectional link
#         self.active_chats[from_key].add(to_key)
#         self.active_chats[to_key].add(from_key)

#     def get_partners(self, from_type: str, from_id: str) -> Set[tuple[str, str]]:
#         key = f"{from_type}:{from_id}"
#         partners = self.active_chats.get(key, set())
#         result = set()
#         for p in partners:
#             p_type, p_id = p.split(":", 1)
#             result.add((p_type, p_id))
#         return result

#     def end_chat(self, from_type: str, from_id: str, to_type: str, to_id: str):
#         from_key = f"{from_type}:{from_id}"
#         to_key = f"{to_type}:{to_id}"
#         if from_key in self.active_chats:
#             self.active_chats[from_key].discard(to_key)
#         if to_key in self.active_chats:
#             self.active_chats[to_key].discard(from_key)

#     def is_chatting_with(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
#         key = f"{from_type}:{from_id}"
#         partner_key = f"{to_type}:{to_id}"
#         return partner_key in self.active_chats.get(key, set())



# manager = ConnectionManager()


# app/utils/websocket_manager_v2.py
"""
Production-grade WebSocket Manager
3 Purposes: LOCATION_SEND, MESSAGING, NOTIFICATIONS
4 Client Types: VENDORS, CUSTOMERS, RIDERS, ADMINS (optional)
"""

import asyncio
import json
import logging
from typing import Dict, Set, Optional, Tuple, List
from fastapi import WebSocket
from collections import defaultdict
from datetime import datetime
from enum import Enum
import uuid

logger = logging.getLogger(__name__)


class ConnectionPurpose(str, Enum):
    """Message purposes - prevents cross-contamination"""
    LOCATION_SEND = "location_send"
    MESSAGING = "messaging"
    NOTIFICATIONS = "notifications"


class ClientType(str, Enum):
    """Valid client types"""
    VENDORS = "vendors"
    CUSTOMERS = "customers"
    RIDERS = "riders"
    ADMINS = "admins"


class WSConnection:
    """Represents a single WebSocket connection with metadata"""
    
    def __init__(self, websocket: WebSocket, client_type: str, user_id: str, purpose: str):
        self.websocket = websocket
        self.client_type = client_type
        self.user_id = user_id
        self.purpose = purpose
        self.connected_at = datetime.utcnow()
        self.last_message_at = datetime.utcnow()
        self.message_count = 0
        self.is_active = True
        self.connection_id = str(uuid.uuid4())
    
    async def send_json(self, data: dict) -> bool:
        """Send JSON data through WebSocket"""
        try:
            await self.websocket.send_json(data)
            self.last_message_at = datetime.utcnow()
            self.message_count += 1
            return True
        except Exception as e:
            logger.error(f"Failed to send JSON: {str(e)}")
            self.is_active = False
            return False
    
    def to_dict(self) -> dict:
        """Serialize connection metadata"""
        return {
            "connection_id": self.connection_id,
            "client_type": self.client_type,
            "user_id": self.user_id,
            "purpose": self.purpose,
            "connected_at": self.connected_at.isoformat(),
            "last_message_at": self.last_message_at.isoformat(),
            "message_count": self.message_count
        }


class ProductionConnectionManager:
    """
    Enterprise-grade connection manager for multi-user, multi-purpose WebSocket connections
    
    Structure:
    connections[purpose][client_type][user_id] = WSConnection
    
    Examples:
    - Location tracking: connections[LOCATION_SEND][RIDERS][123]
    - Messaging: connections[MESSAGING][CUSTOMERS][456]
    - Notifications: connections[NOTIFICATIONS][VENDORS][789]
    """
    
    def __init__(self):
        # Main connection store: purpose -> client_type -> user_id -> WSConnection
        self.connections: Dict[str, Dict[str, Dict[str, WSConnection]]] = {
            ConnectionPurpose.LOCATION_SEND.value: {
                ClientType.RIDERS.value: {},
                ClientType.CUSTOMERS.value: {},
                ClientType.VENDORS.value: {},
                ClientType.ADMINS.value: {}
            },
            ConnectionPurpose.MESSAGING.value: {
                ClientType.RIDERS.value: {},
                ClientType.CUSTOMERS.value: {},
                ClientType.VENDORS.value: {},
                ClientType.ADMINS.value: {}
            },
            ConnectionPurpose.NOTIFICATIONS.value: {
                ClientType.RIDERS.value: {},
                ClientType.CUSTOMERS.value: {},
                ClientType.VENDORS.value: {},
                ClientType.ADMINS.value: {}
            }
        }
        
        # Location tracking: rider_id -> set(customer_ids watching)
        self.rider_location_subscribers: Dict[str, Set[str]] = defaultdict(set)
        self.customer_tracking_rider: Dict[str, str] = {}  # customer_id -> rider_id
        
        # Active chats: "type:id" -> set("type:id") (bidirectional)
        self.active_chats: Dict[str, Set[str]] = defaultdict(set)
        
        # Heartbeat tasks
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        client_type: str,
        user_id: str,
        purpose: str,
        username: Optional[str] = None
    ) -> bool:
        """
        Accept and register a new WebSocket connection
        
        Args:
            websocket: FastAPI WebSocket
            client_type: "riders", "customers", "vendors", "admins"
            user_id: User identifier
            purpose: "location_send", "messaging", "notifications"
            username: Optional display name
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate inputs
            if client_type not in [ct.value for ct in ClientType]:
                logger.error(f"Invalid client_type: {client_type}")
                await websocket.close(code=4000, reason="Invalid client type")
                return False
            
            if purpose not in [cp.value for cp in ConnectionPurpose]:
                logger.error(f"Invalid purpose: {purpose}")
                await websocket.close(code=4001, reason="Invalid purpose")
                return False
            
            # Accept connection
            await websocket.accept()
            
            # Create connection object
            conn = WSConnection(websocket, client_type, str(user_id), purpose)
            
            # Store connection
            self.connections[purpose][client_type][str(user_id)] = conn
            
            logger.info(
                f"✓ Connected: {client_type}:{user_id} (Purpose: {purpose}) "
                f"[ID: {conn.connection_id}]"
            )
            
            # Start heartbeat for long-lived connections
            await self._start_heartbeat(purpose, client_type, str(user_id))
            
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            return False
    
    def disconnect(self, client_type: str, user_id: str, purpose: Optional[str] = None) -> None:
        """
        Disconnect a user from one or all purposes
        
        Args:
            client_type: Client type
            user_id: User ID
            purpose: Specific purpose to disconnect, or None for all
        """
        try:
            user_id = str(user_id)
            
            if purpose:
                # Disconnect from specific purpose
                if (purpose in self.connections and 
                    client_type in self.connections[purpose] and
                    user_id in self.connections[purpose][client_type]):
                    
                    del self.connections[purpose][client_type][user_id]
                    
                    # Cancel heartbeat
                    task_key = f"{purpose}:{client_type}:{user_id}"
                    if task_key in self.heartbeat_tasks:
                        self.heartbeat_tasks[task_key].cancel()
                        del self.heartbeat_tasks[task_key]
                    
                    logger.info(f"✗ Disconnected: {client_type}:{user_id} (Purpose: {purpose})")
            else:
                # Disconnect from ALL purposes
                for p in [ConnectionPurpose.LOCATION_SEND.value,
                         ConnectionPurpose.MESSAGING.value,
                         ConnectionPurpose.NOTIFICATIONS.value]:
                    if p in self.connections and client_type in self.connections[p]:
                        if user_id in self.connections[p][client_type]:
                            del self.connections[p][client_type][user_id]
                            
                            task_key = f"{p}:{client_type}:{user_id}"
                            if task_key in self.heartbeat_tasks:
                                self.heartbeat_tasks[task_key].cancel()
                                del self.heartbeat_tasks[task_key]
            
            # Cleanup location tracking if customer disconnects
            if client_type == ClientType.CUSTOMERS.value and user_id in self.customer_tracking_rider:
                rider_id = self.customer_tracking_rider.pop(user_id)
                self.rider_location_subscribers[rider_id].discard(user_id)
            
            # Cleanup location tracking if rider disconnects
            if client_type == ClientType.RIDERS.value:
                if user_id in self.rider_location_subscribers:
                    del self.rider_location_subscribers[user_id]
                
                # Remove reverse mappings
                to_remove = [cid for cid, rid in self.customer_tracking_rider.items() if rid == user_id]
                for cid in to_remove:
                    self.customer_tracking_rider.pop(cid, None)
            
            # Cleanup chats
            key = f"{client_type}:{user_id}"
            if key in self.active_chats:
                for partner_key in self.active_chats[key]:
                    if partner_key in self.active_chats:
                        self.active_chats[partner_key].discard(key)
                del self.active_chats[key]
                
        except Exception as e:
            logger.error(f"Disconnect error: {str(e)}")
    
    def get_connection(
        self,
        client_type: str,
        user_id: str,
        purpose: str
    ) -> Optional[WSConnection]:
        """Get a specific connection"""
        try:
            return self.connections.get(purpose, {}).get(client_type, {}).get(str(user_id))
        except Exception as e:
            logger.error(f"Error getting connection: {str(e)}")
            return None
    
    async def send_to(
        self,
        message: dict,
        client_type: str,
        user_id: str,
        purpose: str
    ) -> bool:
        """Send message to a specific user for a specific purpose"""
        try:
            conn = self.get_connection(client_type, user_id, purpose)
            if conn and conn.is_active:
                success = await conn.send_json(message)
                if not success:
                    self.disconnect(client_type, user_id, purpose)
                return success
            return False
        except Exception as e:
            logger.error(f"Send failed: {str(e)}")
            return False
    
    async def broadcast_to_type(
        self,
        message: dict,
        client_type: str,
        purpose: str
    ) -> Dict[str, bool]:
        """Broadcast to all users of a specific client type for a purpose"""
        results = {}
        try:
            users = self.connections.get(purpose, {}).get(client_type, {})
            for user_id, conn in list(users.items()):
                if conn.is_active:
                    results[user_id] = await conn.send_json(message)
                    if not results[user_id]:
                        self.disconnect(client_type, user_id, purpose)
        except Exception as e:
            logger.error(f"Broadcast failed: {str(e)}")
        return results
    
    # ============================================================
    # LOCATION_SEND Purpose Methods
    # ============================================================
    
    def add_location_subscriber(self, rider_id: str, customer_id: str) -> None:
        """Customer starts tracking rider's location"""
        rider_id = str(rider_id)
        customer_id = str(customer_id)
        self.rider_location_subscribers[rider_id].add(customer_id)
        self.customer_tracking_rider[customer_id] = rider_id
        logger.info(f"Location tracking: Customer {customer_id} -> Rider {rider_id}")
    
    def remove_location_subscriber(self, rider_id: str, customer_id: str) -> None:
        """Customer stops tracking rider's location"""
        rider_id = str(rider_id)
        customer_id = str(customer_id)
        self.rider_location_subscribers[rider_id].discard(customer_id)
        self.customer_tracking_rider.pop(customer_id, None)
    
    async def send_location_update(
        self,
        rider_id: str,
        latitude: float,
        longitude: float,
        additional_data: Optional[dict] = None
    ) -> Dict[str, bool]:
        """Send location to all customers tracking this rider"""
        rider_id = str(rider_id)
        customers = self.rider_location_subscribers.get(rider_id, set())
        
        message = {
            "type": ConnectionPurpose.LOCATION_SEND.value,
            "rider_id": rider_id,
            "latitude": latitude,
            "longitude": longitude,
            "timestamp": datetime.utcnow().isoformat(),
            **(additional_data or {})
        }
        
        results = {}
        for customer_id in customers:
            results[customer_id] = await self.send_to(
                message,
                ClientType.CUSTOMERS.value,
                customer_id,
                ConnectionPurpose.LOCATION_SEND.value
            )
        
        return results
    
    def get_location_subscribers(self, rider_id: str) -> Set[str]:
        """Get all customers tracking this rider"""
        return self.rider_location_subscribers.get(str(rider_id), set())
    
    # ============================================================
    # MESSAGING Purpose Methods
    # ============================================================
    
    def start_chat(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
        """Start bidirectional chat between two users"""
        try:
            from_key = f"{from_type}:{from_id}"
            to_key = f"{to_type}:{to_id}"
            
            self.active_chats[from_key].add(to_key)
            self.active_chats[to_key].add(from_key)
            
            logger.info(f"Chat started: {from_key} <-> {to_key}")
            return True
        except Exception as e:
            logger.error(f"Start chat failed: {str(e)}")
            return False
    
    def end_chat(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
        """End bidirectional chat"""
        try:
            from_key = f"{from_type}:{from_id}"
            to_key = f"{to_type}:{to_id}"
            
            self.active_chats[from_key].discard(to_key)
            self.active_chats[to_key].discard(from_key)
            
            logger.info(f"Chat ended: {from_key} <-> {to_key}")
            return True
        except Exception as e:
            logger.error(f"End chat failed: {str(e)}")
            return False
    
    def is_chatting_with(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str
    ) -> bool:
        """Check if active chat exists"""
        from_key = f"{from_type}:{from_id}"
        to_key = f"{to_type}:{to_id}"
        return to_key in self.active_chats.get(from_key, set())
    
    def get_chat_partners(self, client_type: str, user_id: str) -> List[Tuple[str, str]]:
        """Get all active chat partners for a user"""
        key = f"{client_type}:{user_id}"
        partners = []
        for p in self.active_chats.get(key, set()):
            try:
                p_type, p_id = p.split(":", 1)
                partners.append((p_type, p_id))
            except ValueError:
                continue
        return partners
    
    async def send_message(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        text: str,
        from_name: Optional[str] = None
    ) -> bool:
        """Send direct message between two users"""
        if not self.is_chatting_with(from_type, from_id, to_type, to_id):
            logger.warning(f"No active chat: {from_type}:{from_id} -> {to_type}:{to_id}")
            return False
        
        message = {
            "type": ConnectionPurpose.MESSAGING.value,
            "from_type": from_type,
            "from_id": from_id,
            "from_name": from_name or from_id,
            "text": text,
            "timestamp": datetime.utcnow().isoformat(),
            "message_id": str(uuid.uuid4())
        }
        
        return await self.send_to(message, to_type, to_id, ConnectionPurpose.MESSAGING.value)
    
    # ============================================================
    # NOTIFICATIONS Purpose Methods
    # ============================================================
    
    async def send_notification(
        self,
        to_type: str,
        to_id: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
        urgency: str = "normal"
    ) -> bool:
        """Send notification to a specific user"""
        message = {
            "type": ConnectionPurpose.NOTIFICATIONS.value,
            "title": title,
            "body": body,
            "data": data or {},
            "urgency": urgency,
            "timestamp": datetime.utcnow().isoformat(),
            "notification_id": str(uuid.uuid4())
        }
        
        return await self.send_to(message, to_type, to_id, ConnectionPurpose.NOTIFICATIONS.value)
    
    async def broadcast_notification(
        self,
        to_type: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
        urgency: str = "normal"
    ) -> Dict[str, bool]:
        """Broadcast notification to all users of a type"""
        message = {
            "type": ConnectionPurpose.NOTIFICATIONS.value,
            "title": title,
            "body": body,
            "data": data or {},
            "urgency": urgency,
            "timestamp": datetime.utcnow().isoformat(),
            "notification_id": str(uuid.uuid4())
        }
        
        return await self.broadcast_to_type(message, to_type, ConnectionPurpose.NOTIFICATIONS.value)
    
    # ============================================================
    # Heartbeat & Monitoring
    # ============================================================
    
    async def _start_heartbeat(self, purpose: str, client_type: str, user_id: str) -> None:
        """Start periodic heartbeat to detect dead connections"""
        task_key = f"{purpose}:{client_type}:{user_id}"
        try:
            task = asyncio.create_task(
                self._heartbeat_loop(purpose, client_type, user_id)
            )
            self.heartbeat_tasks[task_key] = task
        except Exception as e:
            logger.error(f"Failed to start heartbeat: {str(e)}")
    
    async def _heartbeat_loop(self, purpose: str, client_type: str, user_id: str) -> None:
        """Periodic check for dead connections"""
        try:
            while True:
                await asyncio.sleep(30)  # 30 second heartbeat interval
                
                conn = self.get_connection(client_type, user_id, purpose)
                if not conn or not conn.is_active:
                    self.disconnect(client_type, user_id, purpose)
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat loop error: {str(e)}")
    
    def get_stats(self) -> dict:
        """Get connection statistics"""
        stats = {
            "timestamp": datetime.utcnow().isoformat(),
            "by_purpose": {},
            "location_subscribers": {},
            "active_chats": len(self.active_chats)
        }
        
        for purpose in self.connections:
            total = sum(
                len(users) for users in self.connections[purpose].values()
            )
            stats["by_purpose"][purpose] = {
                "total": total,
                "by_type": {
                    ct: len(users)
                    for ct, users in self.connections[purpose].items()
                }
            }
        
        stats["location_subscribers"] = {
            rider_id: list(customers)
            for rider_id, customers in self.rider_location_subscribers.items()
        }
        
        return stats
    
    def get_active_users(self, client_type: Optional[str] = None, purpose: Optional[str] = None) -> Dict[str, List[str]]:
        """Get list of active users"""
        result = {}
        
        purposes = [purpose] if purpose else list(self.connections.keys())
        client_types = [client_type] if client_type else list(self.connections.get(purposes[0], {}).keys())
        
        for p in purposes:
            for ct in client_types:
                users = list(self.connections.get(p, {}).get(ct, {}).keys())
                key = f"{p}:{ct}"
                result[key] = users
        
        return result


# Global instance
manager = ProductionConnectionManager()