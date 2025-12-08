# app/utils/websocket_manager_production.py
"""
Production-grade WebSocket Manager with persistence and offline support
- Messages persist to database
- Offline users receive messages on reconnection
- Active chat state persists
- Notifications queued for offline users
- Location history maintained
"""

import asyncio
import json
import logging
from typing import Dict, Set, Optional, Tuple, List
from fastapi import WebSocket
from collections import defaultdict
from datetime import datetime, timedelta
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
    Enterprise-grade connection manager with database persistence.
    
    This manager:
    1. Stores all messages in database for offline users
    2. Delivers messages on reconnection
    3. Maintains chat session state in database
    4. Queues notifications for offline users
    5. Keeps location history for analytics
    """

    def __init__(self):
        # In-memory active connections
        # Structure: connections[purpose][client_type][user_id] = WSConnection
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

        # Location tracking (in-memory, as it's real-time)
        self.rider_location_subscribers: Dict[str, Set[str]] = defaultdict(set)
        self.customer_tracking_rider: Dict[str, str] = {}

        # Active chats (will also check database)
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
        Accept and register a new WebSocket connection.
        Also delivers any offline messages/notifications.
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

            # ⭐ KEY: Deliver offline messages/notifications on reconnection
            if purpose == ConnectionPurpose.MESSAGING.value:
                await self._deliver_offline_messages(client_type, str(user_id), conn)
            elif purpose == ConnectionPurpose.NOTIFICATIONS.value:
                await self._deliver_offline_notifications(client_type, str(user_id), conn)

            # Start heartbeat
            await self._start_heartbeat(purpose, client_type, str(user_id))

            return True

        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            return False

    async def _deliver_offline_messages(self, client_type: str, user_id: str, conn: WSConnection) -> None:
        """
        Get undelivered messages from database and send to reconnecting user.
        This replicates real apps like Uber, WhatsApp, Facebook Messenger.
        """
        try:
            from applications.user.chat_notification import ChatMessage

            # Get messages where user is recipient and not delivered
            offline_messages = await ChatMessage.filter(
                to_type=client_type,
                to_id=user_id,
                is_delivered=False
            ).order_by("created_at")

            if offline_messages:
                logger.info(f"Found {len(offline_messages)} offline messages for {client_type}:{user_id}")

                # Send all offline messages
                for msg in offline_messages:
                    payload = {
                        "type": ConnectionPurpose.MESSAGING.value,
                        "from_type": msg.from_type,
                        "from_id": msg.from_id,
                        "from_name": msg.from_name,
                        "text": msg.text,
                        "message_id": msg.message_id,
                        "timestamp": msg.created_at.isoformat(),
                        "is_offline_message": True  # Mark as previously offline
                    }

                    success = await conn.send_json(payload)

                    if success:
                        # Mark as delivered
                        msg.is_delivered = True
                        await msg.save()
                        logger.info(f"Delivered offline message {msg.message_id}")

        except Exception as e:
            logger.error(f"Error delivering offline messages: {str(e)}")

    async def _deliver_offline_notifications(self, client_type: str, user_id: str, conn: WSConnection) -> None:
        """
        Get queued notifications and send to reconnecting user.
        """
        try:
            from applications.user.chat_notification import OfflineNotification

            # Get undelivered notifications
            notifications = await OfflineNotification.filter(
                to_type=client_type,
                to_id=user_id,
                is_delivered=False
            ).order_by("created_at")

            if notifications:
                logger.info(f"Found {len(notifications)} offline notifications for {client_type}:{user_id}")

                for notif in notifications:
                    payload = {
                        "type": ConnectionPurpose.NOTIFICATIONS.value,
                        "notification_id": notif.notification_id,
                        "title": notif.title,
                        "body": notif.body,
                        "data": notif.data,
                        "urgency": notif.urgency,
                        "timestamp": notif.created_at.isoformat(),
                        "is_offline_notification": True  # Mark as previously queued
                    }

                    success = await conn.send_json(payload)

                    if success:
                        notif.is_delivered = True
                        notif.delivered_at = datetime.utcnow()
                        await notif.save()
                        logger.info(f"Delivered offline notification {notif.notification_id}")

        except Exception as e:
            logger.error(f"Error delivering offline notifications: {str(e)}")

    async def _start_heartbeat(self, purpose: str, client_type: str, user_id: str) -> None:
        """Periodic heartbeat to detect dead connections"""
        task_key = f"{purpose}:{client_type}:{user_id}"

        async def heartbeat():
            try:
                while True:
                    await asyncio.sleep(60)  # Every 60 seconds
                    conn = self.get_connection(client_type, user_id, purpose)
                    if conn and conn.is_active:
                        try:
                            await conn.send_json({"type": "ping"})
                        except:
                            conn.is_active = False
                            break
                    else:
                        break
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Heartbeat error: {str(e)}")

        task = asyncio.create_task(heartbeat())
        self.heartbeat_tasks[task_key] = task

    def disconnect(self, client_type: str, user_id: str, purpose: Optional[str] = None) -> None:
        """
        Disconnect a user from one or all purposes.
        Does NOT delete chat history (it's in database).
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

                # Cleanup location tracking
                if client_type == ClientType.CUSTOMERS.value and user_id in self.customer_tracking_rider:
                    rider_id = self.customer_tracking_rider.pop(user_id)
                    self.rider_location_subscribers[rider_id].discard(user_id)

                if client_type == ClientType.RIDERS.value:
                    if user_id in self.rider_location_subscribers:
                        del self.rider_location_subscribers[user_id]

                    to_remove = [cid for cid, rid in self.customer_tracking_rider.items() if rid == user_id]
                    for cid in to_remove:
                        self.customer_tracking_rider.pop(cid, None)

                # Cleanup chats (keep session active)
                key = f"{client_type}:{user_id}"
                if key in self.active_chats:
                    for partner_key in list(self.active_chats[key]):
                        if partner_key in self.active_chats:
                            self.active_chats[partner_key].discard(key)

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
        except:
            return None

    async def send_to(
        self,
        message: dict,
        client_type: str,
        user_id: str,
        purpose: str
    ) -> bool:
        """
        Send message to a user.
        If user is offline, store in database for later delivery.
        """
        try:
            user_id = str(user_id)
            conn = self.get_connection(client_type, user_id, purpose)

            if conn and conn.is_active:
                # User is online - send directly
                success = await conn.send_json(message)
                if not success:
                    self.disconnect(client_type, user_id, purpose)
                return success
            else:
                # User is offline - store in database
                if purpose == ConnectionPurpose.MESSAGING.value:
                    await self._store_offline_message(message, client_type, user_id)
                elif purpose == ConnectionPurpose.NOTIFICATIONS.value:
                    await self._store_offline_notification(message, client_type, user_id)

                logger.info(f"User {client_type}:{user_id} offline - queued message")
                return True  # We stored it, so return success

        except Exception as e:
            logger.error(f"Send failed: {str(e)}")
            return False

    async def _store_offline_message(self, message: dict, client_type: str, user_id: str) -> None:
        """Store message in database for offline user"""
        try:
            from applications.user.chat_notification import ChatMessage

            msg = ChatMessage(
                from_type=message.get("from_type"),
                from_id=message.get("from_id"),
                from_name=message.get("from_name"),
                to_type=client_type,
                to_id=user_id,
                text=message.get("text"),
                message_id=message.get("message_id", str(uuid.uuid4())),
                is_delivered=False,
                is_read=False
            )
            await msg.save()
            logger.info(f"Stored offline message: {msg.message_id}")

        except Exception as e:
            logger.error(f"Failed to store offline message: {str(e)}")

    async def _store_offline_notification(self, message: dict, client_type: str, user_id: str) -> None:
        """Store notification in database for offline user"""
        try:
            from applications.user.chat_notification import OfflineNotification

            notif = OfflineNotification(
                to_type=client_type,
                to_id=user_id,
                notification_id=message.get("notification_id", str(uuid.uuid4())),
                title=message.get("title"),
                body=message.get("body"),
                data=message.get("data", {}),
                urgency=message.get("urgency", "normal"),
                is_delivered=False,
                expires_at=datetime.utcnow() + timedelta(days=30)
            )
            await notif.save()
            logger.info(f"Stored offline notification: {notif.notification_id}")

        except Exception as e:
            logger.error(f"Failed to store offline notification: {str(e)}")

    async def broadcast_to_type(
        self,
        message: dict,
        client_type: str,
        purpose: str
    ) -> Dict[str, bool]:
        """Broadcast to all users of a specific client type"""
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
    # LOCATION TRACKING METHODS
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

        # Store location in database
        await self._store_location_history(rider_id, latitude, longitude, additional_data)

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

    async def _store_location_history(self, rider_id: str, latitude: float, longitude: float, data: dict = None) -> None:
        """Store location for analytics and offline retrieval"""
        try:
            from applications.user.chat_notification import LocationHistory

            loc = LocationHistory(
                rider_id=rider_id,
                latitude=latitude,
                longitude=longitude,
                accuracy=data.get("accuracy") if data else None,
                speed=data.get("speed") if data else None,
                heading=data.get("heading") if data else None,
                expires_at=datetime.utcnow() + timedelta(hours=24)
            )
            await loc.save()

        except Exception as e:
            logger.error(f"Failed to store location: {str(e)}")

    def get_location_subscribers(self, rider_id: str) -> Set[str]:
        """Get all customers tracking this rider"""
        return self.rider_location_subscribers.get(str(rider_id), set())

    # ============================================================
    # CHAT SESSION MANAGEMENT
    # ============================================================

    async def start_chat(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
        """
        Start a chat session between two users.
        Creates persistent session in database.
        """
        try:
            from applications.user.chat_notification import ChatSession

            from_key = f"{from_type}:{from_id}"
            to_key = f"{to_type}:{to_id}"

            # In-memory
            self.active_chats[from_key].add(to_key)
            self.active_chats[to_key].add(from_key)

            # Database (for persistence and reconnection detection)
            session, created = await ChatSession.get_or_create(
                user1_type=from_type,
                user1_id=from_id,
                user2_type=to_type,
                user2_id=to_id,
                defaults={
                    "is_active": True,
                    "last_message_at": datetime.utcnow()
                }
            )

            if not created:
                session.is_active = True
                await session.save()

            logger.info(f"Chat session started: {from_key} <-> {to_key}")
            return True

        except Exception as e:
            logger.error(f"Failed to start chat: {str(e)}")
            return False

    async def end_chat(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
        """End a chat session"""
        try:
            from applications.user.chat_notification import ChatSession

            from_key = f"{from_type}:{from_id}"
            to_key = f"{to_type}:{to_id}"

            # In-memory cleanup
            if from_key in self.active_chats:
                self.active_chats[from_key].discard(to_key)
            if to_key in self.active_chats:
                self.active_chats[to_key].discard(from_key)

            # Database
            session = await ChatSession.get_or_none(
                user1_type=from_type,
                user1_id=from_id,
                user2_type=to_type,
                user2_id=to_id
            )

            if session:
                session.is_active = False
                session.ended_at = datetime.utcnow()
                await session.save()

            return True

        except Exception as e:
            logger.error(f"Failed to end chat: {str(e)}")
            return False

    async def is_chatting_with(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
        """
        Check if two users have an active chat session.
        Checks both in-memory and database.
        """
        try:
            from applications.user.chat_notification import ChatSession

            from_key = f"{from_type}:{from_id}"
            to_key = f"{to_type}:{to_id}"

            # Check in-memory first (faster)
            if to_key in self.active_chats.get(from_key, set()):
                return True

            # Check database (for reconnection scenarios)
            session = await ChatSession.get_or_none(
                user1_type=from_type,
                user1_id=from_id,
                user2_type=to_type,
                user2_id=to_id,
                is_active=True
            )

            if session:
                # Restore to in-memory cache
                self.active_chats[from_key].add(to_key)
                self.active_chats[to_key].add(from_key)
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking chat status: {str(e)}")
            return False

    async def send_message(
        self,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
        text: str,
        from_name: str = None
    ) -> bool:
        """
        Send a message and store in database for persistence.
        Works whether recipient is online or offline.
        """
        try:
            message_id = str(uuid.uuid4())

            # Store in database immediately
            await self._store_offline_message(
                {
                    "from_type": from_type,
                    "from_id": from_id,
                    "from_name": from_name,
                    "text": text,
                    "message_id": message_id
                },
                to_type,
                to_id
            )

            # Send if online
            message = {
                "type": ConnectionPurpose.MESSAGING.value,
                "from_type": from_type,
                "from_id": from_id,
                "from_name": from_name,
                "text": text,
                "message_id": message_id,
                "timestamp": datetime.utcnow().isoformat()
            }

            await self.send_to(message, to_type, to_id, ConnectionPurpose.MESSAGING.value)
            return True

        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            return False

    async def send_notification(
        self,
        to_type: str,
        to_id: str,
        title: str,
        body: str,
        data: dict = None,
        urgency: str = "normal"
    ) -> bool:
        """Send notification to user (offline or online)"""
        try:
            notification_id = str(uuid.uuid4())

            message = {
                "type": ConnectionPurpose.NOTIFICATIONS.value,
                "notification_id": notification_id,
                "title": title,
                "body": body,
                "data": data or {},
                "urgency": urgency,
                "timestamp": datetime.utcnow().isoformat()
            }

            return await self.send_to(message, to_type, to_id, ConnectionPurpose.NOTIFICATIONS.value)

        except Exception as e:
            logger.error(f"Failed to send notification: {str(e)}")
            return False

    def get_active_users(self, client_type: str = None, purpose: str = None) -> Dict:
        """Get statistics about active connections"""
        result = {}

        if purpose:
            purposes = [purpose]
        else:
            purposes = [cp.value for cp in ConnectionPurpose]

        for p in purposes:
            if client_type:
                users = self.connections.get(p, {}).get(client_type, {})
                result[f"{p}:{client_type}"] = list(users.keys())
            else:
                for ct in [ClientType.RIDERS.value, ClientType.CUSTOMERS.value, ClientType.VENDORS.value, ClientType.ADMINS.value]:
                    users = self.connections.get(p, {}).get(ct, {})
                    result[f"{p}:{ct}"] = list(users.keys())

        return result

    def get_chat_partners(self, client_type: str, user_id: str) -> List[Tuple[str, str]]:
        """Get all active chat partners for a user"""
        key = f"{client_type}:{user_id}"
        partners = self.active_chats.get(key, set())

        result = []
        for p in partners:
            try:
                p_type, p_id = p.split(":", 1)
                result.append((p_type, p_id))
            except:
                pass

        return result

    def get_stats(self) -> dict:
        """Get connection statistics"""
        stats = {
            "total_active_connections": 0,
            "by_purpose": {},
            "by_client_type": {},
            "active_chats": len(self.active_chats),
            "heartbeat_tasks": len(self.heartbeat_tasks)
        }

        for purpose in [cp.value for cp in ConnectionPurpose]:
            purpose_count = 0
            for client_type in [ClientType.RIDERS.value, ClientType.CUSTOMERS.value, ClientType.VENDORS.value, ClientType.ADMINS.value]:
                count = len(self.connections.get(purpose, {}).get(client_type, {}))
                purpose_count += count

                key = f"{client_type}"
                if key not in stats["by_client_type"]:
                    stats["by_client_type"][key] = 0
                stats["by_client_type"][key] += count

            stats["by_purpose"][purpose] = purpose_count
            stats["total_active_connections"] += purpose_count

        return stats


# Global instance
manager = ProductionConnectionManager()






# # app/utils/websocket_manager_v2.py
# """
# Production-grade WebSocket Manager
# 3 Purposes: LOCATION_SEND, MESSAGING, NOTIFICATIONS
# 4 Client Types: VENDORS, CUSTOMERS, RIDERS, ADMINS (optional)
# """

# import asyncio
# import json
# import logging
# from typing import Dict, Set, Optional, Tuple, List
# from fastapi import WebSocket
# from collections import defaultdict
# from datetime import datetime
# from enum import Enum
# import uuid

# logger = logging.getLogger(__name__)


# class ConnectionPurpose(str, Enum):
#     """Message purposes - prevents cross-contamination"""
#     LOCATION_SEND = "location_send"
#     MESSAGING = "messaging"
#     NOTIFICATIONS = "notifications"


# class ClientType(str, Enum):
#     """Valid client types"""
#     VENDORS = "vendors"
#     CUSTOMERS = "customers"
#     RIDERS = "riders"
#     ADMINS = "admins"


# class WSConnection:
#     """Represents a single WebSocket connection with metadata"""
    
#     def __init__(self, websocket: WebSocket, client_type: str, user_id: str, purpose: str):
#         self.websocket = websocket
#         self.client_type = client_type
#         self.user_id = user_id
#         self.purpose = purpose
#         self.connected_at = datetime.utcnow()
#         self.last_message_at = datetime.utcnow()
#         self.message_count = 0
#         self.is_active = True
#         self.connection_id = str(uuid.uuid4())
    
#     async def send_json(self, data: dict) -> bool:
#         """Send JSON data through WebSocket"""
#         try:
#             await self.websocket.send_json(data)
#             self.last_message_at = datetime.utcnow()
#             self.message_count += 1
#             return True
#         except Exception as e:
#             logger.error(f"Failed to send JSON: {str(e)}")
#             self.is_active = False
#             return False
    
#     def to_dict(self) -> dict:
#         """Serialize connection metadata"""
#         return {
#             "connection_id": self.connection_id,
#             "client_type": self.client_type,
#             "user_id": self.user_id,
#             "purpose": self.purpose,
#             "connected_at": self.connected_at.isoformat(),
#             "last_message_at": self.last_message_at.isoformat(),
#             "message_count": self.message_count
#         }


# class ProductionConnectionManager:
#     """
#     Enterprise-grade connection manager for multi-user, multi-purpose WebSocket connections
    
#     Structure:
#     connections[purpose][client_type][user_id] = WSConnection
    
#     Examples:
#     - Location tracking: connections[LOCATION_SEND][RIDERS][123]
#     - Messaging: connections[MESSAGING][CUSTOMERS][456]
#     - Notifications: connections[NOTIFICATIONS][VENDORS][789]
#     """
    
#     def __init__(self):
#         # Main connection store: purpose -> client_type -> user_id -> WSConnection
#         self.connections: Dict[str, Dict[str, Dict[str, WSConnection]]] = {
#             ConnectionPurpose.LOCATION_SEND.value: {
#                 ClientType.RIDERS.value: {},
#                 ClientType.CUSTOMERS.value: {},
#                 ClientType.VENDORS.value: {},
#                 ClientType.ADMINS.value: {}
#             },
#             ConnectionPurpose.MESSAGING.value: {
#                 ClientType.RIDERS.value: {},
#                 ClientType.CUSTOMERS.value: {},
#                 ClientType.VENDORS.value: {},
#                 ClientType.ADMINS.value: {}
#             },
#             ConnectionPurpose.NOTIFICATIONS.value: {
#                 ClientType.RIDERS.value: {},
#                 ClientType.CUSTOMERS.value: {},
#                 ClientType.VENDORS.value: {},
#                 ClientType.ADMINS.value: {}
#             }
#         }
        
#         # Location tracking: rider_id -> set(customer_ids watching)
#         self.rider_location_subscribers: Dict[str, Set[str]] = defaultdict(set)
#         self.customer_tracking_rider: Dict[str, str] = {}  # customer_id -> rider_id
        
#         # Active chats: "type:id" -> set("type:id") (bidirectional)
#         self.active_chats: Dict[str, Set[str]] = defaultdict(set)
        
#         # Heartbeat tasks
#         self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
    
#     async def connect(
#         self,
#         websocket: WebSocket,
#         client_type: str,
#         user_id: str,
#         purpose: str,
#         username: Optional[str] = None
#     ) -> bool:
#         """
#         Accept and register a new WebSocket connection
        
#         Args:
#             websocket: FastAPI WebSocket
#             client_type: "riders", "customers", "vendors", "admins"
#             user_id: User identifier
#             purpose: "location_send", "messaging", "notifications"
#             username: Optional display name
        
#         Returns:
#             True if successful, False otherwise
#         """
#         try:
#             # Validate inputs
#             if client_type not in [ct.value for ct in ClientType]:
#                 logger.error(f"Invalid client_type: {client_type}")
#                 await websocket.close(code=4000, reason="Invalid client type")
#                 return False
            
#             if purpose not in [cp.value for cp in ConnectionPurpose]:
#                 logger.error(f"Invalid purpose: {purpose}")
#                 await websocket.close(code=4001, reason="Invalid purpose")
#                 return False
            
#             # Accept connection
#             await websocket.accept()
            
#             # Create connection object
#             conn = WSConnection(websocket, client_type, str(user_id), purpose)
            
#             # Store connection
#             self.connections[purpose][client_type][str(user_id)] = conn
            
#             logger.info(
#                 f"✓ Connected: {client_type}:{user_id} (Purpose: {purpose}) "
#                 f"[ID: {conn.connection_id}]"
#             )
            
#             # Start heartbeat for long-lived connections
#             await self._start_heartbeat(purpose, client_type, str(user_id))
            
#             return True
            
#         except Exception as e:
#             logger.error(f"Connection failed: {str(e)}")
#             return False
    
#     def disconnect(self, client_type: str, user_id: str, purpose: Optional[str] = None) -> None:
#         """
#         Disconnect a user from one or all purposes
        
#         Args:
#             client_type: Client type
#             user_id: User ID
#             purpose: Specific purpose to disconnect, or None for all
#         """
#         try:
#             user_id = str(user_id)
            
#             if purpose:
#                 # Disconnect from specific purpose
#                 if (purpose in self.connections and 
#                     client_type in self.connections[purpose] and
#                     user_id in self.connections[purpose][client_type]):
                    
#                     del self.connections[purpose][client_type][user_id]
                    
#                     # Cancel heartbeat
#                     task_key = f"{purpose}:{client_type}:{user_id}"
#                     if task_key in self.heartbeat_tasks:
#                         self.heartbeat_tasks[task_key].cancel()
#                         del self.heartbeat_tasks[task_key]
                    
#                     logger.info(f"✗ Disconnected: {client_type}:{user_id} (Purpose: {purpose})")
#             else:
#                 # Disconnect from ALL purposes
#                 for p in [ConnectionPurpose.LOCATION_SEND.value,
#                          ConnectionPurpose.MESSAGING.value,
#                          ConnectionPurpose.NOTIFICATIONS.value]:
#                     if p in self.connections and client_type in self.connections[p]:
#                         if user_id in self.connections[p][client_type]:
#                             del self.connections[p][client_type][user_id]
                            
#                             task_key = f"{p}:{client_type}:{user_id}"
#                             if task_key in self.heartbeat_tasks:
#                                 self.heartbeat_tasks[task_key].cancel()
#                                 del self.heartbeat_tasks[task_key]
            
#             # Cleanup location tracking if customer disconnects
#             if client_type == ClientType.CUSTOMERS.value and user_id in self.customer_tracking_rider:
#                 rider_id = self.customer_tracking_rider.pop(user_id)
#                 self.rider_location_subscribers[rider_id].discard(user_id)
            
#             # Cleanup location tracking if rider disconnects
#             if client_type == ClientType.RIDERS.value:
#                 if user_id in self.rider_location_subscribers:
#                     del self.rider_location_subscribers[user_id]
                
#                 # Remove reverse mappings
#                 to_remove = [cid for cid, rid in self.customer_tracking_rider.items() if rid == user_id]
#                 for cid in to_remove:
#                     self.customer_tracking_rider.pop(cid, None)
            
#             # Cleanup chats
#             key = f"{client_type}:{user_id}"
#             if key in self.active_chats:
#                 for partner_key in self.active_chats[key]:
#                     if partner_key in self.active_chats:
#                         self.active_chats[partner_key].discard(key)
#                 del self.active_chats[key]
                
#         except Exception as e:
#             logger.error(f"Disconnect error: {str(e)}")
    
#     def get_connection(
#         self,
#         client_type: str,
#         user_id: str,
#         purpose: str
#     ) -> Optional[WSConnection]:
#         """Get a specific connection"""
#         try:
#             return self.connections.get(purpose, {}).get(client_type, {}).get(str(user_id))
#         except Exception as e:
#             logger.error(f"Error getting connection: {str(e)}")
#             return None
    
#     async def send_to(
#         self,
#         message: dict,
#         client_type: str,
#         user_id: str,
#         purpose: str
#     ) -> bool:
#         """Send message to a specific user for a specific purpose"""
#         try:
#             conn = self.get_connection(client_type, user_id, purpose)
#             if conn and conn.is_active:
#                 success = await conn.send_json(message)
#                 if not success:
#                     self.disconnect(client_type, user_id, purpose)
#                 return success
#             return False
#         except Exception as e:
#             logger.error(f"Send failed: {str(e)}")
#             return False
    
#     async def broadcast_to_type(
#         self,
#         message: dict,
#         client_type: str,
#         purpose: str
#     ) -> Dict[str, bool]:
#         """Broadcast to all users of a specific client type for a purpose"""
#         results = {}
#         try:
#             users = self.connections.get(purpose, {}).get(client_type, {})
#             for user_id, conn in list(users.items()):
#                 if conn.is_active:
#                     results[user_id] = await conn.send_json(message)
#                     if not results[user_id]:
#                         self.disconnect(client_type, user_id, purpose)
#         except Exception as e:
#             logger.error(f"Broadcast failed: {str(e)}")
#         return results
    
#     # ============================================================
#     # LOCATION_SEND Purpose Methods
#     # ============================================================
    
#     def add_location_subscriber(self, rider_id: str, customer_id: str) -> None:
#         """Customer starts tracking rider's location"""
#         rider_id = str(rider_id)
#         customer_id = str(customer_id)
#         self.rider_location_subscribers[rider_id].add(customer_id)
#         self.customer_tracking_rider[customer_id] = rider_id
#         logger.info(f"Location tracking: Customer {customer_id} -> Rider {rider_id}")
    
#     def remove_location_subscriber(self, rider_id: str, customer_id: str) -> None:
#         """Customer stops tracking rider's location"""
#         rider_id = str(rider_id)
#         customer_id = str(customer_id)
#         self.rider_location_subscribers[rider_id].discard(customer_id)
#         self.customer_tracking_rider.pop(customer_id, None)
    
#     async def send_location_update(
#         self,
#         rider_id: str,
#         latitude: float,
#         longitude: float,
#         additional_data: Optional[dict] = None
#     ) -> Dict[str, bool]:
#         """Send location to all customers tracking this rider"""
#         rider_id = str(rider_id)
#         customers = self.rider_location_subscribers.get(rider_id, set())
        
#         message = {
#             "type": ConnectionPurpose.LOCATION_SEND.value,
#             "rider_id": rider_id,
#             "latitude": latitude,
#             "longitude": longitude,
#             "timestamp": datetime.utcnow().isoformat(),
#             **(additional_data or {})
#         }
        
#         results = {}
#         for customer_id in customers:
#             results[customer_id] = await self.send_to(
#                 message,
#                 ClientType.CUSTOMERS.value,
#                 customer_id,
#                 ConnectionPurpose.LOCATION_SEND.value
#             )
        
#         return results
    
#     def get_location_subscribers(self, rider_id: str) -> Set[str]:
#         """Get all customers tracking this rider"""
#         return self.rider_location_subscribers.get(str(rider_id), set())
    
#     # ============================================================
#     # MESSAGING Purpose Methods
#     # ============================================================
    
#     def start_chat(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
#         """Start bidirectional chat between two users"""
#         try:
#             from_key = f"{from_type}:{from_id}"
#             to_key = f"{to_type}:{to_id}"
            
#             self.active_chats[from_key].add(to_key)
#             self.active_chats[to_key].add(from_key)
            
#             logger.info(f"Chat started: {from_key} <-> {to_key}")
#             return True
#         except Exception as e:
#             logger.error(f"Start chat failed: {str(e)}")
#             return False
    
#     def end_chat(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
#         """End bidirectional chat"""
#         try:
#             from_key = f"{from_type}:{from_id}"
#             to_key = f"{to_type}:{to_id}"
            
#             self.active_chats[from_key].discard(to_key)
#             self.active_chats[to_key].discard(from_key)
            
#             logger.info(f"Chat ended: {from_key} <-> {to_key}")
#             return True
#         except Exception as e:
#             logger.error(f"End chat failed: {str(e)}")
#             return False
    
#     def is_chatting_with(
#         self,
#         from_type: str,
#         from_id: str,
#         to_type: str,
#         to_id: str
#     ) -> bool:
#         """Check if active chat exists"""
#         from_key = f"{from_type}:{from_id}"
#         to_key = f"{to_type}:{to_id}"
#         return to_key in self.active_chats.get(from_key, set())
    
#     def get_chat_partners(self, client_type: str, user_id: str) -> List[Tuple[str, str]]:
#         """Get all active chat partners for a user"""
#         key = f"{client_type}:{user_id}"
#         partners = []
#         for p in self.active_chats.get(key, set()):
#             try:
#                 p_type, p_id = p.split(":", 1)
#                 partners.append((p_type, p_id))
#             except ValueError:
#                 continue
#         return partners
    
#     async def send_message(
#         self,
#         from_type: str,
#         from_id: str,
#         to_type: str,
#         to_id: str,
#         text: str,
#         from_name: Optional[str] = None
#     ) -> bool:
#         """Send direct message between two users"""
#         if not self.is_chatting_with(from_type, from_id, to_type, to_id):
#             logger.warning(f"No active chat: {from_type}:{from_id} -> {to_type}:{to_id}")
#             return False
        
#         message = {
#             "type": ConnectionPurpose.MESSAGING.value,
#             "from_type": from_type,
#             "from_id": from_id,
#             "from_name": from_name or from_id,
#             "text": text,
#             "timestamp": datetime.utcnow().isoformat(),
#             "message_id": str(uuid.uuid4())
#         }
        
#         return await self.send_to(message, to_type, to_id, ConnectionPurpose.MESSAGING.value)
    
#     # ============================================================
#     # NOTIFICATIONS Purpose Methods
#     # ============================================================
    
#     async def send_notification(
#         self,
#         to_type: str,
#         to_id: str,
#         title: str,
#         body: str,
#         data: Optional[dict] = None,
#         urgency: str = "normal"
#     ) -> bool:
#         """Send notification to a specific user"""
#         message = {
#             "type": ConnectionPurpose.NOTIFICATIONS.value,
#             "title": title,
#             "body": body,
#             "data": data or {},
#             "urgency": urgency,
#             "timestamp": datetime.utcnow().isoformat(),
#             "notification_id": str(uuid.uuid4())
#         }
        
#         return await self.send_to(message, to_type, to_id, ConnectionPurpose.NOTIFICATIONS.value)
    
#     async def broadcast_notification(
#         self,
#         to_type: str,
#         title: str,
#         body: str,
#         data: Optional[dict] = None,
#         urgency: str = "normal"
#     ) -> Dict[str, bool]:
#         """Broadcast notification to all users of a type"""
#         message = {
#             "type": ConnectionPurpose.NOTIFICATIONS.value,
#             "title": title,
#             "body": body,
#             "data": data or {},
#             "urgency": urgency,
#             "timestamp": datetime.utcnow().isoformat(),
#             "notification_id": str(uuid.uuid4())
#         }
        
#         return await self.broadcast_to_type(message, to_type, ConnectionPurpose.NOTIFICATIONS.value)
    
#     # ============================================================
#     # Heartbeat & Monitoring
#     # ============================================================
    
#     async def _start_heartbeat(self, purpose: str, client_type: str, user_id: str) -> None:
#         """Start periodic heartbeat to detect dead connections"""
#         task_key = f"{purpose}:{client_type}:{user_id}"
#         try:
#             task = asyncio.create_task(
#                 self._heartbeat_loop(purpose, client_type, user_id)
#             )
#             self.heartbeat_tasks[task_key] = task
#         except Exception as e:
#             logger.error(f"Failed to start heartbeat: {str(e)}")
    
#     async def _heartbeat_loop(self, purpose: str, client_type: str, user_id: str) -> None:
#         """Periodic check for dead connections"""
#         try:
#             while True:
#                 await asyncio.sleep(30)  # 30 second heartbeat interval
                
#                 conn = self.get_connection(client_type, user_id, purpose)
#                 if not conn or not conn.is_active:
#                     self.disconnect(client_type, user_id, purpose)
#                     break
#         except asyncio.CancelledError:
#             pass
#         except Exception as e:
#             logger.error(f"Heartbeat loop error: {str(e)}")
    
#     def get_stats(self) -> dict:
#         """Get connection statistics"""
#         stats = {
#             "timestamp": datetime.utcnow().isoformat(),
#             "by_purpose": {},
#             "location_subscribers": {},
#             "active_chats": len(self.active_chats)
#         }
        
#         for purpose in self.connections:
#             total = sum(
#                 len(users) for users in self.connections[purpose].values()
#             )
#             stats["by_purpose"][purpose] = {
#                 "total": total,
#                 "by_type": {
#                     ct: len(users)
#                     for ct, users in self.connections[purpose].items()
#                 }
#             }
        
#         stats["location_subscribers"] = {
#             rider_id: list(customers)
#             for rider_id, customers in self.rider_location_subscribers.items()
#         }
        
#         return stats
    
#     def get_active_users(self, client_type: Optional[str] = None, purpose: Optional[str] = None) -> Dict[str, List[str]]:
#         """Get list of active users"""
#         result = {}
        
#         purposes = [purpose] if purpose else list(self.connections.keys())
#         client_types = [client_type] if client_type else list(self.connections.get(purposes[0], {}).keys())
        
#         for p in purposes:
#             for ct in client_types:
#                 users = list(self.connections.get(p, {}).get(ct, {}).keys())
#                 key = f"{p}:{ct}"
#                 result[key] = users
        
#         return result


# # Global instance
# manager = ProductionConnectionManager()