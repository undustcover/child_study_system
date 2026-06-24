from fastapi import WebSocket


class DeviceConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}

    async def connect(self, device_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[device_id] = websocket

    def disconnect(self, device_id: str) -> None:
        self._connections.pop(device_id, None)

    def is_connected(self, device_id: str) -> bool:
        return device_id in self._connections

    async def send_json(self, device_id: str, payload: dict) -> bool:
        websocket = self._connections.get(device_id)
        if websocket is None:
            return False
        await websocket.send_json(payload)
        return True


device_connection_manager = DeviceConnectionManager()
