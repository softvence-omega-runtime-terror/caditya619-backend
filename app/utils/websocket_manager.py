from typing import Dict, Set, Optional
from fastapi import WebSocket
from collections import defaultdict


# app/utils/websocket_manager.py


class ConnectionManager:
    def __init__(self):
        self.connections: Dict[str, Dict[str, WebSocket]] = {
            "riders": {}, "customers": {}, "vendors": {}
        }

        # NEW: Which customers are tracking which rider
        # Format: rider_id -> set(customer_id)
        self.rider_to_customers: Dict[str, Set[str]] = defaultdict(set)
        
        # Reverse: customer_id -> rider_id (for cleanup)
        self.customer_to_rider: Dict[str, str] = {}
        self.active_chats: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, client_type: str, user_id: str):
        await websocket.accept()
        if client_type not in self.connections:
            raise ValueError("Invalid client_type")
        self.connections[client_type][user_id] = websocket
        print(f"Connected {client_type} {user_id}")
        print(f"Current connections: {self.connections}")

    def disconnect(self, client_type: str, user_id: str):
        if client_type in self.connections and user_id in self.connections[client_type]:
            del self.connections[client_type][user_id]

        # If customer disconnects → remove from tracking
        if client_type == "customers" and user_id in self.customer_to_rider:
            rider_id = self.customer_to_rider.pop(user_id)
            self.rider_to_customers[rider_id].discard(user_id)

        # If rider disconnects → clear all tracking
        if client_type == "riders":
            if user_id in self.rider_to_customers:
                del self.rider_to_customers[user_id]
            # Remove reverse mappings
            to_remove = [cid for cid, rid in self.customer_to_rider.items() if rid == user_id]
            for cid in to_remove:
                self.customer_to_rider.pop(cid, None)

    def get_socket(self, client_type: str, user_id: str) -> Optional[WebSocket]:
        print(f"Getting socket for {client_type} {user_id}")
        connetions = self.connections.get(client_type, {}).get(user_id)
        print(f"Connections found: {connetions}")
        return connetions                  #self.connections.get(client_type, {}).get(user_id)

    async def send_to(self, message: dict, client_type: str, user_id: str):
        print(f"Attempting to send to {client_type} {user_id}")
        ws = self.get_socket(client_type, user_id)
        if ws:
            print(f"Found websocket for {client_type} {user_id}, sending message.")
            try:
                print(f"Sending message to {client_type} {user_id}: {message}")
                await ws.send_json(message)
            except:
                self.disconnect(client_type, user_id)

    async def broadcast_to_type(self, message: dict, client_type: str):
        for user_id, ws in self.connections.get(client_type, {}).items():
            try:
                await ws.send_json(message)
            except:
                self.disconnect(client_type, user_id)

    # NEW: Add customer to rider's tracking list
    def add_tracking(self, rider_id: str, customer_id: str):
        print(f"Customer {customer_id} is now tracking Rider {rider_id}")
        self.rider_to_customers[rider_id].add(customer_id)
        self.customer_to_rider[customer_id] = rider_id

    # NEW: Send location only to customers tracking this rider
    async def send_location_to_tracking_customers(self, rider_id: str, location_data: dict):
        customer_ids = self.rider_to_customers.get(rider_id, set())
        for customer_id in customer_ids:
            await self.send_to(location_data, "customers", customer_id)


    def start_chat(self, from_type: str, from_id: str, to_type: str, to_id: str):
        from_key = f"{from_type}:{from_id}"
        to_key = f"{to_type}:{to_id}"

        # Initialize sets
        self.active_chats.setdefault(from_key, set())
        self.active_chats.setdefault(to_key, set())

        # Add bidirectional link
        self.active_chats[from_key].add(to_key)
        self.active_chats[to_key].add(from_key)

    def get_partners(self, from_type: str, from_id: str) -> Set[tuple[str, str]]:
        key = f"{from_type}:{from_id}"
        partners = self.active_chats.get(key, set())
        result = set()
        for p in partners:
            p_type, p_id = p.split(":", 1)
            result.add((p_type, p_id))
        return result

    def end_chat(self, from_type: str, from_id: str, to_type: str, to_id: str):
        from_key = f"{from_type}:{from_id}"
        to_key = f"{to_type}:{to_id}"
        if from_key in self.active_chats:
            self.active_chats[from_key].discard(to_key)
        if to_key in self.active_chats:
            self.active_chats[to_key].discard(from_key)

    def is_chatting_with(self, from_type: str, from_id: str, to_type: str, to_id: str) -> bool:
        key = f"{from_type}:{from_id}"
        partner_key = f"{to_type}:{to_id}"
        return partner_key in self.active_chats.get(key, set())



manager = ConnectionManager()