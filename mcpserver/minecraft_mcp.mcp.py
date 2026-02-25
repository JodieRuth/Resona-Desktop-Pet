import json
import threading
import time
import asyncio
import uuid
from pathlib import Path
import configparser
import websockets

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MinecraftMCP")

class ExternalWsMcpClient:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="ExternalWsMcpClient", daemon=True)
        self._stop_event = threading.Event()
        self._connected = threading.Event()
        self._lock = threading.Lock()
        self._pending = {}
        self._ws = None
        self._thread.start()

    def _run(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect_loop())

    async def _connect_loop(self):
        while not self._stop_event.is_set():
            try:
                uri = f"ws://{self._host}:{self._port}"
                async with websockets.connect(uri) as ws:
                    self._ws = ws
                    self._connected.set()
                    print(f"[MinecraftMCP] ExternalWS connected: {uri}")
                    await ws.send(json.dumps({"type": "mcp_register", "role": "mcp_client"}))
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except Exception:
                            continue
                        if not isinstance(data, dict):
                            continue
                        if data.get("type") != "mcp_response":
                            if data.get("status") or data.get("message"):
                                print(f"[MinecraftMCP] ExternalWS status: {data}")
                            continue
                        req_id = data.get("id")
                        if not req_id:
                            continue
                        with self._lock:
                            entry = self._pending.get(req_id)
                        if entry:
                            entry["data"] = data
                            entry["event"].set()
            except Exception:
                self._connected.clear()
                self._ws = None
                print(f"[MinecraftMCP] ExternalWS disconnected, retrying...")
                await asyncio.sleep(1.0)

    def request(self, action: str, payload: dict, timeout: float = 2.5):
        if not self._connected.wait(timeout=1.0):
            return {
                "type": "mcp_response",
                "status": "no_connection",
                "message": "external ws not connected",
                "mc_version": "unknown",
                "window_title": ""
            }
        req_id = f"mcp-{uuid.uuid4().hex}"
        entry = {"event": threading.Event(), "data": None}
        with self._lock:
            self._pending[req_id] = entry
        message = {"type": "mcp_request", "id": req_id, "action": action}
        if payload:
            message.update(payload)
        try:
            future = asyncio.run_coroutine_threadsafe(self._send(message), self._loop)
            future.result(timeout=1.0)
        except Exception:
            with self._lock:
                self._pending.pop(req_id, None)
            return {
                "type": "mcp_response",
                "status": "error",
                "message": "external ws send failed",
                "mc_version": "unknown",
                "window_title": ""
            }
        if not entry["event"].wait(timeout):
            with self._lock:
                self._pending.pop(req_id, None)
            return {
                "type": "mcp_response",
                "status": "error",
                "message": "external ws timeout",
                "mc_version": "unknown",
                "window_title": ""
            }
        with self._lock:
            self._pending.pop(req_id, None)
        return entry["data"]

    async def _send(self, message: dict):
        if self._ws:
            await self._ws.send(json.dumps(message))


class MinecraftMcpConnector:
    def __init__(self):
        self._lock = threading.Lock()
        self._last_no_instance_log = 0.0
        self._external_ws_host = "127.0.0.1"
        self._external_ws_port = 12345
        self._ws_client = None
        self._load_config()
        print(f"[MinecraftMCP] ExternalWS host={self._external_ws_host} port={self._external_ws_port}")

    def _load_config(self):
        root = Path(__file__).resolve().parents[1]
        cfg_path = root / "config.cfg"
        cfg = configparser.ConfigParser(interpolation=None)
        if cfg_path.exists():
            cfg.read(cfg_path, encoding="utf-8")
        self._external_ws_host = cfg.get("ExternalAPI", "host", fallback="127.0.0.1")
        self._external_ws_port = cfg.getint("ExternalAPI", "port", fallback=12345)
        self._ws_client = ExternalWsMcpClient(self._external_ws_host, self._external_ws_port)


    def call(self, action: str, payload: dict) -> dict:
        if self._ws_client:
            response = self._ws_client.request(action, payload)
            if isinstance(response, dict):
                return response
        now = time.time()
        if now - self._last_no_instance_log > 3.0:
            self._last_no_instance_log = now
            print(f"[MinecraftMCP] No websocket response from {self._external_ws_host}:{self._external_ws_port}")
        return {
            "status": "no_connection",
            "message": "no websocket response",
            "mc_version": "unknown",
            "window_title": ""
        }


connector = MinecraftMcpConnector()


@mcp.tool()
def mc_list_players() -> dict:
    """Lists all online players in the current Minecraft server.
    Returns a list containing player UUIDs, names, coordinates (x, y, z), and dimensions.
    Use this when you need to know who is nearby or find a player's exact location."""
    return connector.call("list_players", {})


@mcp.tool()
def mc_nearby_tile_entities(player: str = "", x: int = 0, y: int = 0, z: int = 0, dimension: int = 0, radius: int = 10) -> dict:
    """Gets information about Tile Entities (blocks with data like chests, machines, furnaces) near a coordinate or player.
    Args:
        player: Optional, centers the probe on this player.
        radius: Detection radius, max 15.
    Returns coordinates, names, and NBT data of the tile entities."""
    payload = {"player": player, "x": x, "y": y, "z": z, "dimension": dimension, "radius": radius}
    return connector.call("nearby_tile_entities", payload)


@mcp.tool()
def mc_ray_trace(player: str, distance: float = 50.0) -> dict:
    """Performs a ray trace from the specified player's perspective.
    Used to get the block or entity the player is currently looking at.
    Args:
        player: The player's name.
        distance: Maximum detection distance, up to 50.
    Returns details of the block or entity under the crosshair."""
    payload = {"player": player, "distance": distance}
    return connector.call("ray_trace", payload)


@mcp.tool()
def mc_player_inventory(player: str) -> dict:
    """Retrieves the full inventory of a specified player.
    Returns all ItemStacks in the inventory (36 slots) and armor slots (4 slots), including names, counts, and NBT data."""
    payload = {"player": player}
    return connector.call("player_inventory", payload)


@mcp.tool()
def mc_block_info(x: int, y: int, z: int, dimension: int = 0) -> dict:
    """Queries detailed information about a block at specific world coordinates.
    Returns the registration name (key), localized name, parent Mod, and NBT data (if applicable)."""
    payload = {"x": x, "y": y, "z": z, "dimension": dimension}
    return connector.call("block_info", payload)


@mcp.tool()
def mc_search_items(query: str) -> dict:
    """Searches for items in the Minecraft item registry.
    Supports fuzzy matching by name, registration key, or unlocalized name.
    Args:
        query: Search keyword (e.g., "iron", "chest").
    Returns a list of matching items with their names and registry keys."""
    payload = {"query": query}
    return connector.call("search_items", payload)


@mcp.tool()
def mc_search_containers_with_item(player: str, query: str, radius: int = 15) -> dict:
    """Searches for specific items inside containers (chests, machines, etc.) around a player.
    Args:
        player: Centers the search on this player.
        query: Item name keyword.
        radius: Search radius, max 15.
    Returns a list of containers containing the item and their coordinates."""
    payload = {"player": player, "query": query, "radius": radius}
    return connector.call("search_containers_with_item", payload)


@mcp.tool()
def mc_explode(x: int, y: int, z: int, strength: float = 2.0, dimension: int = 0) -> dict:
    """Creates an explosion at the specified coordinates.
    Args:
        strength: Explosion strength (default 2.0, TNT is approx 4.0)."""
    payload = {"x": x, "y": y, "z": z, "dimension": dimension, "strength": strength}
    return connector.call("explode", payload)


@mcp.tool()
def mc_run_command(command: str) -> dict:
    """Executes a console command on the Minecraft server.
    Args:
        command: The command to run (without leading slash, e.g., "time set day").
    Returns the execution result code (0 for success)."""
    payload = {"command": command}
    return connector.call("run_command", payload)


@mcp.tool()
def mc_lookup_items(items: list[dict], mc_version: str = "1.7.10") -> dict:
    """Queries localized information for multiple items at once.
    Args:
        items: A list of dicts, each containing:
               - "identifier": Item ID (e.g. "264") or registration key (e.g. "minecraft:diamond").
               - "damage": Optional damage value (default 0).
        mc_version: Minecraft version ("1.7.10", "1.12.2", or "1.20.1").
    Examples:
        - Single item: mc_lookup_items([{"identifier": "264"}])
        - Multiple items: mc_lookup_items([{"identifier": "1", "damage": 1}, {"identifier": "minecraft:iron_ingot"}])
    Returns a list of item metadata."""
    payload = {"items": items, "mc_version": mc_version}
    return connector.call("lookup_item", payload)


@mcp.tool()
def mc_exit_game() -> dict:
    """Safely shuts down the Minecraft client. 
    This will save the world and close the game properly."""
    return connector.call("exit_game", {})


if __name__ == "__main__":
    mcp.run()
