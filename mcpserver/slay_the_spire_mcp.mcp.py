import json
import socket
import threading
import time
import configparser
import sys
import re
import asyncio
import uuid
import websockets
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("SlayTheSpireMCP")

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
                    log_error(f"ExternalWS connected: {uri}")
                    await ws.send(json.dumps({"type": "mcp_register", "role": "mcp_client"}))
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except Exception:
                            continue
                        if not isinstance(data, dict):
                            continue
                        if data.get("type") != "mcp_response":
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
                await asyncio.sleep(1.0)

    def call(self, method: str, params: dict, timeout: float = 2.5):
        if not self._connected.wait(timeout=1.0):
            return {"status": "error", "message": "external ws not connected"}
        req_id = f"mcp-{uuid.uuid4().hex}"
        entry = {"event": threading.Event(), "data": None}
        with self._lock:
            self._pending[req_id] = entry
        
        message = {
            "type": "mcp_request", 
            "id": req_id, 
            "method": method, 
            "params": params,
            "target": "sts_mod"
        }
        
        try:
            future = asyncio.run_coroutine_threadsafe(self._send(message), self._loop)
            future.result(timeout=1.0)
        except Exception as e:
            with self._lock:
                self._pending.pop(req_id, None)
            return {"status": "error", "message": f"external ws send failed: {e}"}
            
        if not entry["event"].wait(timeout):
            with self._lock:
                self._pending.pop(req_id, None)
            return {"status": "error", "message": "external ws timeout"}
            
        with self._lock:
            self._pending.pop(req_id, None)
        return entry["data"]

    async def _send(self, message: dict):
        if self._ws:
            await self._ws.send(json.dumps(message))

class SlayTheSpireMcpConnector:
    def __init__(self):
        self._external_ws_host = "127.0.0.1"
        self._external_ws_port = 12345
        self._ws_client = None
        self._load_config()

    def _load_config(self):
        root = Path(__file__).resolve().parents[1]
        cfg_path = root / "config.cfg"
        cfg = configparser.ConfigParser(interpolation=None)
        if cfg_path.exists():
            cfg.read(cfg_path, encoding="utf-8")
        self._external_ws_host = cfg.get("ExternalAPI", "host", fallback="127.0.0.1")
        self._external_ws_port = cfg.getint("ExternalAPI", "port", fallback=12345)
        self._ws_client = ExternalWsMcpClient(self._external_ws_host, self._external_ws_port)

    def call_mod(self, tool_name: str, arguments: dict) -> dict:
        if self._ws_client:
            params = {"name": tool_name, "arguments": arguments}
            return self._ws_client.call("call_tool", params)
        return {"status": "error", "message": "ws client not initialized"}

_ws_connector = SlayTheSpireMcpConnector()

def log_error(msg: str):
    sys.stderr.write(f"[SlayTheSpireMCP] {msg}\n")
    sys.stderr.flush()

def _load_config() -> tuple[str, int, float]:
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "config.cfg"
    cfg = configparser.ConfigParser(interpolation=None)
    if cfg_path.exists():
        cfg.read(cfg_path, encoding="utf-8")
    host = cfg.get("SlayTheSpire", "host", fallback="127.0.0.1")
    port = cfg.getint("SlayTheSpire", "port", fallback=25433)
    min_delay = cfg.getfloat("SlayTheSpire", "min_response_delay", fallback=0.25)
    return host, port, max(min_delay, 0.0)


def _is_empty_orb(orb: dict) -> bool:
    if not isinstance(orb, dict):
        return False
    orb_id = orb.get("id")
    if orb_id in ("Empty", "OrbSlot", "EmptyOrb"):
        return True
    name = orb.get("name") or ""
    compact = "".join(str(name).split())
    if "充能球栏位" in compact or "OrbSlot" in compact:
        return True
    return False


class ModPipeServer:
    def __init__(self, host: str, port: int, min_response_delay: float):
        self._host = host
        self._port = port
        self._min_response_delay = max(min_response_delay, 0.0)
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._state_counter = 0
        self._latest_state = None
        self._last_sent_sections = None
        self._conn = None
        self._thread = threading.Thread(target=self._serve, name="SlayTheSpireModPipe", daemon=True)
        self._thread.start()

    def _serve(self):
        try:
            log_error(f"Starting server thread on {self._host}:{self._port}...")
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                server.bind((self._host, self._port))
            except Exception as e:
                log_error(f"CRITICAL: Failed to bind to {self._host}:{self._port}: {e}")
                return
            server.listen(1)
            log_error(f"Server listening on {self._host}:{self._port}")
            while True:
                try:
                    conn, addr = server.accept()
                except Exception as e:
                    log_error(f"Accept error: {e}")
                    continue
                with self._lock:
                    if self._conn:
                        try:
                            self._conn.close()
                        except Exception:
                            pass
                    self._conn = conn
                log_error(f"Connected by game process at {addr}")
                try:
                    conn.sendall(b"ready\n")
                except Exception as e:
                    log_error(f"Failed to send ready signal: {e}")
                    continue
                buffer = b""
                while True:
                    try:
                        data = conn.recv(4096)
                    except Exception as e:
                        log_error(f"Connection error: {e}")
                        break
                    if not data:
                        log_error("Connection closed by game process.")
                        break
                    buffer += data
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line.decode("utf-8", "replace"))
                        except Exception as e:
                            log_error(f"JSON parse error from game: {e} | Raw line: {line[:100]}...")
                            continue
                        with self._lock:
                            self._latest_state = payload
                            self._state_counter += 1
                            self._cond.notify_all()
                with self._lock:
                    if self._conn is conn:
                        self._conn = None
        except Exception as e:
            log_error(f"CRITICAL: Unexpected error in server thread: {e}")
            import traceback
            log_error(traceback.format_exc())

    def get_manual(self) -> str:
        return (
            "Slay the Spire Game Manual:\n"
            "1. Combat: Use 'play card_index monster_index' (e.g. 'play 1 0'). Card indices are 1-based. Monster indices are 0-based (only alive monsters, re-indexed dynamically).\n"
            "2. Ending Turn: Use 'end'.\n"
            "3. Choices: Use 'choose choice_index' (e.g. 'choose 0').\n"
            "4. Potions: Use 'potion use/discard potion_index' (e.g. 'potion use 0'). Potion indices are 0-based (includes empty slots). For target potions (Fire, Weak, etc.), add monster_index (e.g. 'potion use 0 1').\n"
            "5. General: Use 'wait' to poll for stable state."
        )

    def send_command(self, command: str) -> dict:
        if not command:
            return {"status": "error", "message": "command is empty"}
        with self._lock:
            conn = self._conn
        if not conn:
            return {"status": "no_connection", "message": "mod not connected"}
        try:
            conn.sendall((command.strip() + "\n").encode("utf-8"))
        except Exception as e:
            return {"status": "error", "message": str(e)}
        return {"status": "ok"}

    def wait_for_state(self, timeout: float) -> dict | None:
        with self._lock:
            if timeout <= 0:
                return self._latest_state
            start_counter = self._state_counter
            end_time = time.time() + timeout
            while self._state_counter == start_counter:
                remaining = end_time - time.time()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
            return self._latest_state

    def wait_for_ready_state(self, timeout: float) -> dict | None:
        end_time = time.time() + max(timeout, 0.0)
        while True:
            with self._lock:
                payload = self._latest_state
                if self._is_payload_ready(payload):
                    return payload
                if timeout <= 0:
                    return payload
                start_counter = self._state_counter
                remaining = end_time - time.time()
                if remaining <= 0:
                    return payload
                while self._state_counter == start_counter:
                    remaining = end_time - time.time()
                    if remaining <= 0:
                        return payload
                    self._cond.wait(remaining)

    def _apply_min_delay(self, start_time: float):
        if self._min_response_delay <= 0:
            return
        elapsed = time.time() - start_time
        remaining = self._min_response_delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def reset_cache(self):
        with self._lock:
            self._last_sent_sections = None

    def _extract_sections(self, payload: dict) -> tuple[dict, dict]:
        meta = {
            "in_game": False,
            "ready_for_command": False,
            "available_commands": [],
            "error": None
        }
        if not isinstance(payload, dict):
            return {}, meta
            
        meta["error"] = payload.get("error")
        meta["ready_for_command"] = bool(payload.get("ready_for_command"))
        meta["available_commands"] = payload.get("available_commands") or []
        
        in_game = payload.get("in_game")
        game_state = payload.get("game_state")
        
        if meta["error"] and not game_state:
            if self._last_sent_sections:
                meta["in_game" ] = True
                return self._last_sent_sections, meta

        meta["in_game"] = bool(in_game)
        if not meta["in_game"]:
            return {}, meta
            
        game_state = game_state or {}
        sections = {}
        sections["screen_type"] = game_state.get("screen_type")
        sections["screen_state"] = game_state.get("screen_state") or {}
        combat_state = game_state.get("combat_state") or {}
        player_state = combat_state.get("player")
        if not player_state:
            player_state = {
                "current_hp": game_state.get("current_hp"),
                "max_hp": game_state.get("max_hp"),
                "block": 0,
                "energy": 0,
                "powers": [],
                "orbs": [],
                "max_orbs": 0,
                "stance": "Neutral"
            }
        sections["player"] = player_state
        sections["monsters" ] = combat_state.get("monsters", [])
        sections["relics"] = game_state.get("relics", [])
        sections["hand"] = combat_state.get("hand", [])
        sections["draw_pile"] = combat_state.get("draw_pile", [])
        sections["discard_pile"] = combat_state.get("discard_pile", [])
        sections["exhaust_pile"] = combat_state.get("exhaust_pile", [])
        sections["potions"] = game_state.get("potions", [])
        sections["room_phase"] = game_state.get("room_phase")
        sections["turn"] = combat_state.get("turn", 0)
        selection = self._build_selection(game_state)
        if selection:
            sections["selection"] = selection
        sections = self._strip_unwanted_fields(sections)
        return sections, meta

    def _strip_unwanted_fields(self, obj):
        strip_keys = {
            "uuid",
            "cX",
            "cY",
            "hb_x",
            "hb_y",
            "hb_w",
            "hb_h",
            "rarity",
            "upgrades",
            "anim_name"
        }
        if isinstance(obj, dict):
            cleaned = {}
            for k, v in obj.items():
                if k in strip_keys:
                    continue
                cleaned[k] = self._strip_unwanted_fields(v)
            return cleaned
        if isinstance(obj, list):
            return [self._strip_unwanted_fields(item) for item in obj]
        return obj

    def _is_payload_ready(self, payload: dict | None) -> bool:
        if not isinstance(payload, dict):
            return False
        if not payload.get("in_game"):
            return True
        return bool(payload.get("ready_for_command"))

    def _build_selection(self, game_state: dict) -> dict | None:
        screen_type = game_state.get("screen_type")
        screen_state = game_state.get("screen_state") or {}
        choice_list = game_state.get("choice_list")
        if screen_type == "HAND_SELECT":
            return {
                "required": True,
                "type": "hand",
                "screen_type": screen_type,
                "max_cards": screen_state.get("max_cards"),
                "can_pick_zero": screen_state.get("can_pick_zero"),
                "cards": screen_state.get("hand", []),
                "selected": screen_state.get("selected", [])
            }
        if screen_type == "GRID":
            return {
                "required": True,
                "type": "grid",
                "screen_type": screen_type,
                "num_cards": screen_state.get("num_cards"),
                "any_number": screen_state.get("any_number"),
                "cards": screen_state.get("cards", []),
                "selected": screen_state.get("selected_cards", []),
                "source_group": screen_state.get("source_group")
            }
        if choice_list:
            return {
                "required": True,
                "type": "choice",
                "screen_type": screen_type,
                "options": choice_list
            }
        return None

    def _is_meaningful_change(self, old, new) -> bool:
        if type(old) != type(new):
            return True
            
        if isinstance(old, dict):
            all_keys = set(old.keys()) | set(new.keys())
            for k in all_keys:
                if k in ("uuid", "cX", "cY", "hb_x", "hb_y", "hb_w", "hb_h", "anim_name", "rarity", "upgrades"):
                    continue 
                if k not in old or k not in new:
                    return True
                if self._is_meaningful_change(old[k], new[k]):
                    return True
            return False
            
        if isinstance(old, list):
            if len(old) != len(new):
                return True
            for i in range(len(old)):
                if self._is_meaningful_change(old[i], new[i]):
                    return True
            return False
            
        if isinstance(old, float):
            return abs(old - new) > 1.0
            
        return old != new

    def _compact_card(self, card: dict) -> dict:
        if not isinstance(card, dict):
            return card
        keys = ("name", "id", "cost", "type", "description", "is_playable", "damage", "block", "magic_number", "has_target", "ethereal", "exhausts")
        return {k: card.get(k) for k in keys if k in card}

    def _compact_orb(self, orb: dict) -> dict:
        if not isinstance(orb, dict):
            return orb
        is_next = orb.get("next_to_evoke", False)
        name = orb.get("name", "Unknown")
        
        if name == "充能球栏位" or "Slot" in name:
            name = "Empty Slot"
            
        if is_next and name != "Empty Slot":
            name = f"== NEXT TO EVOKE == {name}"
        
        keys = ("id", "passive_amount", "evoke_amount", "index")
        res = {"name": name}
        for k in keys:
            if k in orb: res[k] = orb.get(k)
        res["is_next_to_evoke"] = is_next
        return res

    def _compact_power(self, power: dict) -> dict:
        if not isinstance(power, dict):
            return power
        keys = ("name", "id", "amount", "description")
        return {k: power.get(k) for k in keys if k in power}

    def _compact_monster(self, monster: dict) -> dict:
        if not isinstance(monster, dict):
            return monster
        keys = ("name", "id", "current_hp", "max_hp", "block", "intent", "intent_description", "move_adjusted_damage", "move_hits", "is_gone")
        compact = {k: monster.get(k) for k in keys if k in monster}
        powers = monster.get("powers", [])
        if isinstance(powers, list):
            compact["powers"] = [self._compact_power(p) for p in powers]
        return compact

    def _compact_relic(self, relic: dict) -> dict:
        if not isinstance(relic, dict):
            return relic
        keys = ("name", "id", "counter", "description")
        return {k: relic.get(k) for k in keys if k in relic}

    def _compact_potion(self, potion: dict) -> dict:
        if not isinstance(potion, dict):
            return potion
        keys = ("name", "id", "can_use", "requires_target", "can_discard", "description")
        return {k: potion.get(k) for k in keys if k in potion}

    def _compact_player(self, player: dict) -> dict:
        if not isinstance(player, dict):
            return player
        compact = {}
        for k in ("current_hp", "max_hp", "block", "energy", "max_orbs", "stance"):
            if k in player:
                compact[k] = player.get(k)
        powers = player.get("powers", [])
        if isinstance(powers, list):
            compact["powers"] = [self._compact_power(p) for p in powers]
        orbs = player.get("orbs", [])
        if isinstance(orbs, list):
            compact["orbs"] = [self._compact_orb(o) for o in orbs]
        return compact

    def _compact_section(self, key: str, value):
        if key in ("draw_pile", "discard_pile", "exhaust_pile"):
            if isinstance(value, list):
                return [self._compact_card(c) for c in value]
            return []
        if key == "hand":
            if isinstance(value, list):
                return [self._compact_card(c) for c in value]
        if key == "player":
            return self._compact_player(value)
        if key == "monsters":
            if isinstance(value, list):
                return [self._compact_monster(m) for m in value]
        if key == "relics":
            if isinstance(value, list):
                return [self._compact_relic(r) for r in value]
        if key == "potions":
            if isinstance(value, list):
                return [self._compact_potion(p) for p in value]
        if key == "selection" and isinstance(value, dict):
            compact = dict(value)
            cards = compact.get("cards")
            if isinstance(cards, list):
                compact["cards"] = [self._compact_card(c) for c in cards]
            return compact
        return value

    def _compact_sections(self, sections: dict) -> dict:
        if not isinstance(sections, dict):
            return sections
        return {k: self._compact_section(k, v) for k, v in sections.items()}

    def get_state(self, wait: float = 0.0, force_full: bool = False, delta: bool = True, for_subagent: bool = False) -> dict:
        start_time = time.time()
        payload = self.wait_for_ready_state(wait)
        sections, meta = self._extract_sections(payload or {})
        
        result = {
            "status": "ok",
            "full": False,
            "sections": {},
            "meta": meta
        }

        if not meta.get("in_game"):
            self._apply_min_delay(start_time)
            result["full"] = force_full or self._last_sent_sections is None or not delta
            if meta.get("error"):
                result["status"] = "error"
                result["message"] = meta["error"]
            return result

        if meta.get("error"):
            result["status"] = "error"
            result["message"] = meta["error"]
            if delta and self._last_sent_sections is not None and not force_full:
                reduced = {}
                for k in ("screen_type", "player", "monsters", "hand", "room_phase", "turn"):
                    if k in sections:
                        reduced[k] = sections[k]
                result["sections"] = self._compact_sections(reduced)
            else:
                result["sections"] = sections
            return result

        is_busy = not meta.get("ready_for_command")
        
        if for_subagent:
            force_full = True

        if force_full or self._last_sent_sections is None or not delta:
            self._last_sent_sections = sections
            self._apply_min_delay(start_time)
            result["full"] = True
            result["sections"] = self._compact_sections(sections)
            if is_busy:
                result["status"] = "waiting"
                result["message"] = "Game is busy (animating or enemy turn)."
            return result

        changed = {}
        for key, value in sections.items():
            if self._is_meaningful_change(self._last_sent_sections.get(key), value):
                changed[key] = value
        
        if is_busy:
            result["status"] = "waiting"
            result["message"] = "Game is busy (animating or enemy turn)."
            if changed:
                result["sections"] = self._compact_sections(changed)
        else:
            if changed:
                log_error(f"Delta update: changed sections: {list(changed.keys())}")
                result["sections"] = self._compact_sections(changed)
            else:
                log_error("Delta update: no meaningful changes detected.")
                result["message"] = "No meaningful state changes detected."
        
        self._last_sent_sections = sections
        self._apply_min_delay(start_time)
        return result

_host, _port, _min_delay = _load_config()
_server = ModPipeServer(_host, _port, _min_delay)


@mcp.tool()
def sts_get_manual() -> str:
    """Get a detailed manual on how to use the Slay the Spire delegation tools.
    """
    return (
        "### Slay the Spire Sub-agent Delegation Manual ###\n\n"
        "The Slay the Spire integration now uses a Sub-agent architecture. "
        "The main agent should only perform high-level tasks:\n\n"
        "1. **Observation**: Use `sts_get_full_state()` to see the current situation.\n"
        "2. **Delegation**: \n"
        "   - Use `game_play_battle()` to let an expert sub-agent fight the ENTIRE BATTLE from start to finish (including rewards).\n"
        "     This is the recommended tool for automating a full combat encounter.\n"
        "   - Use `game_play_turn()` ONLY if you need fine-grained control over individual turns.\n"
        "     Note: `game_play_turn()` returns after each turn ends, so you must call it repeatedly.\n"
        "3. **Reporting**: After delegation, the sub-agent will return a summary of the battle or turn.\n\n"
        "Note: You do NOT need to worry about card indices or energy. The sub-agent handles all tactical execution."
    )


@mcp.tool()
def sts_subagent_get_config() -> dict:
    """[PRIVATE] Return configuration for the StS sub-agent.
    """
    return {
        "prune_history": True,
        "hide_tools_pattern": "^sts_get_(?!manual).*",
        "main_prune_pattern": "^sts_(?!get_manual).*",
        "mandatory_instruction": (
            "You MUST use tools (sts_play_cards, sts_end_turn) to perform actions. Do NOT just output JSON.\n"
            "- Card indices are 1-based (1..N). Monster indices are 0-based (0..M).\n"
            "- If playing Attack cards, you MUST specify 'monster_index' (usually 0).\n"
            "- INFO: All 'sts_get_*' tools are DISABLED. Rely on the state provided in the result of your previous action.\n"
            "- Call 'sts_end_turn' when you are out of energy or moves."
        )
    }


@mcp.tool()
def sts_subagent_check_finished(tool_name: str, last_result: str, last_calls: list[dict]) -> dict:
    """[PRIVATE] Check if the sub-agent task is finished.
    """
    finished = False
    reason = ""
    
    state = _server.get_state(delta=False, for_subagent=True)
    sec = state.get("sections", {})
    monsters = sec.get("monsters", [])
    active = [m for m in monsters if isinstance(m, dict) and not m.get("is_gone")]
    
    if state.get("status") == "error" and "not in a game" in state.get("message", "").lower():
        return {"finished": True, "reason": "Game ended or not in game."}

    if sec.get("room_phase") != "COMBAT" or not active:
        finished = True
        reason = "Combat ended."
    elif tool_name == "sts_play_turn":
        if any(c.get("function", {}).get("name") == "sts_end_turn" for c in last_calls):
            finished = True
            reason = "Turn ended."
            
    return {"finished": finished, "reason": reason}


@mcp.tool()
def sts_subagent_summarize_result(initial_state: str, final_state: str, tool_name: str, report: str) -> str:
    """[PRIVATE] Generate a summary of the sub-agent's work.
    """
    def safe_json(s):
        try: return json.loads(s)
        except:
            m = re.search(r"({.*})", s, re.DOTALL)
            if m:
                try: return json.loads(m.group(1))
                except: pass
        return {}

    before = safe_json(initial_state)
    after = safe_json(final_state)
    
    b_sec = before.get("sections", {})
    a_sec = after.get("sections", {})
    
    b_hp = b_sec.get("player", {}).get("current_hp")
    a_hp = a_sec.get("player", {}).get("current_hp")
    hp_change = (a_hp - b_hp) if (isinstance(b_hp, (int, float)) and isinstance(a_hp, (int, float))) else 0
    
    b_pots = [p.get("name") for p in b_sec.get("potions", []) if isinstance(p, dict)]
    a_pots = [p.get("name") for p in a_sec.get("potions", []) if isinstance(p, dict)]
    pots_used = [p for p in b_pots if p not in a_pots]
    
    monsters = a_sec.get("monsters", [])
    active = [m for m in monsters if isinstance(m, dict) and not m.get("is_gone")]
    status = "finished" if (a_sec.get("room_phase") != "COMBAT" or not active) else "ongoing"
    
    summary = {
        "status": "ok",
        "mode": tool_name,
        "combat_status": status,
        "hp_change": hp_change,
        "potions_used": pots_used,
        "subagent_report": report
    }
    return json.dumps(summary, ensure_ascii=False)


@mcp.tool()
def sts_get_subagent_prompt(mode: str = "turn") -> str:
    """[PRIVATE] Return expert system prompt for the StS sub-agent.
    Args:
        mode: "turn" or "battle"
    """
    base = (
        "You are an EXPERT Slay the Spire combat sub-agent. "
        "You see ONLY the current full state and must play optimally. "
        "STRICT CONSTRAINTS:\n"
        "1. You MUST use tools (sts_play_cards, sts_end_turn) to perform actions. Do NOT just output JSON.\n"
        "2. NO GETTERS: All 'sts_get_*' tools are disabled for you. Rely on the full state provided in the 'INITIAL_STATE' and tool results.\n"
        "3. EVERY tool call MUST include a 'thinking' parameter explaining your logic.\n"
        "4. TARGETING: Attack cards (Strike, Bash, etc.) ALWAYS require a 'monster_index' (0, 1, 2...).\n"
        "   - Even if there is only one monster, you MUST specify monster_index: 0.\n"
        "   - Failure to provide monster_index for attack cards will cause an error.\n"
        "   - Card indices are 1-based in your hand. NEVER use 0 as card_index.\n"
        "5. ORB MECHANICS: 'Evoke' (Dualcast) always triggers index 0 (is_next_to_evoke: true).\n"
        "6. POTIONS: Use them if they help you win or prevent massive damage.\n"
        "   - Note: Some potions (like PowerPotion) open a CHOICE screen. You MUST call 'sts_choose' before playing more cards.\n"
        "7. CHOICE SCREENS: If screen_type is NOT 'NONE' (e.g. CARD_REWARD, HAND_SELECT), you MUST use 'sts_choose' to resolve it first.\n"
        "   - Use 'sts_choose(choice=\"0\")' to pick the first option, '1' for second, etc.\n"
        "   - Check the 'selection' field in the state to see available options.\n"
        "8. TURN END: Always call sts_end_turn() when you are out of energy or useful moves.\n"
        "9. DO NOT call 'sts_play_turn' or 'sts_play_battle' yourself. You are the worker, use worker tools.\n"
        "10. If you get a 'requires target' error, it means you forgot the monster_index. Try again with the index.\n"
        "11. Do NOT assume card effects. Use the card description in the state.\n"
        "ONLY return a text report once the turn/battle is finished."
    )
    if mode == "battle":
        return (
            base
            + "\n9. Continue playing turns until victory or defeat is achieved."
        )
    return base


@mcp.tool()
def sts_wait(frames: int = 60, thinking: str = "") -> dict:
    """[PRIVATE] Wait for a number of frames in the game.
    Args:
        frames: Number of frames to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    return sts_send(f"wait {frames}", wait=0.5)


@mcp.tool()
def sts_get_full_state(wait: float = 0.0, thinking: str = "") -> dict:
    """Get the current FULL game state (no delta).
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    return _server.get_state(wait=wait, force_full=True, delta=False, for_subagent=True)


@mcp.tool()
def sts_play_turn(question: str = "") -> dict:
    """[SUBAGENT] Delegate one full turn to a sub-agent.
    The host should treat the result as if it played the turn itself.
    """
    return {
        "status": "error",
        "message": "This tool must be executed by the host sub-agent runner.",
        "suggestion": "Call this tool through the host program, not directly from MCP."
    }


@mcp.tool()
def game_play_battle(question: str = "") -> str:
    """[SUBAGENT] Delegate an entire 'Slay the Spire' battle to an expert sub-agent.
    Use this when you want the sub-agent to control the entire battle from start to finish,
    including all turns and reward selection. The sub-agent will return a summary when the battle is completely over.
    """
    _ws_connector.call_mod("game_play_battle", {"question": question})
    
    return json.dumps({
        "status": "delegate",
        "mode": "battle",
        "question": question
    })


@mcp.tool()
def game_play_turn(question: str = "") -> str:
    """[SUBAGENT] Delegate the current turn of 'Slay the Spire' to an expert sub-agent.
    Use this for tactical turn-by-turn execution. Note: this returns after each turn ends,
    so you must call it repeatedly for subsequent turns. For full battle automation, use game_play_battle instead.
    """
    _ws_connector.call_mod("game_play_turn", {"question": question})
    
    return json.dumps({
        "status": "delegate",
        "mode": "turn",
        "question": question
    })


@mcp.tool()
def game_sts_get_status() -> str:
    """Check the current status of Slay the Spire. 
    Use this to see if a game is running, if you are in combat, and what the current floor/HP is.
    This tool returns a concise natural language summary for the main agent.
    """
    ws_res = _ws_connector.call_mod("sts_get_state", {"full": True, "delta": False, "summary_only": True})
    if isinstance(ws_res, dict) and ws_res.get("type") == "mcp_response":
        result = ws_res.get("result", {})
        summary = result.get("text_summary")
        if summary:
            return summary
        return json.dumps(result, indent=2)
    
    log_error("WebSocket status fetch failed, falling back to legacy ModPipe.")
    state = _server.get_state(wait=0, force_full=True, delta=False, for_subagent=True)
    return json.dumps(state, indent=2)


@mcp.tool()
def game_sts_get_manual() -> str:
    """Get the operation manual for Slay the Spire.
    Includes details about game mechanics, card types, and how to interpret the game state.
    """
    return _server.get_manual()


@mcp.tool()
def sts_get_state(wait: float = 0.0, full: bool = False, delta: bool = True, thinking: str = "") -> dict:
    """[PRIVATE] Get the current game state.
    Args:
        wait: Seconds to wait.
        full: Bypass delta.
        delta: Only return changes.
        thinking: Your thought process (2-3 sentences max).
    """
    ws_res = _ws_connector.call_mod("sts_get_state", {"full": full, "delta": delta, "wait": wait})
    if isinstance(ws_res, dict) and ws_res.get("type") == "mcp_response":
        return ws_res.get("result", {})

    return _server.get_state(wait=wait, force_full=full, delta=delta, for_subagent=True)


@mcp.tool()
def sts_send(command: str, wait: float = 1.0, delta: bool = True) -> dict:
    """[PRIVATE] Send a raw command to the game and return the updated state.
    Available commands: play, end, choose, potion, key, click.
    Args:
        command: The command string to send (e.g. 'play 1 0', 'end').
        wait: Seconds to wait for the command to execute and state to stabilize.
        delta: If True, only return changes in state.
    """
    tokens = command.strip().split()
    if not tokens:
        return {"status": "error", "message": "command is empty"}
    command_name = tokens[0].lower()

    state = None
    sections = {}
    if command_name in ("end", "play", "key", "click", "choose", "potion"):
        state = _server.get_state(delta=False, for_subagent=True)
        status = state.get("status")
        sections = state.get("sections", {}) or {}
        if status == "waiting":
            return {
                "status": "waiting",
                "message": "Game is busy (animating or enemy turn).",
                "suggestion": "Game is busy. Wait and poll again until ready_for_command is True.",
                "sections": sections
            }
        if status == "error":
            return {
                "status": "error",
                "message": state.get("message") or "Mod reported error. Check the battlefield and try again.",
                "suggestion": "The current state is unstable. Please call sts_get_state to sync before taking further actions.",
                "sections": sections
            }
        meta = state.get("meta", {}) or {}
        available = meta.get("available_commands") or []
        if available and command_name not in available:
            return {
                "status": "error",
                "message": f"Invalid command: {command_name}. Possible commands: {available}",
                "suggestion": f"The command '{command_name}' is not available right now. Choose from {available}.",
                "sections": sections
            }

    if command_name == "end":
        player = sections.get("player", {})
        energy = player.get("energy", 0)
        hand = sections.get("hand", [])
        playable_cards = [c for c in hand if c.get("is_playable")]
        if energy > 0 and playable_cards:
            return {
                "status": "error",
                "message": f"CRITICAL SAFETY INTERCEPT: You have {energy} energy and {len(playable_cards)} playable cards. Ending the turn now might be a mistake.",
                "suggestion": "You still have energy and playable cards. Review the state (sts_get_state) before ending. If intentional, use sts_end_turn(force=True).",
                "sections": sections
            }
    if command_name == "play":
        if len(tokens) < 2 or not tokens[1].isdigit() or int(tokens[1]) <= 0:
            return {
                "status": "error",
                "message": f"Invalid play command: {command}. Card index must be a positive integer.",
                "suggestion": "Use sts_play_card(card_index=1..N) and ensure the index is valid.",
                "sections": sections
            }
        card_index = int(tokens[1])
        hand = sections.get("hand", [])
        if hand and card_index > len(hand):
            return {
                "status": "error",
                "message": f"Invalid play command: card_index {card_index} out of bounds (hand size {len(hand)}).",
                "suggestion": "Call sts_get_state to check your hand before choosing an index.",
                "sections": sections
            }
    if command_name == "key":
        if len(tokens) < 2:
            return {
                "status": "error",
                "message": "Invalid key command: missing key argument.",
                "suggestion": "Provide a valid key name (e.g., 'esc', 'enter').",
                "sections": sections
            }
        if tokens[1].isdigit():
            return {
                "status": "error",
                "message": f"Invalid key command: {command}.",
                "suggestion": "Digit keys are not valid inputs here. Use key names.",
                "sections": sections
            }

    result = _server.send_command(command)
    if result.get("status") != "ok":
        msg = result.get("message", "")
        screen = sections.get("screen_type", "NONE")
        if "Selected card cannot be played with the selected target" in msg and screen != "NONE":
            result["message"] = f"ERROR: You cannot play cards while a choice screen is up (Current: {screen}). Use 'sts_choose' or 'sts_send' to resolve the screen first."
            result["suggestion"] = f"A choice screen ({screen}) is active. You MUST resolve it before playing cards."
        elif "Selected card requires an enemy target" in msg:
            result["message"] = "ERROR: You attempted to play an attack without a valid target."
            result["suggestion"] = "Use sts_play_card/ sts_play_cards with monster_index (0..). Card indices are 1-based from the hand list."
        elif "Selected card cannot be played with the selected target" in msg:
            result["message"] = "ERROR: The selected card cannot be played with that target."
            result["suggestion"] = "Re-sync with sts_get_state and choose a playable card index (1..N) and a valid monster_index."
        return result
    return _server.get_state(wait=wait, force_full=False, delta=delta, for_subagent=True)


@mcp.tool()
def sts_play_card(card_index: int, monster_index: int = -1, wait: float = 1.5, thinking: str = "") -> dict:
    """[PRIVATE] Play a single card from hand.
    Args:
        card_index: 1-based index of the card.
        monster_index: 0-based index of the monster.
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    state = _server.get_state(delta=False, for_subagent=True)
    status = state.get("status")
    if status != "ok":
        return state
    sections = state.get("sections", {}) or {}
    screen = sections.get("screen_type", "NONE")
    if screen != "NONE":
        return {
            "status": "error",
            "message": f"Cannot play card '{card_index}' because a choice screen ({screen}) is up.",
            "suggestion": f"Use 'sts_choose' or appropriate tool to resolve the {screen} screen first.",
            "sections": sections
        }

    hand = sections.get("hand", [])
    if not isinstance(card_index, int) or card_index <= 0:
        return {
            "status": "error",
            "message": f"Invalid card_index: {card_index}. Card index must be a positive integer.",
            "suggestion": "Check the number of cards in your hand using sts_get_state before choosing an index.",
            "sections": sections
        }
    if hand and card_index > len(hand):
        return {
            "status": "error",
            "message": f"Invalid card_index: {card_index}. Hand size is {len(hand)}.",
            "suggestion": "Check the number of cards in your hand using sts_get_state before choosing an index.",
            "sections": sections
        }
    if hand:
        card = hand[card_index - 1]
        if not card.get("is_playable"):
            return {
                "status": "error",
                "message": f"Card '{card.get('name')}' is not playable right now.",
                "suggestion": "Try playing a different card that is marked as is_playable.",
                "sections": sections
            }
        if card.get("has_target") and monster_index == -1:
            return {
                "status": "error",
                "message": f"Card '{card.get('name')}' requires a target.",
                "suggestion": "Provide a monster_index parameter.",
                "sections": sections
            }
    if monster_index != -1:
        monsters = sections.get("monsters", [])
        if monster_index < 0 or monster_index >= len(monsters) or monsters[monster_index].get("is_gone"):
            return {
                "status": "error",
                "message": f"Invalid monster_index: {monster_index}. Monster does not exist or is dead.",
                "suggestion": "Check the 'monsters' list for valid indices.",
                "sections": sections
            }
    
    if hand:
        card = hand[card_index - 1]
        if card.get("has_target") and monster_index == -1:
             return {
                "status": "error",
                "message": f"Card '{card.get('name')}' requires a target but monster_index was not provided.",
                "suggestion": "Specify a 'monster_index' (0, 1, 2...) for this card.",
                "sections": sections
            }

    cmd = f"play {card_index}"
    if monster_index != -1:
        cmd += f" {monster_index}"
    return sts_send(cmd, wait=wait, delta=True)


@mcp.tool()
def sts_choose(choice: str, wait: float = 1.0, thinking: str = "") -> dict:
    """[PRIVATE] Make a choice from a screen (rewards, events, card select).
    Args:
        choice: The choice string or index.
        wait: Seconds to wait for state update.
        thinking: Your thought process (2-3 sentences max).
    """
    return sts_send(f"choose {choice}", wait=wait, delta=True)


@mcp.tool()
def sts_end_turn(wait: float = 5.0, force: bool = False, thinking: str = "") -> dict:
    """[PRIVATE] End the current turn.
    Args:
        wait: Seconds to wait for animations and enemy turn.
        force: If True, skip the safety check (energy/playable cards).
        thinking: Your thought process (2-3 sentences max).
    """
    if force:
        result = _server.send_command("end")
        if result.get("status") != "ok":
            return result
        return _server.get_state(wait=wait, force_full=False, delta=True)
    return sts_send("end", wait=wait, delta=True)


@mcp.tool()
def sts_play_cards(cards: list[dict], wait: float = 1.0, thinking: str = "") -> dict:
    """[PRIVATE] Play multiple cards in a single sequence.
    Args:
        cards: A list of dicts, each with 'card_index' (1-based) and optional 'monster_index' (0-based).
               Example: [{"card_index": 1, "monster_index": 0}, {"card_index": 2}]
        wait: Seconds to wait after the last card is played.
        thinking: Your thought process (2-3 sentences max).
    """
    last_result = {"status": "ok", "message": "No cards played"}
    
    played_indices = []
    
    for i, play_info in enumerate(cards):
        orig_card_idx = play_info.get("card_index")
        monster_idx = play_info.get("monster_index", -1)
        
        if not orig_card_idx:
            continue
        shift = len([idx for idx in played_indices if idx < orig_card_idx])
        current_card_idx = orig_card_idx - shift
        
        state = _server.get_state(delta=False, for_subagent=True)
        if state.get("status") != "ok":
            return state
            
        sections = state.get("sections", {}) or {}
        screen = sections.get("screen_type", "NONE")
        if screen != "NONE":
            return {
                "status": "error",
                "message": f"Cannot play cards because a choice screen ({screen}) is up.",
                "suggestion": f"Use 'sts_choose' or appropriate tool to resolve the {screen} screen first.",
                "sections": sections
            }

        hand = sections.get("hand", [])
        
        if current_card_idx <= 0 or current_card_idx > len(hand):
            return {
                "status": "error",
                "message": f"Step {i+1}: Adjusted card_index {current_card_idx} (originally {orig_card_idx}) out of bounds. Hand size is {len(hand)}.",
                "suggestion": "Card sequence interrupted. Your indices might have been based on a stale state or the shift logic failed. Try playing cards one by one or providing a new sequence.",
                "sections": sections
            }
            
        card = hand[current_card_idx - 1]
        if not card.get("is_playable"):
            return {
                "status": "error",
                "message": f"Step {i+1}: Card '{card.get('name')}' (Adjusted index {current_card_idx}) is not playable.",
                "suggestion": "Insufficient energy or requirements not met. Re-evaluate your remaining moves.",
                "sections": sections
            }
        
        if card.get("has_target") and monster_idx == -1:
            return {
                "status": "error",
                "message": f"Step {i+1}: Card '{card.get('name')}' (Adjusted index {current_card_idx}) requires a monster_index.",
                "suggestion": "Please provide a 'monster_index' (0, 1, 2...) for attack cards.",
                "sections": sections
            }
            
        cmd = f"play {current_card_idx}"
        if monster_idx != -1:
            cmd += f" {monster_idx}"
            
        is_last = (i == len(cards) - 1)
        step_wait = wait if is_last else 0.5
        
        last_result = sts_send(cmd, wait=step_wait, delta=True)
        played_indices.append(orig_card_idx)
        
        if last_result.get("status") != "ok":
            return last_result
            
    return last_result


@mcp.tool()
def sts_use_potion(index: int, monster_index: int = -1, wait: float = 1.0, thinking: str = "") -> dict:
    """[PRIVATE] Use a potion from the potion bar.
    Args:
        index: 0-based index of the potion slot.
        monster_index: 0-based index of the monster (if required).
        wait: Seconds to wait for animations.
        thinking: Your thought process (2-3 sentences max).
    """
    cmd = f"potion use {index}"
    if monster_index != -1:
        cmd += f" {monster_index}"
    return sts_send(cmd, wait=wait)


@mcp.tool()
def sts_get_combat_summary(thinking: str = "") -> str:
    """[PRIVATE] Get a concise, human-readable summary of the combat state.
    Args:
        thinking: Your thought process (2-3 sentences max).
    """
    state = _server.get_state(delta=False, for_subagent=True)
    status = state.get("status")
    
    meta = state.get("meta", {})
    sections = state.get("sections", {})
    if not meta.get("in_game") and not sections:
        return "Not currently in a game."
    
    room_phase = sections.get("room_phase")
    monsters = sections.get("monsters", [])
    active_monsters = [m for m in monsters if not m.get("is_gone")]

    screen_type = sections.get("screen_type", "NONE")
    selection = sections.get("selection")

    if screen_type != "NONE":
        summary = [f"!!! CHOICE SCREEN ACTIVE: {screen_type} !!!"]
        summary.append("You MUST resolve this screen before playing cards or ending turn.")
        if selection:
            summary.append(f"\nOptions to choose from (use sts_choose):")
            if selection.get("type") == "choice":
                for i, opt in enumerate(selection.get("options", [])):
                    summary.append(f"[{i}] {opt}")
            elif selection.get("type") in ("hand", "grid"):
                cards = selection.get("cards", [])
                for i, c in enumerate(cards):
                    summary.append(f"[{i}] {c.get('name')} : {c.get('description', '')}")
        return "\n".join(summary)

    if not active_monsters or room_phase != "COMBAT":
        return "!!! VICTORY !!!\nCombat is finished. Task completed. You can stop now."

    player = sections.get("player", {})
    hand = sections.get("hand", [])
    
    summary = []
    
    if status == "waiting":
        summary.append("!!! WARNING: GAME IS BUSY (ANIMATING/ENEMY TURN) !!!")
        summary.append("State below might be slightly outdated. Please wait and poll again if needed.\n")

    summary.append(f"--- Turn {sections.get('turn', 1)} ---")
    summary.append("Hand indices are 1-based. Use card_index=1..N.")
    player_line = f"HP:{player.get('current_hp')}/{player.get('max_hp')} | BLK:{player.get('block')} | NRG:{player.get('energy')}"
    if player.get("stance") and player.get("stance") != "Neutral":
        player_line += f" | {player.get('stance')}"
    summary.append(player_line)
    
    orbs = player.get("orbs", [])
    max_orbs = player.get("max_orbs", 0)
    if max_orbs > 0:
        orb_strs = []
        active_orbs = [o for o in orbs if not _is_empty_orb(o)]
        for i in range(max_orbs):
            if i < len(orbs):
                o = orbs[i]
                prefix = "*" if (o.get('next_to_evoke') or (i == 0 and not _is_empty_orb(o))) else ""
                orb_strs.append(f"{prefix}{o.get('name')}(P:{o.get('passive_amount')},E:{o.get('evoke_amount')})")
            else:
                orb_strs.append("[EMPTY]")
        summary.append(f"Orbs: {'|'.join(orb_strs)}")
    
    relics = sections.get("relics", [])
    if relics:
        summary.append(f"Relics: {', '.join([r.get('name') for r in relics])}")

    potions = sections.get("potions", [])
    if potions:
        pots_strs = []
        for p in potions:
            name = p.get("name")
            desc = p.get("description")
            if desc:
                pots_strs.append(f"{name}({desc})")
            else:
                pots_strs.append(name)
        summary.append(f"Potions: {', '.join(pots_strs)}")

    powers = [f"{p.get('name')}({p.get('amount')})" for p in player.get("powers", [])]
    if powers:
        summary.append(f"Powers: {', '.join(powers)}")
    
    summary.append("\n--- Monsters ---")
    for i, m in enumerate(monsters):
        if m.get("is_gone"): continue
        m_info = f"[{i}]{m.get('name')}: {m.get('current_hp')}/{m.get('max_hp')} | Intent:{m.get('intent')}"
        if m.get("move_adjusted_damage") is not None:
            m_info += f" ({m.get('move_adjusted_damage')}x{m.get('move_hits', 1)})"
        summary.append(m_info)
            
    summary.append(f"\n--- Hand ({len(hand)}) ---")
    for i, c in enumerate(hand):
        target = "!" if c.get('has_target') else ""
        card_info = f"[{i+1}]{c.get('name')}({c.get('cost')}){target}"
        if c.get("type"):
            card_info += f" | {c.get('type')}"
        if c.get("description"):
            card_info += f" : {c.get('description')}"
        summary.append(card_info)

    summary.append(f"\n--- Strategy ---")
    summary.append(_server._generate_suggestion(sections, meta))
        
    return "\n".join(summary)


@mcp.tool()
def sts_get_player(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get the latest player section (HP, energy, stance, powers, orbs).
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "player": result.get("sections", {}).get("player"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_monsters(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get the latest monsters section (HP, intents, powers, block).
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "monsters": result.get("sections", {}).get("monsters"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_hand(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get the latest hand section (cards, cost, is_playable, description).
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "hand": result.get("sections", {}).get("hand"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_draw_pile(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get draw pile.
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "draw_pile": result.get("sections", {}).get("draw_pile"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_discard_pile(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get discard pile.
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "discard_pile": result.get("sections", {}).get("discard_pile"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_exhaust_pile(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get exhaust pile.
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "exhaust_pile": result.get("sections", {}).get("exhaust_pile"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_potions(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get potions.
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "potions": result.get("sections", {}).get("potions"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_relics(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get relics.
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "relics": result.get("sections", {}).get("relics"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_selection(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get selection.
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "selection": result.get("sections", {}).get("selection"), "meta": result.get("meta")}


@mcp.tool()
def sts_get_meta(wait: float = 0.0, thinking: str = "") -> dict:
    """[PRIVATE] Get meta.
    Args:
        wait: Seconds to wait.
        thinking: Your thought process (2-3 sentences max).
    """
    result = _server.get_state(wait=wait, force_full=False, delta=False)
    meta = result.get("meta")
    if result.get("status") == "waiting":
        return {"status": "waiting", "meta": meta}
    if result.get("status") != "ok":
        return result
    return {"status": "ok", "meta": meta}


if __name__ == "__main__":
    mcp.run()
