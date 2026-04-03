import asyncio
import json
import base64
import os
import sys
import socket
import threading
import logging
from pathlib import Path
from typing import Optional, Dict, Set
from dataclasses import dataclass, field

try:
    import websockets
except ImportError:
    print("[SoVITS-Server] Error: websockets library required. Run: pip install websockets")
    sys.exit(1)

from .sovits_manager import SoVITSManager, set_sovits_logger

BROADCAST_PORT = 19876
BROADCAST_INTERVAL = 5.0
BROADCAST_MAGIC = "SOVITS_SERVER_ANNOUNCE"

logger = logging.getLogger("SoVITS-Server")

def setup_logger(log_file: Optional[Path] = None):
    """Setup logger with optional file handler. Called from main.py after setup_logging."""
    logger.setLevel(logging.INFO)
    
    # Only add file handler if not already present
    has_file_handler = any(isinstance(h, logging.FileHandler) for h in logger.handlers)
    if log_file and not has_file_handler:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter('[%(asctime)s.%(msecs)03d] [SoVITS-Server] %(message)s', '%H:%M:%S'))
        logger.addHandler(file_handler)
    
    def sovits_log_handler(message):
        logger.info(message)
    set_sovits_logger(sovits_log_handler)
    
    return logger


@dataclass
class PackWeights:
    pack_id: str
    gpt_path: Optional[str] = None
    sovits_path: Optional[str] = None
    version: str = "v2"
    valid: bool = False


@dataclass
class ClientSession:
    websocket: any
    pack_id: Optional[str] = None
    client_id: str = ""


class SoVITSServer:
    def __init__(self, project_root: Path, port: int = 9876, device: str = "cuda", 
                 broadcast_enabled: bool = True, sovits_api_port: int = 9880,
                 default_pack: str = None):
        self.project_root = project_root
        self.port = port
        self.device = device
        self.broadcast_enabled = broadcast_enabled
        self.sovits_api_port = sovits_api_port
        self.default_pack = default_pack
        self.sovits_manager: Optional[SoVITSManager] = None
        self.packs_index: Dict[str, PackWeights] = {}
        self.clients: Dict[str, ClientSession] = {}
        self._current_loaded_pack: Optional[str] = None
        self._lock = asyncio.Lock()
        self._request_queue: asyncio.Queue = asyncio.Queue()
        self._processing = False
        self._broadcast_socket: Optional[socket.socket] = None
        self._broadcast_running = False
        self._local_ip = self._get_local_ip()
        self._sovits_starting = False

    def _get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def _start_broadcast(self):
        if not self.broadcast_enabled:
            return

        try:
            self._broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self._broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._broadcast_running = True

            def broadcast_loop():
                while self._broadcast_running:
                    try:
                        available_packs = [p for p, w in self.packs_index.items() if w.valid]
                        message = json.dumps({
                            "magic": BROADCAST_MAGIC,
                            "host": self._local_ip,
                            "port": self.port,
                            "packs": available_packs
                        })
                        self._broadcast_socket.sendto(
                            message.encode("utf-8"),
                            ("<broadcast>", BROADCAST_PORT)
                        )
                    except Exception as e:
                        if self._broadcast_running:
                            logger.info(f"Broadcast error: {e}")
                    import time
                    time.sleep(BROADCAST_INTERVAL)

            self._broadcast_thread = threading.Thread(target=broadcast_loop, daemon=True)
            self._broadcast_thread.start()
            logger.info(f"Broadcast started on port {BROADCAST_PORT}, local IP: {self._local_ip}")
        except Exception as e:
            logger.info(f"Failed to start broadcast: {e}")
            self.broadcast_enabled = False

    def _stop_broadcast(self):
        self._broadcast_running = False
        if self._broadcast_socket:
            try:
                self._broadcast_socket.close()
            except:
                pass
            self._broadcast_socket = None
        logger.info("Broadcast stopped")

    def scan_packs(self) -> Dict[str, PackWeights]:
        packs_dir = self.project_root / "packs"
        if not packs_dir.exists():
            logger.info(f"Packs directory not found: {packs_dir}")
            return {}

        index = {}
        for pack_dir in packs_dir.iterdir():
            if not pack_dir.is_dir():
                continue

            pack_json = pack_dir / "pack.json"
            if not pack_json.exists():
                continue

            try:
                with open(pack_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pack_id = data.get("id") or data.get("pack_info", {}).get("id") or pack_dir.name
                sovits_model = data.get("character", {}).get("sovits_model", {})
                version = sovits_model.get("version", "v2")
            except Exception as e:
                logger.info(f"Failed to read pack.json in {pack_dir.name}: {e}")
                pack_id = pack_dir.name
                version = "v2"

            model_dir = pack_dir / "models" / "sovits"
            ckpt_files = list(model_dir.glob("*.ckpt")) if model_dir.exists() else []
            pth_files = list(model_dir.glob("*.pth")) if model_dir.exists() else []

            weights = PackWeights(pack_id=pack_id, version=version)
            if ckpt_files:
                weights.gpt_path = str(sorted(ckpt_files)[0].absolute())
            if pth_files:
                weights.sovits_path = str(sorted(pth_files)[0].absolute())
            weights.valid = bool(weights.gpt_path and weights.sovits_path)

            index[pack_id] = weights
            status = "valid" if weights.valid else "no weights"
            logger.info(f"Indexed pack: {pack_id} (version={version}, {status})")

        return index

    async def start_sovits(self, pack_id: str) -> bool:
        if self.sovits_manager:
            is_running = self.sovits_manager.is_running()
            logger.info(f"start_sovits check: sovits_manager exists, is_running={is_running}")
            if is_running:
                return True
        else:
            logger.info(f"start_sovits check: sovits_manager is None")

        if self._sovits_starting:
            logger.info(f"start_sovits check: SoVITS is already starting, waiting...")
            import time
            for _ in range(60):  
                if self.sovits_manager and self.sovits_manager.is_running():
                    logger.info(f"start_sovits check: SoVITS is now ready")
                    return True
                time.sleep(0.5)
            logger.info(f"start_sovits check: Timeout waiting for SoVITS to start")
            return False

        if pack_id not in self.packs_index:
            logger.info(f"Pack not found: {pack_id}")
            return False

        weights = self.packs_index[pack_id]
        if not weights.valid:
            logger.info(f"Pack has no valid weights: {pack_id}")
            return False

        self._sovits_starting = True
        try:
            self.sovits_manager = SoVITSManager(
                self.project_root,
                port=self.sovits_api_port,
                device=self.device,
                model_version=weights.version
            )

            def _start_sync():
                return self.sovits_manager.start(timeout=120, kill_existing=True, pack_id=pack_id)

            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, _start_sync)

            if success:
                self._current_loaded_pack = pack_id
                logger.info(f"SoVITS process started with pack: {pack_id}")
                logger.info(f"Waiting for SoVITS API to be fully ready...")
                import time
                for attempt in range(30):  
                    if self.sovits_manager.is_running(timeout=1.0):
                        logger.info(f"SoVITS API is ready after {attempt + 1} checks")
                        return True
                    time.sleep(0.5)
                logger.info(f"Warning: SoVITS API may not be fully ready yet")
            else:
                logger.info(f"Failed to start SoVITS for pack: {pack_id}")

            return success
        finally:
            self._sovits_starting = False

    async def synthesize(self, pack_id: str, text: str, emotion_config: dict, params: dict) -> Optional[bytes]:
        if not await self.start_sovits(pack_id):
            return None

        ref_wav_path = emotion_config.get("ref_wav_path")
        if not ref_wav_path:
            logger.info("Missing ref_wav_path in emotion_config")
            return None

        weights = self.packs_index.get(pack_id)
        
        payload = {
            "text": text,
            "text_lang": params.get("text_lang", "ja"),
            "ref_audio_path": ref_wav_path,
            "prompt_text": emotion_config.get("ref_text", ""),
            "prompt_lang": emotion_config.get("ref_lang", "ja"),
            "top_k": params.get("top_k", 15),
            "top_p": params.get("top_p", 1.0),
            "temperature": params.get("temperature", 1.0),
            "speed_factor": params.get("speed", 1.0),
            "media_type": "wav",
            "streaming_mode": False,
            "text_split_method": params.get("text_split_method", "cut5"),
            "fragment_interval": params.get("fragment_interval", 0.25),
            "repetition_penalty": 1.35
        }

        if weights and weights.gpt_path and weights.sovits_path:
            payload["gpt_method"] = "set_gpt_weights"
            payload["gpt_path"] = weights.gpt_path.replace("\\", "/")
            payload["sovits_method"] = "set_sovits_weights"
            payload["sovits_path"] = weights.sovits_path.replace("\\", "/")
            logger.info(f"Dynamic model switch: gpt={payload['gpt_path']}, sovits={payload['sovits_path']}")

        import aiohttp
        api_url = f"http://127.0.0.1:{self.sovits_api_port}"
        timeout = aiohttp.ClientTimeout(total=params.get("timeout", 120))

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{api_url}/tts", json=payload) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        error_text = await response.text()
                        logger.info(f"TTS API error: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.info(f"TTS request failed: {e}")
            return None

    async def handle_client(self, websocket, path=""):
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        session = ClientSession(websocket=websocket, client_id=client_id)
        self.clients[client_id] = session
        logger.info(f"Client connected: {client_id}")

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    await self.handle_message(session, data)
                except json.JSONDecodeError as e:
                    logger.info(f"Invalid JSON from {client_id}: {e}")
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            del self.clients[client_id]
            logger.info(f"Client disconnected: {client_id}")

    async def handle_message(self, session: ClientSession, data: dict):
        msg_type = data.get("type")
        logger.info(f"Received message from {session.client_id}: type={msg_type}")

        if msg_type == "handshake":
            pack_id = data.get("pack_id", "")
            session.pack_id = pack_id

            available_packs = [p for p, w in self.packs_index.items() if w.valid]
            pack_valid = pack_id in self.packs_index and self.packs_index[pack_id].valid

            response = {
                "type": "handshake_ack",
                "available_packs": available_packs,
                "requested_pack_valid": pack_valid,
                "requested_pack_id": pack_id
            }
            await session.websocket.send(json.dumps(response))
            logger.info(f"Handshake from {session.client_id}: pack={pack_id}, valid={pack_valid}")

        elif msg_type == "synthesize":
            await self._queue_synthesize(session, data)

        elif msg_type == "list_packs":
            available_packs = [
                {"pack_id": p, "valid": w.valid}
                for p, w in self.packs_index.items()
            ]
            await session.websocket.send(json.dumps({
                "type": "packs_list",
                "packs": available_packs
            }))

    async def _queue_synthesize(self, session: ClientSession, data: dict):
        pack_id = data.get("pack_id") or session.pack_id
        logger.info(f"Queueing synthesize request: pack_id={pack_id}, session_pack={session.pack_id}")
        if not pack_id:
            await session.websocket.send(json.dumps({
                "type": "synthesize_result",
                "status": "error",
                "error": "No pack_id specified"
            }))
            return

        if pack_id not in self.packs_index or not self.packs_index[pack_id].valid:
            await session.websocket.send(json.dumps({
                "type": "synthesize_result",
                "status": "error",
                "error": f"Pack '{pack_id}' not found or has no valid weights"
            }))
            return

        await self._request_queue.put((session, data, pack_id))
        logger.info(f"Queued synthesize request from {session.client_id} for pack {pack_id}")

        if not self._processing:
            asyncio.create_task(self._process_queue())

    async def _process_queue(self):
        if self._processing:
            return

        self._processing = True
        try:
            while not self._request_queue.empty():
                session, data, pack_id = await self._request_queue.get()

                request_id = data.get("request_id", "")
                text = data.get("text", "")
                emotion_config = data.get("emotion_config", {})
                params = data.get("params", {})

                logger.info(f"Processing synthesize: pack={pack_id}, request_id={request_id}, text_len={len(text)}")

                audio_data = await self.synthesize(pack_id, text, emotion_config, params)

                if audio_data:
                    audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                    await session.websocket.send(json.dumps({
                        "type": "synthesize_result",
                        "request_id": request_id,
                        "status": "success",
                        "audio_data": audio_b64,
                        "format": "wav"
                    }))
                    logger.info(f"Sent audio to {session.client_id}: {len(audio_data)} bytes")
                else:
                    await session.websocket.send(json.dumps({
                        "type": "synthesize_result",
                        "request_id": request_id,
                        "status": "error",
                        "error": "Synthesis failed"
                    }))
        finally:
            self._processing = False

    async def run(self):
        self.packs_index = self.scan_packs()
        logger.info(f"Scanned {len(self.packs_index)} packs, {sum(1 for w in self.packs_index.values() if w.valid)} valid")

        temp_dir = self.project_root / "TEMP"
        if temp_dir.exists():
            import shutil
            for f in temp_dir.iterdir():
                try:
                    if f.is_file():
                        f.unlink()
                    elif f.is_dir():
                        shutil.rmtree(f)
                except Exception as e:
                    logger.info(f"Failed to clean {f}: {e}")
            logger.info("Cleaned TEMP directory")

        if self.default_pack:
            if self.default_pack in self.packs_index and self.packs_index[self.default_pack].valid:
                logger.info(f"Preloading default pack: {self.default_pack}")
                success = await self.start_sovits(self.default_pack)
                if success:
                    logger.info(f"Default pack {self.default_pack} loaded successfully")
                else:
                    logger.info(f"Failed to preload default pack: {self.default_pack}")
            else:
                logger.info(f"Default pack {self.default_pack} not found or invalid, skipping preload")
        else:
            valid_packs = [p for p, w in self.packs_index.items() if w.valid]
            if valid_packs:
                auto_pack = valid_packs[0]
                logger.info(f"Auto-preloading first valid pack: {auto_pack}")
                success = await self.start_sovits(auto_pack)
                if success:
                    logger.info(f"Auto-loaded pack: {auto_pack}")
                else:
                    logger.info(f"Failed to auto-load pack: {auto_pack}")

        self._start_broadcast()

        logger.info(f"Starting WebSocket server on port {self.port}")
        try:
            async with websockets.serve(self.handle_client, "0.0.0.0", self.port):
                logger.info(f"Server started. Local IP: {self._local_ip}:{self.port}")
                logger.info("Press Ctrl+C to stop.")
                await asyncio.Future()
        finally:
            self._stop_broadcast()
            if self.sovits_manager:
                self.sovits_manager.stop()


def run_server(project_root: str = None, port: int = 9876, device: str = "cuda",
               broadcast_enabled: bool = True, sovits_api_port: int = 9880,
               log_file: Optional[Path] = None, default_pack: str = None):
    setup_logger(log_file)
    
    if project_root is None:
        project_root = Path(__file__).parent.parent.parent
    else:
        project_root = Path(project_root)

    server = SoVITSServer(
        project_root, 
        port=port, 
        device=device,
        broadcast_enabled=broadcast_enabled,
        sovits_api_port=sovits_api_port,
        default_pack=default_pack
    )
    asyncio.run(server.run())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SoVITS WebSocket Server")
    parser.add_argument("--project-root", type=str, default=None, help="Project root directory")
    parser.add_argument("--port", type=int, default=9876, help="WebSocket server port")
    parser.add_argument("--device", type=str, default="cuda", help="Device to use (cuda/cpu)")
    parser.add_argument("--no-broadcast", action="store_true", help="Disable UDP broadcast")
    parser.add_argument("--sovits-api-port", type=int, default=9880, help="SoVITS API port")
    args = parser.parse_args()

    run_server(
        args.project_root, 
        args.port, 
        args.device,
        broadcast_enabled=not args.no_broadcast,
        sovits_api_port=args.sovits_api_port
    )
