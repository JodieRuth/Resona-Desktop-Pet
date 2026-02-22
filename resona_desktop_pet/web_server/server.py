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
from pathlib import Path
from typing import Optional
from .session_manager import SessionManager
from resona_desktop_pet.utils.audio_utils import convert_to_wav

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
        print(f"Error resolving idle image: {e}")
        
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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = str(websocket.client.host)
    
    try:
        init_data = await websocket.receive_json()
        pack_id = init_data.get("pack_id", "default")
        sess_id = init_data.get("session_id")

        if (pack_id == "default" or not pack_id) and controller_ref:
            pack_id = controller_ref.config.pack_manager.active_pack_id

        session = None
        if sess_id:
            session = session_manager.get_session(sess_id)
        
        if not session:
            session = session_manager.create_session(pack_id, 20)
        
        session.websocket = websocket
        session.pack_id = pack_id
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
                         print(f"Switching pack to: {pack_id}")
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
    print(f"[Web] upload_audio received session_id={session_id} filename={getattr(file, 'filename', None)} content_type={getattr(file, 'content_type', None)}")

    session = session_manager.get_session(session_id)
    if not session:
        print(f"[Web] upload_audio invalid session_id={session_id}")
        return JSONResponse({"error": "Invalid session"}, status_code=404)

    upload_dir = Path(controller_ref.config.html_upload_dir)
    if not upload_dir.is_absolute():
        upload_dir = Path(controller_ref.project_root) / upload_dir
        
    upload_dir.mkdir(parents=True, exist_ok=True)
    print(f"[Web] upload_audio upload_dir={upload_dir}")
    
    filename = f"web_audio_{session_id}_{int(asyncio.get_event_loop().time())}.wav"
    file_path = upload_dir / filename
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        try:
            size = file_path.stat().st_size
        except Exception:
            size = None
        print(f"[Web] upload_audio saved file_path={file_path} size={size}")

        converted_path = file_path.with_name(f"{file_path.stem}_converted.wav")
        ok = convert_to_wav(file_path, converted_path)
        print(f"[Web] upload_audio convert_to_wav ok={ok} src={file_path} dst={converted_path}")
        if ok:
            file_path.unlink()
            file_path = converted_path
        else:
            try:
                file_path.unlink()
            except Exception:
                pass
            return JSONResponse({"error": "Audio conversion failed. Ensure ffmpeg is available in PATH."}, status_code=500)

        print(f"[Web] upload_audio dispatch handle_web_audio path={file_path}")
        asyncio.run_coroutine_threadsafe(
            controller_ref.handle_web_audio(str(file_path), session),
            main_loop
        )
        return {"status": "processing", "path": str(file_path)}
    except Exception as e:
        print(f"[Web] upload_audio exception: {e}")
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
        print(f"[Web] index.html marker={has_marker} size={size} mtime={mtime}")
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
    print(f"[Web] ClientLog: {data}")
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
        print(f"[Web] Static path: {static_path}")
        
        packs_path = Path(self.controller.project_root) / "packs"
        app.mount("/packs", StaticFiles(directory=str(packs_path)), name="packs")
        
        temp_path = Path(self.controller.project_root) / "TEMP"
        temp_path.mkdir(parents=True, exist_ok=True)
        app.mount("/temp", StaticFiles(directory=str(temp_path)), name="temp")

        app.mount("/static", StaticFiles(directory=str(static_path), html=True), name="static")

        config = uvicorn.Config(app, host=self.host, port=self.port, log_level="error", log_config=None)
        server = uvicorn.Server(config)
        server.run()
