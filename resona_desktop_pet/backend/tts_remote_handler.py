import asyncio
import json
import base64
import os
import sys
import socket
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

try:
    import websockets
except ImportError:
    websockets = None

from ..config import ConfigManager

BROADCAST_PORT = 19876
BROADCAST_MAGIC = "SOVITS_SERVER_ANNOUNCE"
DISCOVERY_TIMEOUT = 10.0


def log(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [TTS-Remote] {message}")


@dataclass
class TTSResult:
    audio_path: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0


class RemoteTTSHandler:
    def __init__(self, config: ConfigManager, temp_dir: Path):
        self.config = config
        self.temp_dir = temp_dir
        self.temp_dir.mkdir(exist_ok=True)
        self.server_host = config.sovits_server_host
        self.server_port = config.sovits_server_port
        self.auto_discover = config.sovits_server_auto_discover
        self.ws_url = f"ws://{self.server_host}:{self.server_port}"
        self._ws: Optional[any] = None
        self._connected = False
        self._pack_valid = False
        self._available_packs: List[str] = []
        self._pending_results: Dict[str, asyncio.Future] = {}
        self._receive_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._discovered_server: Optional[Dict] = None
        self._discovery_socket: Optional[socket.socket] = None
        self._discovery_running = False

    def _start_discovery_listener(self):
        try:
            self._discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._discovery_socket.bind(("0.0.0.0", BROADCAST_PORT))
            self._discovery_socket.settimeout(1.0)
            self._discovery_running = True

            def listen_loop():
                while self._discovery_running:
                    try:
                        data, addr = self._discovery_socket.recvfrom(4096)
                        message = json.loads(data.decode("utf-8"))
                        if message.get("magic") == BROADCAST_MAGIC:
                            self._discovered_server = {
                                "host": message.get("host"),
                                "port": message.get("port"),
                                "packs": message.get("packs", [])
                            }
                            log(f"Discovered server: {self._discovered_server['host']}:{self._discovered_server['port']}")
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self._discovery_running:
                            pass
                try:
                    self._discovery_socket.close()
                except:
                    pass

            self._discovery_thread = threading.Thread(target=listen_loop, daemon=True)
            self._discovery_thread.start()
            log(f"Discovery listener started on port {BROADCAST_PORT}")
            return True
        except Exception as e:
            log(f"Failed to start discovery listener: {e}")
            return False

    def _stop_discovery_listener(self):
        self._discovery_running = False
        if self._discovery_socket:
            try:
                self._discovery_socket.close()
            except:
                pass

    async def discover_server(self, timeout: float = DISCOVERY_TIMEOUT) -> Optional[Dict]:
        if not self._discovery_running:
            if not self._start_discovery_listener():
                return None

        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            if self._discovered_server:
                return self._discovered_server
            await asyncio.sleep(0.5)

        return None

    async def connect_with_discovery(self, pack_id: str, prefer_discovery: bool = True) -> bool:
        if prefer_discovery and self.auto_discover:
            log("Attempting to discover server via UDP broadcast...")
            discovered = await self.discover_server(timeout=DISCOVERY_TIMEOUT)
            if discovered:
                self.server_host = discovered["host"]
                self.server_port = discovered["port"]
                self.ws_url = f"ws://{self.server_host}:{self.server_port}"
                log(f"Using discovered server: {self.server_host}:{self.server_port}")
            else:
                log("Discovery timeout, using configured server address")

        return await self.connect(pack_id)

    async def connect(self, pack_id: str) -> bool:
        if websockets is None:
            log("Error: websockets library not installed")
            return False

        try:
            self._ws = await websockets.connect(self.ws_url, ping_interval=30, ping_timeout=10)
            log(f"Connected to server: {self.ws_url}")

            await self._ws.send(json.dumps({
                "type": "handshake",
                "pack_id": pack_id
            }))

            log("Waiting for handshake_ack...")
            response = await asyncio.wait_for(self._ws.recv(), timeout=10)
            log(f"Received response: {response[:200]}...")
            data = json.loads(response)

            if data.get("type") == "handshake_ack":
                self._connected = True
                self._available_packs = data.get("available_packs", [])
                self._pack_valid = data.get("requested_pack_valid", False)
                log(f"Handshake complete. Pack valid: {self._pack_valid}, Available: {self._available_packs}")
                
                self._stop_discovery_listener()

                self._receive_task = asyncio.create_task(self._receive_loop())
                return True
            else:
                log(f"Unexpected handshake response: {data}")
                return False

        except asyncio.TimeoutError:
            log("Connection failed: handshake timeout")
            self._connected = False
            return False
        except Exception as e:
            log(f"Connection failed: {e}")
            import traceback
            log(f"Connection error traceback: {traceback.format_exc()}")
            self._connected = False
            return False

    async def _receive_loop(self):
        try:
            async for message in self._ws:
                try:
                    data = json.loads(message)
                    msg_type = data.get("type")

                    if msg_type == "synthesize_result":
                        request_id = data.get("request_id")
                        if request_id and request_id in self._pending_results:
                            future = self._pending_results.pop(request_id)
                            if not future.done():
                                future.set_result(data)
                except Exception as e:
                    log(f"Error processing message: {e}")
        except asyncio.CancelledError:
            log("Receive loop cancelled")
            raise
        except websockets.exceptions.ConnectionClosed:
            log("Connection closed by server")
            self._connected = False
        except Exception as e:
            log(f"Receive loop error: {e}")
            self._connected = False

    async def ensure_connected(self, pack_id: str) -> bool:
        log(f"[ensure_connected] _connected={self._connected}, _ws={self._ws is not None}")
        
        if self._connected and self._ws:
            try:
                await asyncio.wait_for(self._ws.ping(), timeout=2)
                log(f"[ensure_connected] Connection alive, returning True")
                return True
            except Exception as e:
                log(f"[ensure_connected] Connection test failed: {e}")
                self._connected = False
        
        log(f"[ensure_connected] Need to connect...")
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except:
                pass
            self._connected = False
            if self._receive_task:
                self._receive_task.cancel()
                try:
                    await self._receive_task
                except asyncio.CancelledError:
                    pass
        
        if self.auto_discover:
            result = await self.connect_with_discovery(pack_id)
            log(f"[ensure_connected] connect_with_discovery returned: {result}")
            return result
        result = await self.connect(pack_id)
        log(f"[ensure_connected] connect returned: {result}")
        return result

    async def synthesize(
        self,
        text: str,
        emotion_config: dict,
        params: dict,
        pack_id: str
    ) -> TTSResult:
        log(f"Synthesize called: pack_id={pack_id}, text_len={len(text)}")
        if not await self.ensure_connected(pack_id):
            log(f"Failed to ensure connection for pack {pack_id}")
            return TTSResult(error="Not connected to server")

        if not self._pack_valid:
            log(f"Pack {pack_id} not valid on server")
            return TTSResult(error=f"Pack '{pack_id}' not valid on server")

        request_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        future: asyncio.Future = asyncio.Future()
        self._pending_results[request_id] = future

        payload = {
            "type": "synthesize",
            "request_id": request_id,
            "pack_id": pack_id,
            "text": text,
            "emotion_config": emotion_config,
            "params": params
        }

        try:
            await self._ws.send(json.dumps(payload))
            log(f"Sent synthesize request: {request_id}")

            result = await asyncio.wait_for(future, timeout=params.get("timeout", 120))

            if result.get("status") == "success":
                audio_b64 = result.get("audio_data")
                if audio_b64:
                    audio_data = base64.b64decode(audio_b64)
                    output_path = self.temp_dir / f"remote_{request_id}.wav"
                    with open(output_path, "wb") as f:
                        f.write(audio_data)

                    duration = 0.0
                    try:
                        import soundfile as sf
                        info = sf.info(str(output_path))
                        data, sr = sf.read(str(output_path), dtype="float32")
                        duration = len(data) / sr
                        log(f"Received audio: {len(audio_data)} bytes, duration: {duration:.2f}s, sr={sr}Hz, subtype={info.subtype}")
                        
                        TARGET_SR = 44100
                        if info.subtype != "PCM_16" or sr != TARGET_SR:
                            pcm_path = str(output_path).replace(".wav", "_pcm16.wav")
                            ffmpeg_exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
                            ffmpeg_local = self.temp_dir.parent / "ffmpeg" / "bin" / ffmpeg_exe
                            ffmpeg_cmd = str(ffmpeg_local) if ffmpeg_local.exists() else "ffmpeg"
                            result_ffmpeg = subprocess.run([
                                ffmpeg_cmd, "-y", "-i", str(output_path),
                                "-ar", str(TARGET_SR),
                                "-ac", "1",
                                "-sample_fmt", "s16",
                                pcm_path
                            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                            log(f"FFmpeg resample exit={result_ffmpeg.returncode}, {sr}Hz -> {TARGET_SR}Hz PCM_16 (cmd={ffmpeg_cmd})")
                            if result_ffmpeg.returncode == 0:
                                output_path = Path(pcm_path)
                            else:
                                log(f"FFmpeg failed: {result_ffmpeg.stderr.decode('utf-8', errors='ignore')[-200:]}")
                    except Exception as e:
                        log(f"Failed to process audio: {e}")

                    return TTSResult(audio_path=str(output_path), duration=duration)
                else:
                    return TTSResult(error="No audio data in response")
            else:
                error = result.get("error", "Unknown error")
                log(f"Synthesis failed: {error}")
                return TTSResult(error=error)

        except asyncio.TimeoutError:
            self._pending_results.pop(request_id, None)
            return TTSResult(error="Request timeout")
        except Exception as e:
            self._pending_results.pop(request_id, None)
            log(f"Synthesize error: {e}")
            return TTSResult(error=str(e))

    async def get_available_packs(self) -> List[str]:
        if not await self.ensure_connected(""):
            return []

        try:
            await self._ws.send(json.dumps({"type": "list_packs"}))
            response = await asyncio.wait_for(self._ws.recv(), timeout=5)
            data = json.loads(response)
            if data.get("type") == "packs_list":
                return [p["pack_id"] for p in data.get("packs", []) if p.get("valid")]
        except Exception as e:
            log(f"Failed to get packs list: {e}")

        return self._available_packs

    async def close(self):
        self._stop_discovery_listener()

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except:
                pass

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._connected = False
        log("Connection closed")

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None and not self._ws.closed

    @property
    def is_pack_valid(self) -> bool:
        return self._pack_valid
