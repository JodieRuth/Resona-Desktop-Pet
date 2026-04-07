from fastapi import FastAPI, WebSocket, Request, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import threading
import json
import os
import shutil
import time
import websockets
import logging
from pathlib import Path
from typing import Optional
from .session_manager import SessionManager
from resona_desktop_pet.utils.audio_utils import convert_to_wav

logger = logging.getLogger("Web")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

session_manager = SessionManager()
controller_ref = None
main_loop = None
BEACON_PORT = 50123

def resolve_static_path(controller, static_dir: str) -> Path:
    project_root = Path(controller.project_root)
    builtin_static = Path(__file__).resolve().parent / "static"
    builtin_static_alt = project_root / "resona_desktop_pet" / "web_server" / "static"
    default_static = project_root / static_dir
    if static_dir.strip().lower() == "html":
        candidate_paths = [
            builtin_static,
            builtin_static_alt,
            default_static
        ]
    else:
        candidate_paths = [
            default_static,
            builtin_static,
            builtin_static_alt
        ]
    for candidate in candidate_paths:
        if (candidate / "index.html").exists():
            return candidate
    return candidate_paths[0]

import random

def resolve_idle_image(controller, pack_id: str, outfit_id: str) -> Optional[str]:
    if not controller: return None
    
    pm = controller.config.pack_manager
    image_url = None
    
    try:
        pack_data = pm._get_pack_data(pack_id)
        outfits = pack_data.get("character", {}).get("outfits", [])
        
        target_outfit = next((o for o in outfits if o.get("id") == outfit_id), None)
        if not target_outfit:
             target_outfit = next((o for o in outfits if o.get("is_default")), None)
        
        if target_outfit:
            outfit_path = target_outfit.get("path")
            full_outfit_path = pm.packs_dir / pack_id / outfit_path
            sum_path = full_outfit_path / "sum.json"
            
            if sum_path.exists():
                with open(sum_path, "r", encoding="utf-8") as f:
                    sum_data = json.load(f)
                    
                    candidate_images = []
                    
                    for key in ["<E:smile>", "<E:normal>", "<E:default>"]:
                        if key in sum_data and sum_data[key]:
                            images = sum_data[key]
                            if not isinstance(images, list): images = [images]
                            
                            valid_images = []
                            for img_name in images:
                                for ext in [".png", ".jpg", ".jpeg"]:
                                    if (full_outfit_path / (img_name + ext)).exists():
                                        valid_images.append((img_name, ext))
                                        break
                            
                            if valid_images:
                                candidate_images = valid_images
                                break 
                    
                    if candidate_images:
                        def get_digit_sum(s):
                            return sum(int(c) for c in s if c.isdigit())
                        best_img = min(candidate_images, key=lambda x: (get_digit_sum(x[0]), len(x[0]), x[0]))
                        image_url = f"/packs/{pack_id}/{outfit_path}/{best_img[0]}{best_img[1]}"
    except Exception as e:
        logger.error(f"Error resolving idle image: {e}")
        
    return image_url

def get_initial_pack_state(controller, pack_id: Optional[str] = None, outfit_id: Optional[str] = None):
    if not controller: return {}
    
    pm = controller.config.pack_manager
    active_pack = pack_id if pack_id else pm.active_pack_id
    default_outfit = outfit_id if outfit_id else controller.config.default_outfit
    
    image_url = resolve_idle_image(controller, active_pack, default_outfit)

    pack_data = pm._get_pack_data(active_pack) or {}
    pack_info = pack_data.get("pack_info", {})
    character_name = pack_data.get("character", {}).get("name") or "Unknown"
    
    all_packs = []
    try:
        for pack_dir in pm.packs_dir.iterdir():
            if pack_dir.is_dir() and (pack_dir / "pack.json").exists():
                try:
                    with open(pack_dir / "pack.json", "r", encoding="utf-8") as f:
                        pdata = json.load(f)
                        pinfo = pdata.get("pack_info", {})
                        all_packs.append({
                            "id": pack_dir.name,
                            "name": pinfo.get("name", pack_dir.name),
                            "description": pinfo.get("description", "")
                        })
                except: pass
    except: pass

    return {
        "active_pack": active_pack,
        "default_outfit": default_outfit,
        "character_name": character_name,
        "initial_image_url": image_url,
        "pack_metadata": {
            "name": pack_info.get("name", "Unknown"),
            "description": pack_info.get("description", "No description"),
            "author": pack_info.get("author", "Unknown"),
            "version": pack_info.get("version", "0.0.0")
        },
        "available_packs": all_packs
    }

def get_listening_state(controller):
    if not controller: return {}
    
    listening_texts = getattr(controller.config, "listening_texts", [])
    listen_text_entry = random.choice(listening_texts) if listening_texts else "Listening..."
    if isinstance(listen_text_entry, dict):
        listen_text = listen_text_entry.get("text", "Listening...")
    else:
        listen_text = str(listen_text_entry)
    
    
    return {
        "text": listen_text
    }

def set_controller(controller, loop):
    global controller_ref, main_loop
    controller_ref = controller
    main_loop = loop

def start_udp_beacon(http_port: int):
    def run():
        payload = json.dumps({"type": "resona_server", "port": http_port}).encode("utf-8")
        while True:
            try:
                import socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s.sendto(payload, ("255.255.255.255", BEACON_PORT))
                s.close()
            except Exception:
                pass
            time.sleep(2.0)
    threading.Thread(target=run, daemon=True).start()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = str(websocket.client.host)
    
    try:
        init_data = await websocket.receive_json()
        pack_id = init_data.get("pack_id", "default")
        sess_id = init_data.get("session_id")
        client_type = init_data.get("client_type", "web_app")

        if (pack_id == "default" or not pack_id) and controller_ref:
            pack_id = controller_ref.config.pack_manager.active_pack_id

        session = None
        if sess_id:
            session = session_manager.get_session(sess_id)
        
        if not session:
            session = session_manager.create_session(pack_id, 20)
        
        session.websocket = websocket
        session.pack_id = pack_id
        session.client_type = client_type
        session.touch()
        
        pack_state = get_initial_pack_state(controller_ref, pack_id=session.pack_id, outfit_id=session.outfit)
        
        await websocket.send_json({
            "type": "handshake_ack",
            "session_id": session.session_id,
            "config": {
                "stt_max_duration": controller_ref.config.stt_max_duration,
                "stt_silence_threshold": controller_ref.config.stt_silence_threshold,
                "sovits_enabled": controller_ref.config.sovits_enabled,
                "text_read_speed": controller_ref.config.text_read_speed,
                "base_display_time": controller_ref.config.base_display_time,
                **pack_state
            }
        })

        while True:
            msg = await websocket.receive_json()
            session.touch()
            msg_type = msg.get("type")

            if msg_type == "text_input":
                text = msg.get("text", "")
                if text and controller_ref and main_loop:
                    asyncio.run_coroutine_threadsafe(
                        controller_ref.handle_web_query(text, session),
                        main_loop
                    )

            elif msg_type == "start_recording":
                if controller_ref and main_loop:
                    asyncio.run_coroutine_threadsafe(
                        controller_ref.handle_web_start_recording(session),
                        main_loop
                    )
            
            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "get_outfits":
                if controller_ref:
                    try:
                        pm = controller_ref.config.pack_manager
                        target_pack = session.pack_id
                        pack_data = pm._get_pack_data(target_pack)
                        outfits = pack_data.get("character", {}).get("outfits", [])
                        
                        outfit_list = []
                        for o in outfits:
                            outfit_list.append({
                                "id": o.get("id"),
                                "name": o.get("name", o.get("id")),
                                "is_default": o.get("is_default", False),
                                "path": o.get("path")
                            })
                        
                        await websocket.send_json({
                            "type": "outfits_list",
                            "pack_id": target_pack,
                            "outfits": outfit_list,
                            "current_outfit": session.outfit or controller_ref.config.default_outfit
                        })
                    except Exception as e:
                         await websocket.send_json({"type": "error", "message": f"Failed to get outfits: {e}"})

            elif msg_type == "set_outfit":
                outfit_id = msg.get("outfit_id")
                if outfit_id:
                    session.outfit = outfit_id
                    if controller_ref:
                        image_url = resolve_idle_image(controller_ref, session.pack_id, outfit_id)
                        
                        await websocket.send_json({
                            "type": "outfit_changed",
                            "outfit_id": outfit_id,
                            "image_url": image_url
                        })


            elif msg_type == "settings_update":
                settings = msg.get("settings", {})
                if controller_ref and main_loop and settings:
                    if "active_pack" in settings:
                         pack_id = settings["active_pack"]
                         logger.info(f"Switching pack to: {pack_id}")
                         asyncio.run_coroutine_threadsafe(
                             controller_ref.handle_web_pack_switch(pack_id, session),
                             main_loop
                         )
                    else:
                        asyncio.run_coroutine_threadsafe(
                            controller_ref.handle_web_settings_update(settings, session),
                            main_loop
                        )

    except Exception as e:
        pass
    finally:
        if session:
            session.websocket = None

@app.post("/upload_audio")
async def upload_audio(
    file: UploadFile = File(...), 
    session_id: str = Form(...)
):
    if not controller_ref:
        return JSONResponse({"error": "Backend not ready"}, status_code=503)
    logger.debug(f"[Web] upload_audio received session_id={session_id} filename={getattr(file, 'filename', None)} content_type={getattr(file, 'content_type', None)}")

    session = session_manager.get_session(session_id)
    if not session:
        logger.warning(f"[Web] upload_audio invalid session_id={session_id}")
        return JSONResponse({"error": "Invalid session"}, status_code=404)

    upload_dir = Path(controller_ref.config.html_upload_dir)
    if not upload_dir.is_absolute():
        upload_dir = Path(controller_ref.project_root) / upload_dir
        
    upload_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"[Web] upload_audio upload_dir={upload_dir}")
    
    filename = f"web_audio_{session_id}_{int(asyncio.get_event_loop().time())}.wav"
    file_path = upload_dir / filename
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        try:
            size = file_path.stat().st_size
        except Exception:
            size = None
        logger.debug(f"[Web] upload_audio saved file_path={file_path} size={size}")

        converted_path = file_path.with_name(f"{file_path.stem}_converted.wav")
        ok = convert_to_wav(file_path, converted_path)
        logger.debug(f"[Web] upload_audio convert_to_wav ok={ok} src={file_path} dst={converted_path}")
        if ok:
            file_path.unlink()
            file_path = converted_path
        else:
            try:
                file_path.unlink()
            except Exception:
                pass
            return JSONResponse({"error": "Audio conversion failed. Ensure ffmpeg is available in PATH."}, status_code=500)

        logger.debug(f"[Web] upload_audio dispatch handle_web_audio path={file_path}")
        asyncio.run_coroutine_threadsafe(
            controller_ref.handle_web_audio(str(file_path), session),
            main_loop
        )
        return {"status": "processing", "path": str(file_path)}
    except Exception as e:
        logger.error(f"[Web] upload_audio exception: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/")
async def get_index():
    if controller_ref:
        static_path = resolve_static_path(controller_ref, controller_ref.config.html_static_dir)
        index_path = static_path / "index.html"
        has_marker = False
        size = None
        mtime = None
        try:
            size = index_path.stat().st_size
            mtime = index_path.stat().st_mtime
            with open(index_path, "r", encoding="utf-8") as f:
                has_marker = "__RES_WEB_VERSION" in f.read()
        except Exception:
            pass
        logger.debug(f"[Web] index.html marker={has_marker} size={size} mtime={mtime}")
        return FileResponse(index_path, headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        })
    return JSONResponse({"error": "Server not ready"}, status_code=503)

@app.get("/__static_info")
async def get_static_info():
    if controller_ref:
        static_path = resolve_static_path(controller_ref, controller_ref.config.html_static_dir)
        index_path = static_path / "index.html"
        has_marker = False
        size = None
        mtime = None
        try:
            size = index_path.stat().st_size
            mtime = index_path.stat().st_mtime
            with open(index_path, "r", encoding="utf-8") as f:
                has_marker = "__RES_WEB_VERSION" in f.read()
        except Exception:
            pass
        return JSONResponse({
            "static_path": str(static_path),
            "index_path": str(index_path),
            "index_size": size,
            "index_mtime": mtime,
            "index_has_marker": has_marker
        })
    return JSONResponse({"error": "Server not ready"}, status_code=503)

@app.post("/__client_log")
async def client_log(request: Request):
    try:
        data = await request.json()
    except Exception:
        data = None
    logger.debug(f"[Web] ClientLog: {data}")
    return {"status": "ok"}

class WebServerThread(threading.Thread):
    def __init__(self, controller, loop, host, port, static_dir):
        super().__init__()
        self.controller = controller
        self.loop = loop
        self.host = host
        self.port = port
        self.static_dir = static_dir
        self.daemon = True

    def run(self):
        set_controller(self.controller, self.loop)
        
        static_path = resolve_static_path(self.controller, self.static_dir)
        logger.debug(f"[Web] Static path: {static_path}")
        start_udp_beacon(self.port)
        
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            logger.info(f"\n[Web] Server is running! Access it from your phone at: http://{local_ip}:{self.port}\n")
        except Exception:
            logger.info(f"\n[Web] Server is running at: http://localhost:{self.port}\n")

        packs_path = Path(self.controller.project_root) / "packs"
        app.mount("/packs", StaticFiles(directory=str(packs_path)), name="packs")
        
        temp_path = Path(self.controller.project_root) / "TEMP"
        temp_path.mkdir(parents=True, exist_ok=True)
        app.mount("/temp", StaticFiles(directory=str(temp_path)), name="temp")

        app.mount("/static", StaticFiles(directory=str(static_path), html=True), name="static")

        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="error", log_config=None)
        server = uvicorn.Server(config)
        server.run()

class ExternalWSServerThread(threading.Thread):
    def __init__(self, controller, loop, host, port):
        super().__init__()
        self.controller = controller
        self.loop = loop
        self.host = host
        self.port = port
        self.daemon = True
        self._sockets = {} 
        self._pending = {}

    def _format_ws_log(self, message: str) -> str:
        if not isinstance(message, str):
            message = str(message)
        if len(message) <= 800:
            return message
        head = message[:320]
        tail = message[-200:]
        return f"{head} ... ({len(message)} chars) ... {tail}"

    async def _handle_connection(self, websocket):
        role = None
        try:
            async for message in websocket:
                try:
                    logger.debug(f"[ExternalWS] Message received: {self._format_ws_log(message)}")
                    data = json.loads(message)
                    if not isinstance(data, dict):
                        if self.controller.config.external_ws_return_status:
                            await websocket.send(json.dumps({"status": "error", "message": "Message must be a JSON object"}))
                        continue
                    
                    msg_type = data.get("type")
                    if msg_type == "mcp_register":
                        role = data.get("role")
                        prefixes = data.get("prefixes", [])
                        if role:
                            self._sockets[role] = {
                                "socket": websocket,
                                "prefixes": prefixes
                            }
                            logger.info(f"[ExternalWS] Role registered: {role} (Prefixes: {prefixes})")
                        if self.controller.config.external_ws_return_status:
                            await websocket.send(json.dumps({"status": "ok", "message": f"Registered as {role}"}))
                        continue
                    if msg_type == "mcp_response":
                        req_id = data.get("id")
                        future = self._pending.pop(req_id, None)
                        if future and not future.done():
                            future.set_result(data)
                        continue
                    if msg_type == "mcp_request":
                        req_id = data.get("id") or f"mcp-{int(time.time() * 1000)}"
                        
                        target = data.get("target")
                        if not target:
                            method = data.get("method", "")
                            params = data.get("params", {})
                            action = data.get("action", "")
                            tool_name = params.get("name", "") or action or method
                            
                            for r, info in self._sockets.items():
                                if any(tool_name.startswith(p + "_") or p in tool_name for p in info.get("prefixes", [])):
                                    target = r
                                    break
                            
                            if not target:
                                if "minecraft" in tool_name: target = "minecraft_mod"
                                elif "sts" in tool_name: target = "sts_mod"

                        target_info = self._sockets.get(target)
                        target_socket = target_info["socket"] if target_info else None
                        
                        if not target_socket:
                            mod_roles = [r for r in self._sockets.keys() if r.endswith("_mod")]
                            if mod_roles:
                                target = mod_roles[0]
                                target_socket = self._sockets[target]["socket"]

                        if not target_socket:
                            logger.warning(f"[ExternalWS] MCP request failed: target '{target}' not connected")
                            await websocket.send(json.dumps({"type": "mcp_response", "id": req_id, "status": "error", "message": f"Target mod '{target}' not connected"}))
                            continue
                            
                        data["id"] = req_id
                        loop = asyncio.get_running_loop()
                        future = loop.create_future()
                        self._pending[req_id] = future
                        try:
                            await target_socket.send(json.dumps(data))
                        except Exception:
                            self._pending.pop(req_id, None)
                            if target in self._sockets:
                                del self._sockets[target]
                            logger.warning(f"[ExternalWS] MCP request failed: send to '{target}' failed")
                            await websocket.send(json.dumps({"type": "mcp_response", "id": req_id, "status": "error", "message": f"Send to '{target}' failed"}))
                            continue
                        try:
                            resp = await asyncio.wait_for(future, timeout=2.5)
                        except asyncio.TimeoutError:
                            resp = {"type": "mcp_response", "id": req_id, "status": "error", "message": "timeout"}
                        self._pending.pop(req_id, None)
                        await websocket.send(json.dumps(resp))
                        continue

                    if msg_type == "log":
                        level = data.get("level", "info")
                        message_text = data.get("message", "")
                        if message_text:
                            logger.debug(f"[ExternalWS:{level}] {message_text}")
                        if self.controller.config.external_ws_return_status:
                            await websocket.send(json.dumps({"status": "ok", "message": "log received"}))
                        continue

                    if msg_type == "config_request":
                        cfg = self.controller.config.get_llm_config() if self.controller else {}
                        await websocket.send(json.dumps({
                            "type": "config_response",
                            "id": data.get("id"),
                            "max_tokens": cfg.get("max_tokens", 512),
                            "temperature": cfg.get("temperature", 0.7),
                            "top_p": cfg.get("top_p", 1.0)
                        }))
                        continue

                    if msg_type == "llm_request":
                        req_id = data.get("id") or f"llm-{int(time.time() * 1000)}"
                        try:
                            messages = data.get("messages") or []
                            temperature = data.get("temperature", 0.7)
                            top_p = data.get("top_p", 1.0)
                            max_tokens = data.get("max_tokens", 500)
                            llm_pack_id = session.pack_id if session.pack_id else controller_ref.config.pack_manager.active_pack_id
                            result = await self.controller.llm_backend.query_raw(
                                messages=messages,
                                temperature=temperature,
                                top_p=top_p,
                                max_tokens=max_tokens,
                                pack_id=llm_pack_id,
                                enable_memory=True
                            )
                            await websocket.send(json.dumps({
                                "type": "llm_response",
                                "id": req_id,
                                "status": "ok",
                                "raw_text": result.get("raw_text", ""),
                                "reasoning": result.get("reasoning", "")
                            }))
                        except Exception as e:
                            logger.error(f"[ExternalWS] llm_request failed: {e}")
                            await websocket.send(json.dumps({"type": "llm_response", "id": req_id, "status": "error", "message": str(e)}))
                        continue

                    if msg_type == "task_finished":
                        report = data.get("report")
                        mode = data.get("mode")
                        if report:
                            logger.debug(f"[ExternalWS] Subagent result ({mode}): {report}")
                        if self.controller.llm_backend:
                            self.controller.llm_backend.set_subagent_result(mode, report)
                        if self.controller.config.external_ws_return_status:
                            await websocket.send(json.dumps({"status": "ok", "message": "report stored"}))
                        continue

                    question = data.get("question")
                    if not question or not isinstance(question, str) or not question.strip():
                        if self.controller.config.external_ws_return_status:
                            await websocket.send(json.dumps({"status": "error", "message": "JSON must contain a non-empty 'question' string field"}))
                        continue

                    if self.controller.config.external_ws_ignore_if_busy and self.controller.is_busy:
                        logger.debug(f"[ExternalWS] Program is busy, ignoring question: {question}")
                        if self.controller.config.external_ws_return_status:
                             await websocket.send(json.dumps({"status": "ignored", "message": "Program is busy"}))
                        continue
                        
                    logger.info(f"[ExternalWS] Question received: {question}")
                    self.controller.external_query_signal.emit(question)
                    
                    if self.controller.config.external_ws_return_status:
                        await websocket.send(json.dumps({"status": "ok", "message": "Question submitted"}))

                except json.JSONDecodeError:
                    if self.controller.config.external_ws_return_status:
                        await websocket.send(json.dumps({"status": "error", "message": "Invalid JSON format"}))
                    continue
        except Exception as e:
            logger.warning(f"[ExternalWS] Connection error: {e}")
        finally:
            if role and self._sockets.get(role, {}).get("socket") == websocket:
                del self._sockets[role]
                logger.info(f"[ExternalWS] Role disconnected: {role}")

    async def _start_server(self):
        logger.info(f"[ExternalWS] Listening on ws://{self.host}:{self.port}")
        async with websockets.serve(self._handle_connection, self.host, self.port):
            await asyncio.Future() 

    def run(self):
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            new_loop.run_until_complete(self._start_server())
        except Exception as e:
            logger.error(f"[ExternalWS] Server failed: {e}")
