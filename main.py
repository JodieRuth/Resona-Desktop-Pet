import sys
import os
import logging
from pathlib import Path
project_root = Path(__file__).parent.absolute()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
import asyncio
import threading
import traceback
import ctypes
import json
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Any, Optional
from PySide6.QtCore import QObject, Signal, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from resona_desktop_pet.config import ConfigManager
from resona_desktop_pet.backend import LLMBackend, TTSBackend, MCPManager
from resona_desktop_pet.backend.sovits_manager import SoVITSManager
from resona_desktop_pet.ui.luna.main_window import MainWindow
from resona_desktop_pet.ui.tray_icon import TrayIcon
from resona_desktop_pet.cleanup_manager import cleanup_manager
if sys.platform == "win32":
    from resona_desktop_pet.behavior_monitor import BehaviorMonitor
else:
    BehaviorMonitor = None
from resona_desktop_pet.web_server import WebServerThread, session_manager, ClientSession
from memory.memory_manager import MemoryManager
from memory.startup_processor import StartupProcessor
from resona_desktop_pet.utils.logger import setup_logging, get_logger

def exception_hook(exctype, value, tb):
    traceback.print_exception(exctype, value, tb)
    logging.error("Uncaught exception:", exc_info=(exctype, value, tb))

def log(message):
    logging.info(message)

logger = logging.getLogger("Main")

class AudioPlayer(QObject):
    playback_finished = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer()
        self._audio_output = QAudioOutput()
        self._audio_output.setVolume(1.0)
        self._player.setAudioOutput(self._audio_output)
        self._player.mediaStatusChanged.connect(self._on_status_changed)
    def play(self, file_path: str):
        from PySide6.QtCore import QUrl
        self._player.setSource(QUrl.fromLocalFile(file_path))
        self._player.play()
    def stop(self):
        self._player.stop()
    def _on_status_changed(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.playback_finished.emit()
    def refresh_audio_device(self):
        try:
            self._player.stop()
            self._player.setAudioOutput(None)
            self._audio_output = QAudioOutput()
            self._audio_output.setVolume(1.0)
            self._player.setAudioOutput(self._audio_output)
            logger.info("[AudioPlayer] Audio output device refreshed to system default")
            return True
        except Exception as e:
            logger.warning(f"[AudioPlayer] Failed to refresh audio device: {e}")
            return False

class TimerScheduler(QObject):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.config = controller.config
        self.project_root = controller.project_root
        self.enabled = self.config.timer_enabled
        self.poll_interval = max(0.1, float(self.config.timer_poll_interval))
        self.inbox_path = self._resolve_path(self.config.timer_inbox_file)
        self.tasks_path = self._resolve_path(self.config.timer_tasks_file)
        self.pre_synthesize = self.config.timer_pre_synthesize
        self.tts_idle_sec = max(0.0, float(self.config.timer_tts_idle_sec))
        self.trigger_delay = max(0.0, float(self.config.timer_trigger_delay))
        self._synth_inflight_id = None
        self._synth_inflight_started_at = None
        self._synth_inflight_last_log_at = None
        self._last_busy = False
        self._busy_released_at = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        if self.enabled:
            self._timer.start(int(self.poll_interval * 1000))

    def refresh_config(self):
        self.enabled = self.config.timer_enabled
        self.poll_interval = max(0.1, float(self.config.timer_poll_interval))
        self.pre_synthesize = self.config.timer_pre_synthesize
        self.tts_idle_sec = max(0.0, float(self.config.timer_tts_idle_sec))
        self.trigger_delay = max(0.0, float(self.config.timer_trigger_delay))
        self.inbox_path = self._resolve_path(self.config.timer_inbox_file)
        self.tasks_path = self._resolve_path(self.config.timer_tasks_file)
        if self.enabled:
            if not self._timer.isActive():
                self._timer.start(int(self.poll_interval * 1000))
        else:
            self._timer.stop()

    def reset(self):
        self._synth_inflight_id = None
        self._synth_inflight_started_at = None
        self._synth_inflight_last_log_at = None
        self._last_busy = False
        self._busy_released_at = None
        self._write_json(self.inbox_path, [])
        self._write_json(self.tasks_path, [])

    def _resolve_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.project_root / path
        return path

    def _load_json(self, path: Path) -> list:
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
        except Exception as e:
            logger.warning(f"[Timer] Failed to read {path}: {e}")
        return []

    def _write_json(self, path: Path, data: list):
        try:
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[Timer] Failed to write {path}: {e}")

    def _normalize_task(self, entry: dict, now: float) -> dict:
        task_id = entry.get("id") or f"timer_{int(now * 1000)}_{random.randint(1000, 9999)}"
        delay_val = entry.get("time", entry.get("delay", entry.get("delay_sec", 0)))
        try:
            delay_sec = float(delay_val)
        except (TypeError, ValueError):
            delay_sec = 0.0
        due_at = entry.get("due_at")
        if due_at is None:
            due_at = now + max(0.0, delay_sec)
        try:
            due_at = float(due_at)
        except (TypeError, ValueError):
            due_at = now
        active_pack_id = getattr(self.config.pack_manager, "active_pack_id", "") or "default"
        return {
            "id": task_id,
            "created_at": float(entry.get("created_at", now)),
            "due_at": due_at,
            "emotion": entry.get("emotion", "<E:smile>"),
            "text_display": entry.get("text_display", ""),
            "text_tts": entry.get("text_tts", ""),
            "audio_path": entry.get("audio_path", ""),
            "status": entry.get("status", "pending"),
            "pack_id": entry.get("pack_id") or active_pack_id
        }

    def _tts_idle(self, now: float) -> bool:
        return (now - self.controller._tts_activity_at) >= self.tts_idle_sec

    def _ready_to_trigger(self, now: float) -> bool:
        if self._busy_released_at is None:
            return True
        return now >= self._busy_released_at + self.trigger_delay

    def _tick(self):
        if not self.enabled:
            return
        now = time.time()
        busy = self.controller.main_window.is_busy
        if self._last_busy and not busy:
            self._busy_released_at = now
        self._last_busy = busy

        tasks = self._load_json(self.tasks_path)
        inbox = self._load_json(self.inbox_path)
        if inbox:
            for entry in inbox:
                if isinstance(entry, dict):
                    tasks.append(self._normalize_task(entry, now))
            self._write_json(self.inbox_path, [])

        if self.pre_synthesize and not busy and self._tts_idle(now) and self._synth_inflight_id is None:
            for task in tasks:
                if task.get("status") in ["pending", "ready"] and not task.get("audio_path"):
                    task_pack_id = task.get("pack_id") or getattr(self.config.pack_manager, "active_pack_id", "") or "default"
                    if task_pack_id != getattr(self.config.pack_manager, "active_pack_id", ""):
                        continue
                    logger.info(f"[Timer] Pre-synthesize queued. id={task.get('id')} due_at={task.get('due_at')}")
                    self._start_synthesize(task)
                    break

        updated = False
        kept = []
        for task in tasks:
            status = task.get("status", "pending")
            if status in ["done", "failed"]:
                updated = True
                continue
            due_at = task.get("due_at", now)
            try:
                due_at = float(due_at)
            except (TypeError, ValueError):
                due_at = now

            if not task.get("broadcasted") and due_at - now <= 10.0:
                task_copy = task.copy()
                task_pack_id = task_copy.get("pack_id") or getattr(self.config.pack_manager, "active_pack_id", "") or "default"
                if task_copy.get("audio_path"):
                    try:
                        audio_p = Path(task_copy["audio_path"])
                        temp_dir = self.project_root / "TEMP"
                        if temp_dir in audio_p.parents:
                            task_copy["audio_url"] = f"/temp/{audio_p.name}"
                    except:
                        pass
                if task_copy.get("emotion"):
                    try:
                        rel_path = self.config.pack_manager.resolve_sprite_path(
                            task_pack_id,
                            self.config.default_outfit,
                            task_copy.get("emotion")
                        )
                        if rel_path:
                            task_copy["image_url"] = f"/packs/{rel_path}"
                    except:
                        pass

                asyncio.run_coroutine_threadsafe(
                    session_manager.broadcast_to_pack(task.get("pack_id", "default"), {
                        "type": "timer_event",
                        "task": task_copy,
                        "trigger_at": due_at
                    }),
                    self.controller._loop
                )
                task["broadcasted"] = True
                updated = True

            if now >= due_at:
                logger.info(f"[Timer] Task due. id={task.get('id')} status={status} audio={bool(task.get('audio_path'))} busy={busy}")
                if busy or not self._ready_to_trigger(now):
                    logger.info(f"[Timer] Task delayed (busy or cooldown). id={task.get('id')}")
                    task["status"] = "ready"
                    task.setdefault("ready_since", now)
                    kept.append(task)
                    updated = True
                    continue
                if self._trigger_task(task):
                    logger.info(f"[Timer] Task triggered and removed. id={task.get('id')}")
                    updated = True
                    continue
                task["status"] = "ready"
                kept.append(task)
                updated = True
                continue
            kept.append(task)

        if inbox or updated:
            self._write_json(self.tasks_path, kept)

    def _trigger_task(self, task: dict) -> bool:
        task_pack_id = task.get("pack_id") or getattr(self.config.pack_manager, "active_pack_id", "") or "default"
        active_pack_id = getattr(self.config.pack_manager, "active_pack_id", "") or "default"
        if task_pack_id != active_pack_id:
            logger.info(f"[Timer] Task skipped due to inactive pack. id={task.get('id')} task_pack={task_pack_id} active_pack={active_pack_id}")
            return True
        text = task.get("text_display", "")
        emotion = task.get("emotion", "<E:smile>")
        task_id = task.get("id")
        audio_path = task.get("audio_path")
        if audio_path:
            path = Path(audio_path)
            if path.exists():
                logger.info(f"[Timer] Playing pre-synth audio. id={task_id} path={path}")
                self.controller._trigger_voice_response(text, emotion, voice_file=str(path), is_behavior=False)
                return True
            logger.info(f"[Timer] Audio path missing. id={task_id} path={path}")
        timed_out = False
        if self.pre_synthesize:
            if self._synth_inflight_id is not None:
                if task_id and self._synth_inflight_id == task_id:
                    now = time.time()
                    started_at = self._synth_inflight_started_at or now
                    timeout_sec = max(5.0, float(self.config.sovits_timeout) + 5.0)
                    elapsed = now - started_at
                    if elapsed >= timeout_sec:
                        logger.info(f"[Timer] Synth timeout, falling back to text. id={task_id} waited={elapsed:.1f}s")
                        self._synth_inflight_id = None
                        self._synth_inflight_started_at = None
                        self._synth_inflight_last_log_at = None
                        timed_out = True
                    else:
                        last_log_at = self._synth_inflight_last_log_at or 0.0
                        if now - last_log_at >= 5.0:
                            logger.info(f"[Timer] Awaiting synth result. id={task_id} waited={elapsed:.1f}s")
                            self._synth_inflight_last_log_at = now
                        return False
                if self._synth_inflight_id is not None:
                    logger.info(f"[Timer] Synth busy with another task. id={task_id} inflight={self._synth_inflight_id}")
                    return False
            if not timed_out and self._tts_idle(time.time()) and not self.controller.main_window.is_busy:
                logger.info(f"[Timer] Trigger requests synth. id={task_id}")
                self._start_synthesize(task)
                return False
        self.controller.main_window.show_behavior_response_with_timeout(text, emotion)
        logger.info(f"[Timer] Trigger fell back to text. id={task_id}")
        return True

    async def _synthesize_task(self, task: dict):
        self.controller._mark_tts_activity()
        text = task.get("text_tts") or task.get("text_display") or ""
        emotion = task.get("emotion", "<E:smile>")
        pack_id = task.get("pack_id") or getattr(self.config.pack_manager, "active_pack_id", "") or "default"
        result = await self.controller.tts_backend.synthesize(text, emotion, pack_id=pack_id)
        return result

    def _start_synthesize(self, task: dict):
        task_id = task.get("id")
        if not task_id:
            return
        self._synth_inflight_id = task_id
        self._synth_inflight_started_at = time.time()
        self._synth_inflight_last_log_at = self._synth_inflight_started_at
        logger.info(f"[Timer] Synth start. id={task_id} text_tts_len={len(task.get('text_tts') or '')}")
        self.controller._mark_tts_activity()
        future = asyncio.run_coroutine_threadsafe(self._synthesize_task(task), self.controller._loop)
        def _done(fut):
            QTimer.singleShot(0, self, lambda: self._on_synthesize_done(task_id, fut))
        future.add_done_callback(_done)

    def _on_synthesize_done(self, task_id: str, future):
        self._synth_inflight_id = None
        self._synth_inflight_started_at = None
        self._synth_inflight_last_log_at = None
        error = None
        result = None
        try:
            result = future.result()
        except Exception as e:
            error = str(e)
        tasks = self._load_json(self.tasks_path)
        updated = False
        for task in tasks:
            if task.get("id") != task_id:
                continue
            if result and getattr(result, "audio_path", None):
                task["audio_path"] = result.audio_path
                if getattr(result, "duration", None):
                    task["audio_duration"] = float(result.duration)
                    task["duration"] = float(result.duration)
                task["status"] = task.get("status", "pending")
                logger.info(f"[Timer] Synth done. id={task_id} path={result.audio_path}")
            else:
                task["status"] = "failed"
                task["error"] = error or getattr(result, "error", "unknown_error")
                logger.error(f"[Timer] Synth failed. id={task_id} error={task.get('error')}")
            updated = True
            break
        if updated:
            self._write_json(self.tasks_path, tasks)
class ApplicationController(QObject):
    llm_response_ready = Signal(object)
    tts_ready = Signal(object)
    stt_result_ready = Signal(object)
    request_stt_start = Signal()
    request_global_show = Signal()
    pack_switch_ready = Signal()
    external_query_signal = Signal(str)
    sovits_ready = Signal(bool, str)
    def __init__(self, sovits_log_path: Optional[Path] = None, llm_log_path: Optional[Path] = None):
        super().__init__()
        self.config = ConfigManager(str(project_root / "config.cfg"))
        self.project_root = Path(self.config.config_path).parent
        self.config.print_all_configs()
        pm = self.config.pack_manager
        logger.info(f"[Debug] PackManager Active ID: {pm.active_pack_id}")
        
        self._loop = asyncio.get_event_loop()
        
        self.sovits_manager = None
        self._sovits_startup_attempts = 0
        self._sovits_max_attempts = 3
        self._sovits_startup_thread = None
        self._sovits_ready = False
        self._pending_tts_requests: list = []
        
        if self.config.html_enabled:
            QTimer.singleShot(3000, self._start_web_server)
        
        if self.config.external_ws_enabled:
            QTimer.singleShot(4000, self._start_external_ws_server)

        logger.info(f"[Debug] PackManager Data Loaded: {bool(pm.pack_data)}")

        pm.load_plugins(self.config.plugins_enabled)

        if pm.pack_data:
            logger.info(f"[Debug] Character Name from Pack: {pm.get_info('character', {}).get('name')}")
        else:
            logger.info("[Debug] CRITICAL: Pack data is empty! Check pack.json path and ID.")
        self._cleanup_temp_dir()
        self._tts_activity_at = time.time()

        self.gpu_vendor = "Unknown"
        self.can_monitor_gpu = True
        try:
            import subprocess
            logger.info("[Main] GPU detection starting (using pnputil)...")
            output = ""
            try:
                result = subprocess.run(
                    'pnputil /enum-devices /class Display',
                    shell=True,
                    stderr=subprocess.STDOUT,
                    stdout=subprocess.PIPE,
                    timeout=2
                )
                raw_out = result.stdout
                try:
                    output = raw_out.decode("utf-8")
                except UnicodeDecodeError:
                    output = raw_out.decode("gbk", errors="ignore")
            except subprocess.TimeoutExpired:
                logger.info("[Main] GPU detection timed out on pnputil.")
            except Exception as ps_e:
                if not output.strip():
                    logger.warning(f"[Main] GPU detection failed (pnputil): {ps_e}")

            output_up = output.upper()
            has_nvidia = "NVIDIA" in output_up
            has_amd = "AMD" in output_up or "RADEON" in output_up

            if has_nvidia:
                self.gpu_vendor = "NVIDIA"
                self.can_monitor_gpu = True
                logger.info("[Main] NVIDIA GPU detected. GPU monitoring enabled.")
                if has_amd:
                    logger.info("[Main] Hybrid GPU system (NVIDIA + AMD) detected. Monitoring NVIDIA dGPU.")
            elif has_amd:
                self.gpu_vendor = "AMD"
                self.can_monitor_gpu = False
                logger.info("[Main] AMD GPU detected (No NVIDIA dGPU). Disabling GPU monitoring to prevent crashes.")
                if self.config.sovits_device == "cuda":
                    logger.info("[Main] AMD GPU detected but SoVITS device is 'cuda'. Forcing to 'cpu' for compatibility.")
                    self.config.set("SoVITS", "device", "cpu")
                    self.config.save()
            else:
                logger.info("[Main] No known discrete GPU detected (Intel or Unknown). GPU monitoring disabled.")
                self.can_monitor_gpu = False
        except Exception as e:
            logger.warning(f"[Main] GPU detection skipped or failed: {e}")

        self._stt_ready = False
        self._last_llm_response = None
        self._trigger_cooldown_end = 0
        self._post_busy_cooldown_end = 0
        self._last_busy_state = False
        self._pending_triggers = []
        self._is_chain_executing = False
        self._chain_cancelled = False
        self._current_sequence = []
        self._current_sequence_idx = 0
        self._current_chain_callback = None
        self._drop_tts_results = False
        self.current_weather = {}
        self.interaction_locked = False
        self._cleanup_started = False
        self._settings_dialog = None
        self.state = self._load_state()
        
        if self.config.sovits_enabled and self.config.sovits_mode == "local":
            logger.info("[Main] SoVITS async startup scheduled (local mode).")
            self.sovits_ready.connect(self._on_sovits_ready)
            self._start_sovits_async()
        
        self.mcp_manager = MCPManager(self.config)
        
        self.memory_manager = None
        if hasattr(self.config, 'memory_enabled') and self.config.memory_enabled:
            self.memory_manager = MemoryManager(self.project_root, self.config)
            logger.info("[Main] Memory manager initialized")
        
        self.llm_backend = LLMBackend(self.config, log_path=llm_log_path, mcp_manager=self.mcp_manager)
        if self.memory_manager:
            self.llm_backend._memory_manager = self.memory_manager
        
        self._current_watchdog_interval = 300000  
        def reset_watchdog():
            if self._busy_watchdog.isActive():
                self._busy_watchdog.start(self._current_watchdog_interval)
        self.llm_backend.set_on_activity_callback(reset_watchdog)
        
        self.tts_backend = TTSBackend(self.config, sovits_log_path=sovits_log_path)
        
        self.stt_backend = None
        if self.config.stt_enabled:
            from resona_desktop_pet.backend import get_stt_backend
            STTBackend = get_stt_backend()
            self.stt_backend = STTBackend(self.config)
            logger.info("[Main] STT backend initialized")
        else:
            logger.info("[Main] STT backend skipped")
        
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        
        if self.config.sovits_enabled and self.config.sovits_mode == "server":
            logger.info(f"[Main] SoVITS server mode: connecting to {self.config.sovits_server_host}:{self.config.sovits_server_port}")
            asyncio.run_coroutine_threadsafe(self._connect_remote_sovits(), self._loop)
        if self.config.mcp_enabled:
            logger.info("[Main] MCP startup begin.")
            future = asyncio.run_coroutine_threadsafe(self.mcp_manager.start(), self._loop)
            try:
                future.result(timeout=self.config.mcp_startup_timeout + 5)
            except Exception as e:
                logger.error(f"[Main] MCP startup failed: {e}")
        
        if hasattr(self.config, 'memory_enabled') and self.config.memory_enabled and self.config.memory_startup_processing:
            logger.info("[Main] Scheduling startup memory processing...")
            asyncio.run_coroutine_threadsafe(self._process_startup_memory(), self._loop)
        
        self.audio_player = AudioPlayer(self)
        self.audio_player.playback_finished.connect(self._on_audio_finished)
        self.main_window = MainWindow(self.config)
        self.main_window.controller = self
        self.timer_scheduler = TimerScheduler(self)

        self.tray_icon = TrayIcon(self.main_window)
        self.tray_icon.add_menu_action("Replay Last Response", self._replay_last_response)
        self.tray_icon.show()
        
        if hasattr(self.config, 'memory_enabled') and self.config.memory_enabled and self.config.memory_startup_processing:
            logger.info("[Main] Scheduling startup memory processing...")
            asyncio.run_coroutine_threadsafe(self._process_startup_memory(), self._loop)

        self.debug_panel = None
        if self.config.debug_panel:
            try:
                from resona_desktop_pet.ui.debug_panel import DebugPanel
                self.debug_panel = DebugPanel(self.config.pack_manager, self.config)
                self.debug_panel.request_manual_response.connect(self.handle_manual_debug_response)
                QTimer.singleShot(1000, lambda: self._add_debug_to_tray())
            except Exception as e:
                logger.warning(f"[Main] Failed to initialize DebugPanel: {e}")

        self.main_window.stats["total_clicks"] = self.state.get("total_clicks", 0)
        
        self._is_windows = sys.platform == "win32"
        
        if self._is_windows:
            self.behavior_monitor = BehaviorMonitor(self.config, self)
            self.behavior_monitor.fullscreen_status_changed.connect(self._handle_fullscreen_status)
            self.behavior_monitor.trigger_matched.connect(self._handle_behavior_trigger)
            self.main_window.file_dropped.connect(self.behavior_monitor.on_file_dropped)
            self.behavior_monitor.start()
        else:
            self.behavior_monitor = None
            logger.info("[Main] BehaviorMonitor disabled on non-Windows platform")
        self._mocker_process = None
        if self.config.debug_trigger:
            import subprocess
            mocker_script = self.project_root / "tools" / "sensor_mocker.py"
            logger.info(f"[Debug] debugtrigger is ENABLED. Starting sensor mocker: {mocker_script}")
            self._mocker_process = subprocess.Popen([sys.executable, str(mocker_script)], cwd=str(self.project_root))
        self.main_window.pack_changed.connect(self._handle_pack_change)
        self.main_window._pack_change_handler_connected = True
        logger.info("[PackSwitch] pack_changed signal connected")
        self.pack_switch_ready.connect(self._finalize_ui_after_pack_change, Qt.QueuedConnection)
        self.main_window.request_query.connect(self._handle_user_query)
        self.external_query_signal.connect(self._handle_user_query)
        self.main_window.replay_requested.connect(self._replay_last_response)
        self.main_window.settings_requested.connect(self._show_settings)
        self.main_window.refresh_audio_requested.connect(self._refresh_audio_devices)
        self.llm_response_ready.connect(self._handle_llm_response)
        self.tts_ready.connect(self._handle_tts_ready)
        self.stt_result_ready.connect(self._handle_stt_result)
        self.request_stt_start.connect(self._handle_stt_request)
        self.request_global_show.connect(self.main_window.manual_show)
        self._trigger_check_timer = QTimer()
        self._trigger_check_timer.timeout.connect(self._check_pending_triggers)
        self._trigger_check_timer.start(1000)
        self._busy_watchdog = QTimer()
        self._busy_watchdog.setSingleShot(True)
        self._busy_watchdog.timeout.connect(self._force_unlock)
        self._pack_switch_wait_timer = QTimer()
        self._pack_switch_wait_timer.setInterval(500)
        self._pack_switch_wait_timer.timeout.connect(self._check_pack_switch_ready)
        self._pack_switch_pending = False
        self._pack_switch_deadline = 0.0
        self._last_question_time = time.time()
        self._idle_trigger_count = 0
        self._idle_trigger_timer = QTimer()
        self._idle_trigger_timer.timeout.connect(self._check_idle_trigger)
        if self.config.idle_trigger_enabled:
            self._idle_trigger_timer.start(1000)
        QTimer.singleShot(2000, self._check_startup_events)
        QTimer.singleShot(1000, self._init_hotkeys)
        QTimer.singleShot(500, self.main_window.manual_show)
    @property
    def is_busy(self) -> bool:
        return self._is_chain_executing or self.main_window.is_busy or self.interaction_locked
    
    def _start_sovits_async(self):
        if self._sovits_startup_thread and self._sovits_startup_thread.is_alive():
            logger.info("[Main] SoVITS startup thread already running.")
            return
        
        self._sovits_startup_thread = threading.Thread(
            target=self._sovits_startup_worker,
            daemon=True
        )
        self._sovits_startup_thread.start()
    
    def _sovits_startup_worker(self):
        while self._sovits_startup_attempts < self._sovits_max_attempts:
            self._sovits_startup_attempts += 1
            attempt = self._sovits_startup_attempts
            
            logger.info(f"[Main] SoVITS startup attempt {attempt}/{self._sovits_max_attempts}")
            
            try:
                manager = SoVITSManager(
                    self.project_root,
                    self.config.sovits_api_port,
                    self.config.sovits_device,
                    self.config.sovits_model_version
                )
                
                if manager.start(timeout=60, kill_existing=self.config.sovits_kill_existing):
                    self.sovits_manager = manager
                    logger.info(f"[Main] SoVITS started successfully on attempt {attempt}.")
                    self.sovits_ready.emit(True, f"SoVITS service ready (attempt {attempt}/{self._sovits_max_attempts})")
                    return
                else:
                    logger.warning(f"[Main] SoVITS startup attempt {attempt} failed: start() returned False")
                    if manager.process:
                        try:
                            manager.stop()
                        except:
                            pass
            except Exception as e:
                logger.warning(f"[Main] SoVITS startup attempt {attempt} exception: {e}")
            
            if attempt < self._sovits_max_attempts:
                logger.info(f"[Main] Retrying SoVITS startup in 2 seconds...")
                time.sleep(2)
        
        logger.error(f"[Main] SoVITS startup failed after {self._sovits_max_attempts} attempts.")
        self.sovits_ready.emit(False, f"SoVITS service startup failed after {self._sovits_max_attempts} attempts")
    
    def _on_sovits_ready(self, success: bool, message: str):
        if success:
            self._sovits_ready = True
            logger.info(f"[Main] SoVITS ready: {message}")
            logger.info(f"[Main] {message}")
            
            if self._pending_tts_requests:
                logger.info(f"[Main] Processing {len(self._pending_tts_requests)} pending TTS request(s)...")
                for req in self._pending_tts_requests:
                    text, emotion, language, queued_at = req
                    delay = time.time() - queued_at
                    logger.info(f"[Main] Sending delayed TTS request (delayed {delay:.2f}s): '{text[:30]}...'")
                    asyncio.run_coroutine_threadsafe(
                        self._generate_tts_internal(text, emotion, language),
                        self._loop
                    )
                self._pending_tts_requests.clear()
        else:
            logger.error(f"[Main] SoVITS failed: {message}")
            self._pending_tts_requests.clear()
            QMessageBox.critical(None, "SoVITS Startup Failed", 
                f"Failed to start GPT-SoVITS service.\n\n{message}\n\nPlease check your configuration.")
            sys.exit(1)
    
    def _init_hotkeys(self):
        try:
            import keyboard
            g_hotkey = self.config.global_show_hotkey
            logger.info(f"[Main] Registering global show hotkey: {g_hotkey}")
            keyboard.add_hotkey(g_hotkey, lambda: self.request_global_show.emit())
        except Exception as e:
            logger.warning(f"[Main] Failed to register global show hotkey: {e}")

        if self.config.stt_enabled:
            logger.info("[Main] Initializing STT hotkey and loading model...")
            self.stt_backend.register_hotkey(lambda: self.request_stt_start.emit())
            asyncio.run_coroutine_threadsafe(self._async_init_stt(), self._loop)

    def _add_debug_to_tray(self):
        try:
            from resona_desktop_pet.ui.tray_icon import TrayIcon
            if hasattr(self, 'tray_icon'):
                self.tray_icon.add_menu_action("Dev Control Panel", self.debug_panel.show)
        except Exception as e:
            logger.warning(f"[Main] Tray integration for debug panel failed: {e}")

    def handle_manual_debug_response(self, data):
        response = data["response"]
        setattr(response, 'tts_lang', data.get("tts_lang", "ja"))

        logger.info(f"[DebugPanel] Manual response received: {response.emotion} | {response.text_display}")

        self.main_window.start_thinking()

        QTimer.singleShot(1500, lambda: self.llm_response_ready.emit(response))

    async def _async_init_stt(self):
        if not self.stt_backend:
            logger.info("[Main] STT backend not available, skipping model load.")
            return
        success = await self.stt_backend.load_model()
        if success:
            logger.info("[Main] STT Model loaded and ready.")
            self._stt_ready = True
        else:
            logger.error("[Main] STT Model loading FAILED.")
    def _force_unlock(self):
        if self.is_busy:
            logger.info("[Watchdog] BUSY state timeout! Force unlocking to prevent freeze.")
            self._is_chain_executing = False
            self.main_window.finish_processing()
    def _mark_tts_activity(self):
        self._tts_activity_at = time.time()

    async def handle_web_query(self, text: str, session: ClientSession):
        if not text.strip(): return
        session.touch()
        
        current_pack_id = session.pack_id
        if not current_pack_id or current_pack_id == "default":
            current_pack_id = self.config.pack_manager.active_pack_id
            session.pack_id = current_pack_id
            
        current_outfit = session.outfit or self.config.default_outfit
            
        pm = self.config.pack_manager
        
        thinking_texts = []
        if self.config.thinking_text_enabled:
            thinking_path = pm.get_path("logic", "thinking", pack_id=current_pack_id)
            if not thinking_path or not thinking_path.exists():
                pack_root = pm.packs_dir / current_pack_id
                fallback_path = pack_root / "logic" / "thinking.json"
                if fallback_path.exists():
                    thinking_path = fallback_path
            if thinking_path and thinking_path.exists():
                try:
                    with open(thinking_path, "r", encoding="utf-8") as f:
                        thinking_texts = json.load(f)
                except: pass
        
        def get_random_think_text():
            entry = random.choice(thinking_texts) if thinking_texts else "Thinking..."
            if isinstance(entry, dict):
                val = entry.get("text", "Thinking...")
                return str(val) if val is not None else "Thinking..."
            return str(entry)

        think_text = get_random_think_text()
        
        if threading.current_thread() != threading.main_thread():
            QTimer.singleShot(0, self.main_window.start_thinking)
        else:
            self.main_window.start_thinking()
        
        think_img_url = None
        rel_path = pm.resolve_sprite_path(current_pack_id, current_outfit, "<E:thinking>")
        if rel_path:
            think_img_url = f"/packs/{rel_path}"

        await session.websocket.send_json({
            "type": "status", 
            "state": "thinking", 
            "text": think_text,
            "image_url": think_img_url
        })
        await session_manager.broadcast_all({"type": "status", "state": "busy"})
        
        stop_thinking_event = asyncio.Event()
        
        async def rotate_thinking_text():
            if not self.config.thinking_text_switch or not thinking_texts:
                return
            
            await asyncio.sleep(self.config.thinking_text_time)
            
            while not stop_thinking_event.is_set():
                new_text = get_random_think_text()
                try:
                    await session.websocket.send_json({
                        "type": "status",
                        "state": "thinking", 
                        "text": new_text,
                    })
                except:
                    break
                
                try:
                    await asyncio.wait_for(stop_thinking_event.wait(), timeout=self.config.thinking_text_switch_time)
                except asyncio.TimeoutError:
                    continue 
                except asyncio.CancelledError:
                    break

        rotation_task = asyncio.create_task(rotate_thinking_text())

        try:
            source = session.client_type if hasattr(session, "client_type") and session.client_type else "web_client"
            response = await self.llm_backend.query(text, history=session.history, pack_id=current_pack_id, source=source)
            
            stop_thinking_event.set()
            if not rotation_task.done():
                rotation_task.cancel()
                try: await rotation_task
                except: pass
            
            if response.error:
                await session.websocket.send_json({"type": "error", "message": response.error})
            else:
                audio_path = None
                duration = 0.0
                if self.config.sovits_enabled and response.text_tts:
                     tts_res = await self.tts_backend.synthesize(
                         response.text_tts, 
                         response.emotion, 
                         pack_id=current_pack_id
                     )
                     if tts_res.audio_path:
                         p = Path(tts_res.audio_path)
                         if "TEMP" in p.parts:
                             audio_path = f"/temp/{p.name}"
                         else:
                             audio_path = f"/temp/{p.name}"
                         duration = tts_res.duration

                image_url = None
                if response.emotion:
                    pm = self.config.pack_manager
                    rel_path = pm.resolve_sprite_path(
                        current_pack_id, 
                        current_outfit, 
                        response.emotion
                    )
                    if rel_path:
                        image_url = f"/packs/{rel_path}"

                await session.websocket.send_json({
                    "type": "speak",
                    "text": response.text_display,
                    "emotion": response.emotion,
                    "audio_url": audio_path,
                    "duration": duration,
                    "image_url": image_url
                })
                

        except Exception as e:
            await session.websocket.send_json({"type": "error", "message": str(e)})
            traceback.print_exc()
        
        idle_image_url = None
        try:
            from resona_desktop_pet.web_server.server import resolve_idle_image
            idle_image_url = resolve_idle_image(self, current_pack_id, current_outfit)
        except Exception:
            idle_image_url = None
        await session.websocket.send_json({"type": "status", "state": "idle", "image_url": idle_image_url})
        await session_manager.broadcast_all({"type": "status", "state": "idle"})
        
        if threading.current_thread() != threading.main_thread():
            QTimer.singleShot(0, self.main_window.finish_processing)
        else:
            self.main_window.finish_processing()

    async def handle_web_settings_update(self, settings: dict, session: ClientSession):
        session.touch()
        updated = False
        
        if "stt_silence_threshold" in settings:
            try:
                val = float(settings["stt_silence_threshold"])
                self.config.set("STT", "silence_threshold", val)
                updated = True
            except: pass
            
        if "stt_max_duration" in settings:
            try:
                val = float(settings["stt_max_duration"])
                self.config.set("STT", "max_duration", val)
                updated = True
            except: pass
            
        if updated:
            self.config.save()
            self._on_settings_saved() 
            
            await session_manager.broadcast_all({
                "type": "config_updated",
                "config": {
                    "stt_max_duration": self.config.stt_max_duration,
                    "stt_silence_threshold": self.config.stt_silence_threshold
                }
            })
            
    async def handle_web_pack_switch(self, pack_id: str, session: ClientSession):
        session.touch()
        
        logger.info(f"[Web] Session {session.session_id} switching to pack {pack_id}")
        
        try:
            session.pack_id = pack_id
            session.outfit = None 
            
            from resona_desktop_pet.web_server.server import get_initial_pack_state
            
            pack_state = get_initial_pack_state(self, pack_id=pack_id, outfit_id=None)
            

            await session.websocket.send_json({
                "type": "handshake_ack", 
                "session_id": session.session_id,
                "config": {
                    "stt_max_duration": self.config.stt_max_duration,
                    "stt_silence_threshold": self.config.stt_silence_threshold,
                    "sovits_enabled": self.config.sovits_enabled,
                    "text_read_speed": self.config.text_read_speed,
                    "base_display_time": self.config.base_display_time,
                    **pack_state
                }
            })
            
        except Exception as e:
            logger.error(f"[Web] Pack switch failed: {e}")
            await session.websocket.send_json({"type": "error", "message": f"Pack switch failed: {str(e)}"})

    async def handle_web_start_recording(self, session: ClientSession):
        session.touch()
        
        current_pack_id = session.pack_id
        if not current_pack_id or current_pack_id == "default":
            current_pack_id = self.config.pack_manager.active_pack_id
            
        pm = self.config.pack_manager
        listening_texts = []
        if self.config.listening_text_enabled:
            listening_path = pm.get_path("logic", "listening", pack_id=current_pack_id)
            if not listening_path or not listening_path.exists():
                pack_root = pm.packs_dir / current_pack_id
                fallback_paths = [
                    pack_root / "logic" / "recording.json",
                    pack_root / "logic" / "listening.json"
                ]
                for candidate in fallback_paths:
                    if candidate.exists():
                        listening_path = candidate
                        break
            if listening_path and listening_path.exists():
                try:
                    with open(listening_path, "r", encoding="utf-8") as f:
                        listening_texts = json.load(f)
                except: pass
        
        listen_text_entry = random.choice(listening_texts) if listening_texts else "Listening..."
        if isinstance(listen_text_entry, dict):
            val = listen_text_entry.get("text", "Listening...")
            listen_text = str(val) if val is not None else "Listening..."
        else:
            listen_text = str(listen_text_entry)
        
        listen_img_url = None
        rel_path = pm.resolve_sprite_path(current_pack_id, session.outfit or self.config.default_outfit, "<E:thinking>")
        if rel_path:
            listen_img_url = f"/packs/{rel_path}"

        await session.websocket.send_json({
            "type": "status", 
            "state": "listening",
            "text": listen_text,
            "image_url": listen_img_url
        })
        
        if threading.current_thread() != threading.main_thread():
            QTimer.singleShot(0, lambda: self.main_window.set_listening(True))
        else:
            self.main_window.set_listening(True)

    async def handle_web_audio(self, file_path: str, session: ClientSession):
        session.touch()
        logger.info(f"[Web] handle_web_audio start path={file_path}")
        
        if threading.current_thread() != threading.main_thread():
            QTimer.singleShot(0, lambda: self.main_window.set_listening(False))
        else:
            self.main_window.set_listening(False)

        await session.websocket.send_json({
            "type": "status", 
            "state": "busy",
            "text": "Processing audio..."
        })
        
        timeout_sec = float(self.config.stt_max_duration) + 15.0
        try:
            if self.stt_backend:
                res = await asyncio.wait_for(
                    asyncio.to_thread(self.stt_backend.recognize_file, file_path),
                    timeout=timeout_sec
                )
            else:
                res = None
                logger.info("[Web] STT backend not available")
        except asyncio.TimeoutError:
            res = None
            logger.info(f"[Web] handle_web_audio stt timeout after {timeout_sec}s")
        if res:
            logger.debug(f"[Web] handle_web_audio stt done error={res.error} text_len={len(res.text) if res and res.text else 0}")
        
        try:
            os.remove(file_path)
        except: pass

        if not res:
             await session.websocket.send_json({"type": "error", "message": "STT timeout"})
             idle_image_url = None
             try:
                 from resona_desktop_pet.web_server.server import resolve_idle_image
                 idle_image_url = resolve_idle_image(self, session.pack_id, session.outfit or self.config.default_outfit)
             except Exception:
                 idle_image_url = None
             await session.websocket.send_json({"type": "status", "state": "idle", "image_url": idle_image_url})
        elif res.error:
             await session.websocket.send_json({"type": "error", "message": res.error})
             idle_image_url = None
             try:
                 from resona_desktop_pet.web_server.server import resolve_idle_image
                 idle_image_url = resolve_idle_image(self, session.pack_id, session.outfit or self.config.default_outfit)
             except Exception:
                 idle_image_url = None
             await session.websocket.send_json({"type": "status", "state": "idle", "image_url": idle_image_url})
        else:
             logger.info(f"[Web] handle_web_audio transcription={res.text}")
             await session.websocket.send_json({"type": "transcription", "text": res.text})
             await self.handle_web_query(res.text, session)

    def _handle_user_query(self, text: str):
        logger.info(f"[Main] _handle_user_query called with: '{text}' (thread: {threading.current_thread().name})")
        if not text.strip(): return

        if self.is_busy:
            logger.info(f"[Main] Program is busy, ignoring user query: {text}")
            return
            
        logger.info(f"[Main] User query received: {text}")
        self._last_question_time = time.time()
        self._idle_trigger_count = 0
        self._current_watchdog_interval = 300000
        self._busy_watchdog.start(self._current_watchdog_interval)
        self.main_window.start_thinking()
        asyncio.run_coroutine_threadsafe(self._query_llm(text), self._loop)
    async def _query_llm(self, text: str):
        try:
            response = await self.llm_backend.query(text, pack_id=self.config.pack_manager.active_pack_id, source="desktop")
            self.llm_response_ready.emit(response)
        except Exception as e:
            logger.error(f"[Main] LLM query failed: {e}")
            from resona_desktop_pet.backend.llm_backend import LLMResponse
            self.llm_response_ready.emit(LLMResponse(error=str(e)))

    def _handle_llm_response(self, response):
        self._last_llm_response = response
        logger.debug(f"[Main] LLM response returned. Error={response.error}")
        
        self._current_watchdog_interval = (self.config.sovits_timeout + 15) * 1000
        if self._busy_watchdog.isActive():
            self._busy_watchdog.start(self._current_watchdog_interval)

        if response.error:
            self._show_error_response("llm_generic_error", response.error)
            return
        self._current_text = response.text_display
        self._current_emotion = response.emotion
        tts_lang_for_trigger = getattr(response, 'tts_lang', None)
        self._trigger_voice_response(response.text_display, response.emotion, None, tts_text=response.text_tts, tts_lang=tts_lang_for_trigger)
    def _handle_tts_ready(self, result):
        logger.debug(f"[Main] TTS synthesized ready. Success={not result.error}")
        if self._drop_tts_results or self._pack_switch_pending:
            logger.info("[Main] Dropping TTS result due to pack switch.")
            return
        self._mark_tts_activity()
        self.main_window.show_response(self._current_text, self._current_emotion)
        if result.error:
            self._show_error_response("sovits_timeout_error", result.error)
            return
        if result.audio_path:
            self._mark_tts_activity()
            self.audio_player.play(result.audio_path)
        else:
            QTimer.singleShot(2000, self.main_window.finish_processing)
    def _on_audio_finished(self):
        try:
            logger.info("[Main] Audio playback finished.")
            self._mark_tts_activity()
            self.main_window.set_speaking(False)
            self.main_window.on_audio_complete()
            self._busy_watchdog.stop()
        except OverflowError as e:
            logger.error(f"[Main] OverflowError in _on_audio_finished: {e}")
            self._is_chain_executing = False

    def _start_web_server(self):
        try:
            if not self.config.html_enabled:
                return
            
            self.web_server_thread = WebServerThread(
                self, 
                self._loop,
                self.config.html_host,
                self.config.html_port,
                self.config.html_static_dir
            )
            self.web_server_thread.start()
            logger.info(f"[Main] Web server started on {self.config.html_host}:{self.config.html_port}")
        except Exception as e:
            logger.error(f"[Main] Failed to start web server: {e}")

    def _start_external_ws_server(self):
        try:
            from resona_desktop_pet.web_server import ExternalWSServerThread
            self.external_ws_thread = ExternalWSServerThread(
                self,
                self._loop,
                self.config.external_ws_host,
                self.config.external_ws_port
            )
            self.external_ws_thread.start()
            logger.info(f"[Main] External WebSocket server started on {self.config.external_ws_host}:{self.config.external_ws_port}")
        except Exception as e:
            logger.error(f"[Main] Failed to start external WS server: {e}")

    def _trigger_voice_response(self, text, emotion, voice_file=None, is_behavior=False, tts_text=None, tts_lang=None):
        if is_behavior and self.config.disable_actions:
            return
        v_path = None
        if voice_file:
            voice_path = Path(voice_file)
            if voice_path.is_absolute():
                v_path = voice_path
                pack_audio_path = None
            else:
                pack_audio_path = self.config.pack_manager.get_path("audio", "event_dir")
                v_path = (pack_audio_path / voice_file) if pack_audio_path else voice_path
            
            if not v_path.exists() and pack_audio_path and pack_audio_path.exists():
                search_name = Path(voice_file).name
                logger.info(f"[Main] Direct path not found: {v_path}. Searching for '{search_name}' in {pack_audio_path}...")
                matches = list(pack_audio_path.rglob(search_name))
                if matches:
                    v_path = matches[0]
                    logger.info(f"[Main] Found match via recursive search: {v_path}")
        
        if v_path and v_path.exists():
            logger.info(f"[Main] Playing pre-recorded: {v_path}")
            self.main_window.set_speaking(True)
            self.main_window.show_response(text, emotion)
            self._mark_tts_activity()
            self.audio_player.play(str(v_path))
        elif self.config.sovits_enabled and not is_behavior:
            logger.info("[Main] Handing over to SoVITS synthesis chain.")
            self.main_window.set_speaking(True)
            self._mark_tts_activity()
            asyncio.run_coroutine_threadsafe(self._generate_tts(tts_text or text, emotion, language=tts_lang), self._loop)
        else:
            logger.info("[Main] No audio source available, showing text response with timeout.")
            self.main_window.show_behavior_response_with_timeout(text, emotion)
    async def _generate_tts(self, text: str, emotion: str, language: Optional[str] = None):
        if self.config.sovits_enabled and self.config.sovits_mode == "local" and not self._sovits_ready:
            queued_at = time.time()
            self._pending_tts_requests.append((text, emotion, language, queued_at))
            logger.info(f"[Main] TTS request queued (SoVITS not ready): '{text[:30]}...'")
            return
        
        await self._generate_tts_internal(text, emotion, language)
    
    async def _generate_tts_internal(self, text: str, emotion: str, language: Optional[str] = None):
        self._mark_tts_activity()

        if not language and self.config.use_pack_settings:
            language = self.config.pack_manager.get_info("tts_language", "ja")

        result = await self.tts_backend.synthesize(text, emotion, language=language)
        self.tts_ready.emit(result)
    def _handle_behavior_trigger(self, actions: list):
        if not actions or self.main_window.manual_hidden: return
        if self._pack_switch_pending: return
        if self.config.disable_actions: return
        if self.interaction_locked: return
        if self.main_window.is_processing or self.main_window.is_listening:
            return

        if self.is_busy:
            return

        if self.config.idle_trigger_enabled:
            self._halve_idle_time()

        now = time.time()
        is_debug = self.config.debug_trigger
        if is_debug:
            self._execute_actions_chain(actions)
            return
        if self.is_busy or now < self._trigger_cooldown_end:
            if not self._pending_triggers:
                self._pending_triggers.append(actions)
        else:
            self._trigger_cooldown_end = now + self.config.trigger_cooldown
            self._execute_actions_chain(actions)
    def _check_pending_triggers(self):
        now = time.time()
        if self.config.disable_actions:
            if self._pending_triggers:
                self._pending_triggers = []
            return
        if self._last_busy_state and not self.main_window.is_busy:
            self._post_busy_cooldown_end = now + self.config.post_busy_delay
        self._last_busy_state = self.main_window.is_busy
        if self._pending_triggers and not self.is_busy and now >= self._post_busy_cooldown_end and now >= self._trigger_cooldown_end:
            logger.info("[Main] Executing pending trigger from queue.")
            trigger = self._pending_triggers.pop(0)
            self._trigger_cooldown_end = now + self.config.trigger_cooldown
            self._execute_actions_chain(trigger)

    def _check_idle_trigger(self):
        if not self.config.idle_trigger_enabled:
            return
        if self.is_busy:
            return
        now = time.time()
        elapsed = now - self._last_question_time
        start_delay = self.config.idle_trigger_start_delay
        if elapsed < start_delay:
            return
        probability = self.config.idle_trigger_probability
        min_triggers = self.config.idle_trigger_min_triggers
        adjusted_elapsed = elapsed - start_delay
        seconds_passed = int(adjusted_elapsed)
        if seconds_passed <= 0:
            return
        expected_triggers = seconds_passed * probability
        if self._idle_trigger_count < min_triggers:
            if random.random() < probability or self._idle_trigger_count < seconds_passed * probability:
                self._trigger_idle_question()
        else:
            if random.random() < probability:
                self._trigger_idle_question()

    def _trigger_idle_question(self):
        if self.is_busy:
            return
        self._idle_trigger_count += 1
        logger.info(f"[Main] Idle trigger activated (count: {self._idle_trigger_count})")
        prompt = self.config.idle_trigger_prompt
        self._last_question_time = time.time()
        self.main_window.start_thinking()
        asyncio.run_coroutine_threadsafe(self._query_llm_idle(prompt), self._loop)

    async def _query_llm_idle(self, prompt: str):
        try:
            response = await self.llm_backend.query_idle(prompt, pack_id=self.config.pack_manager.active_pack_id)
            self.llm_response_ready.emit(response)
        except Exception as e:
            logger.error(f"[Main] Idle LLM query failed: {e}")
            from resona_desktop_pet.backend.llm_backend import LLMResponse
            self.llm_response_ready.emit(LLMResponse(error=str(e)))

    def _halve_idle_time(self):
        elapsed = time.time() - self._last_question_time
        halved = elapsed / 2
        self._last_question_time = time.time() - halved
        logger.info(f"[Main] Idle time halved: {elapsed:.1f}s -> {halved:.1f}s (remaining)")

    def _cancel_action_chain(self):
        self._chain_cancelled = True
        self._is_chain_executing = False
        self._drop_tts_results = True
        self._current_sequence = []
        self._current_sequence_idx = 0
        self._pending_triggers = []
        if self._current_chain_callback:
            try: self.audio_player.playback_finished.disconnect(self._current_chain_callback)
            except: pass
        self._current_chain_callback = None
        try:
            self.audio_player.stop()
        except Exception:
            pass
        try:
            self.main_window.set_speaking(False)
            self.main_window.finish_processing()
        except Exception:
            pass
        try:
            self._busy_watchdog.stop()
        except Exception:
            pass
    def _execute_actions_chain(self, actions):
        if self.config.disable_actions:
            return
        if self.config.action_bring_to_front and not self.config.always_on_top:
            self.main_window.manual_show()

        self._is_chain_executing = True
        self._chain_cancelled = False
        self._current_sequence = actions
        self._current_sequence_idx = 0

        self._current_chain_callback = None

        def execute_next():
            if self._chain_cancelled:
                return
            if self.config.disable_actions:
                self._chain_cancelled = True
                self._is_chain_executing = False
                return
            if self._current_sequence_idx >= len(self._current_sequence):
                if self._current_chain_callback:
                    try: self.audio_player.playback_finished.disconnect(self._current_chain_callback)
                    except: pass
                self._current_chain_callback = None
                self._is_chain_executing = False
                return

            action = self._current_sequence[self._current_sequence_idx]
            self._current_sequence_idx += 1

            if action.get("type") == "random_group":
                branches = action.get("branches", [])
                if branches:
                    selected = random.choices(branches, weights=[b.get("weight", 1.0) for b in branches])[0]
                    self._current_sequence = selected.get("actions", []) + self._current_sequence[self._current_sequence_idx:]
                    self._current_sequence_idx = 0
                execute_next()
                return

            if action.get("type") == "delay":

                try:
                    sec_val = action.get("sec", 1.0)

                    sec = float(sec_val) if sec_val is not None else 1.0

                    sec = max(0.0, min(sec, 300.0))
                    delay_ms = int(sec * 1000)
                    QTimer.singleShot(delay_ms, execute_next)
                except (ValueError, TypeError, OverflowError) as e:
                    logger.warning(f"[Main] Delay action parameter error: {action.get('sec')}, error: {e}")

                    execute_next()
                return

            if action.get("type") == "speak":
                try: self.audio_player.playback_finished.disconnect(execute_next)
                except: pass
                self.audio_player.playback_finished.connect(execute_next)
                self._trigger_voice_response(action.get("text", ""), action.get("emotion", "<E:smile>"), action.get("voice_file"), is_behavior=True)
                return

            self._execute_single_action(action)
            execute_next()

        self._current_chain_callback = execute_next
        execute_next()
    def _unlock_interaction(self):
        self.interaction_locked = False
        self.main_window.set_hard_lock(False)
        self.main_window.manual_show()
    def _execute_single_action(self, action):
        atype = action.get("type")
        mw = self.main_window
        if atype == "move_to":
            pos = action.get("pos", "bottom_right")
            screen = QApplication.primaryScreen().availableGeometry()
            if pos == "top_left": mw.move(20, 20)
            elif pos == "bottom_right": mw.move(screen.width() - mw.width() - 20, screen.height() - mw.height() - 20)
        elif atype == "fade_out":
            mw.fade_to(action.get("opacity", 0.3))
            mw.set_fade_recovery(action.get("hover_recovery", 0.0))
            fade_sec = action.get("sec")
            if fade_sec:
                try:
                    sec = float(fade_sec)
                    sec = max(0.0, min(sec, 300.0))
                    QTimer.singleShot(int(sec * 1000), lambda: mw.fade_to(1.0))
                except (ValueError, TypeError, OverflowError):
                    pass
        elif atype == "lock_interaction":
            duration = action.get("sec", 0.0)
            try:
                dur = float(duration) if duration is not None else 0.0
                dur = max(0.0, min(dur, 300.0))
                if dur > 0:
                    self.interaction_locked = True
                    mw.set_hard_lock(True, highlight=True)
                    QTimer.singleShot(int(dur * 1000), self._unlock_interaction)
            except (ValueError, TypeError, OverflowError):
                pass
        elif atype == "physics_add_directional_acceleration":
            if mw.physics_bridge:
                engine = mw.physics_bridge.engine
                try:
                    direction = int(action.get("direction", 1))
                except (ValueError, TypeError):
                    direction = 1
                try:
                    magnitude = float(action.get("magnitude", 0.0))
                except (ValueError, TypeError):
                    magnitude = 0.0
                direction = max(1, min(direction, 8))
                dirs = [
                    (1, 0),
                    (1, -1),
                    (0, -1),
                    (-1, -1),
                    (-1, 0),
                    (-1, 1),
                    (0, 1),
                    (1, 1)
                ]
                dx, dy = dirs[direction - 1]
                engine.accel_x += dx * magnitude
                engine.accel_y += dy * magnitude
                engine.accel_enabled = True
        elif atype == "physics_disable_temporarily":
            if mw.physics_bridge:
                try:
                    sec = float(action.get("sec", 1.0))
                except (ValueError, TypeError):
                    sec = 1.0
                sec = max(0.0, min(sec, 300.0))
                mw.physics_bridge.set_enabled(False)
                QTimer.singleShot(int(sec * 1000), lambda: mw.physics_bridge.set_enabled(True))
        elif atype == "physics_multiply_forces":
            if mw.physics_bridge:
                engine = mw.physics_bridge.engine
                try:
                    multiplier = float(action.get("multiplier", 1.0))
                except (ValueError, TypeError):
                    multiplier = 1.0
                try:
                    sec = float(action.get("sec", 1.0))
                except (ValueError, TypeError):
                    sec = 1.0
                sec = max(0.0, min(sec, 300.0))
                mw._physics_force_token += 1
                token = mw._physics_force_token
                mw._physics_force_restore = (engine.gravity, engine.accel_x, engine.accel_y)
                engine.gravity *= multiplier
                engine.accel_x *= multiplier
                engine.accel_y *= multiplier
                def restore():
                    if getattr(mw, "_physics_force_token", 0) == token and mw.physics_bridge:
                        restore_vals = getattr(mw, "_physics_force_restore", None)
                        if restore_vals:
                            engine.gravity, engine.accel_x, engine.accel_y = restore_vals
                QTimer.singleShot(int(sec * 1000), restore)
        elif atype == "exit_app":
            logger.info("[Main] Exit action triggered.")
            self.force_exit()
        else:
            if self.config.plugins_enabled:
                pm = self.config.pack_manager
                if atype in pm.plugin_action_map:
                    pid = pm.plugin_action_map[atype]
                    module = pm.loaded_plugins.get(pid)
                    if module:
                        logger.info(f"[Main] Forwarding action '{atype}' to plugin '{pid}'")
                        params = action.get("params", [])
                        threading.Thread(target=module.execute_action, args=(atype, params), daemon=True).start()
    def _handle_pack_change(self, pack_id: str):
        logger.info(f"[PackSwitch] Start: requested={pack_id} current_active={self.config.pack_manager.active_pack_id} project_root={self.project_root}")
        self._cancel_action_chain()
        self.main_window.hide()
        if hasattr(self, "timer_scheduler"):
            self.timer_scheduler.reset()
        
        self.config.pack_manager.set_active_pack(pack_id)
        self.config.pack_manager.load_plugins(self.config.plugins_enabled)
        
        if hasattr(self, 'llm_backend'):
            logger.info(f"[PackSwitch] Clearing conversation history for new pack: {pack_id}")
            self.llm_backend.clear_history()

        pdata = self.config.pack_manager.pack_data
        character = pdata.get("character", {})
        new_name = character.get("name", "Unknown")
        outfits = character.get("outfits", [])
        target_outfit = next((o for o in outfits if o.get("is_default")), None)
        if not target_outfit and outfits:
            target_outfit = outfits[0]
        new_outfit = target_outfit.get("id", "default") if target_outfit else "default"
        raw_prompt_rel = pdata.get("logic", {}).get("prompts", [{}])[0].get("path", "")
        logger.info(f"[PackSwitch] Pack data: active_pack_id={self.config.pack_manager.active_pack_id} name={new_name} default_outfit={new_outfit} prompt_rel={raw_prompt_rel}")
        
        self.config.set("General", "active_pack", pack_id)
        self.config.set("General", "CharacterName", new_name)
        self.config.set("General", "default_outfit", new_outfit)
        self.config.set("Prompt", "file_path", Path(raw_prompt_rel).name)
        
        self.config.save()
        self.config.load()
        if not self.config.sovits_enabled:
            try:
                logger.info(f"[PackSwitch] Pre-refresh config: active_pack={self.config.get('General','active_pack','')} default_outfit={self.config.default_outfit}")
                self.main_window.refresh_from_config()
                self.main_window.manual_show()
            except Exception as e:
                logger.error(f"[PackSwitch] ERROR during pre-refresh: {e}")
                logger.error(traceback.format_exc())
        else:
            logger.info("[PackSwitch] Deferring UI refresh until SoVITS ready")
        
        logger.info("[PackSwitch] Reloading backends")
        self.tts_backend.reload_config()
        self.llm_backend.history.clear()
        if self.behavior_monitor:
            self.behavior_monitor.load_triggers()

        self._pack_switch_pending = True
        self._pack_switch_deadline = time.time() + 75
        if not self._pack_switch_wait_timer.isActive():
            self._pack_switch_wait_timer.start()
        logger.info(f"[PackSwitch] Wait start: pending={self._pack_switch_pending} deadline={self._pack_switch_deadline} sovits_enabled={self.config.sovits_enabled}")

        if self.config.sovits_enabled:
            def wait_for_sovits_then_show():
                if self.sovits_manager.is_running():
                    logger.info("[PackSwitch] SoVITS is already running, skipping restart.")
                    self.tts_backend.reload_config()
                    self.pack_switch_ready.emit()
                    return

                logger.info("[PackSwitch] Starting SoVITS and waiting for API...")
                try:
                    success = self.sovits_manager.start(timeout=60, kill_existing=True)
                    logger.info(f"[PackSwitch] SoVITS start finished. Success={success}")
                    self.pack_switch_ready.emit()
                except Exception as e:
                    logger.error(f"[PackSwitch] CRITICAL ERROR in wait_for_sovits_then_show: {e}")
                    logger.error(traceback.format_exc())
                    self.pack_switch_ready.emit()
            
            thread = threading.Thread(target=wait_for_sovits_then_show, daemon=True)
            logger.info(f"[PackSwitch] Starting background thread: {thread.name}")
            thread.start()
        else:
            logger.info("[PackSwitch] SoVITS disabled, emitting signal directly.")
            self.pack_switch_ready.emit()

    def _check_pack_switch_ready(self):
        if not self._pack_switch_pending:
            if self._pack_switch_wait_timer.isActive():
                self._pack_switch_wait_timer.stop()
            return
        if self.config.sovits_enabled:
            ready = self.sovits_manager.is_running()
        else:
            ready = True
        timed_out = time.time() >= self._pack_switch_deadline
        if ready or timed_out:
            self._pack_switch_wait_timer.stop()
            self._pack_switch_pending = False
            self._finalize_ui_after_pack_change()

    def _finalize_ui_after_pack_change(self):
        logger.info("[PackSwitch] Finalizing UI refresh (triggered by signal)...")
        try:
            if self._pack_switch_wait_timer.isActive():
                self._pack_switch_wait_timer.stop()
            self._pack_switch_pending = False
            self._drop_tts_results = False
            self.config.load()
            if hasattr(self, "timer_scheduler"):
                self.timer_scheduler.refresh_config()
            logger.info(f"[PackSwitch] Finalize config: active_pack={self.config.get('General','active_pack','')} default_outfit={self.config.default_outfit}")
            self.main_window.refresh_from_config()
            
            if hasattr(self, 'tray_icon'):
                self.tray_icon.hide()
                self.tray_icon.show()
                
            self.main_window.manual_show()
            logger.info("[PackSwitch] Pack switch UI refresh complete.")
        except Exception as e:
            logger.error(f"[PackSwitch] ERROR during UI finalize: {e}")
            logger.error(traceback.format_exc())
    def _show_error_response(self, error_type, details=""):
        error_config_path = self.config.pack_manager.get_path("logic", "error_config")
        text, emotion, audio = f"Error: {details}", "<E:sad>", None
        if error_config_path and error_config_path.exists():
            try:
                with open(error_config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f).get(error_type, {})
                    text = cfg.get("text", text)
                    emotion = cfg.get("emotion", emotion)
                    if cfg.get("audio"):
                        aud_dir = self.config.pack_manager.get_path("audio", "error_dir")
                        if aud_dir: audio = str(aud_dir / cfg["audio"])
            except: pass
        if self.config.disable_actions:
            self.main_window.show_behavior_response_with_timeout(text, emotion)
        else:
            self._trigger_voice_response(text, emotion, audio, is_behavior=True)
        self._is_chain_executing = False
    def _replay_last_response(self):
        if not self._last_llm_response: return
        logger.info("[Main] Replaying last response...")
        self.main_window.start_thinking()
        self._handle_llm_response(self._last_llm_response)
    def _refresh_audio_devices(self):
        logger.info("[Main] Refreshing audio devices...")
        output_success = self.audio_player.refresh_audio_device()
        input_success = self.stt_backend.refresh_audio_device() if self.stt_backend else True
        if output_success and input_success:
            logger.info("[Main] Audio devices refreshed successfully")
        else:
            logger.warning("[Main] Failed to refresh some audio devices")
    def _handle_stt_request(self):
        if not self._stt_ready or not self.stt_backend:
            logger.info("[STT] STT not ready or not available, ignoring request.")
            return
        if self.stt_backend.is_recording():
            self.stt_backend.stop_recording()
            return
        logger.info("[STT] Recording started...")
        self.main_window.set_input_locked(True)
        self.main_window.set_listening(True, username=self.config.username)
        asyncio.run_coroutine_threadsafe(self.stt_backend.start_recording(on_complete=lambda r: self.stt_result_ready.emit(r)), self._loop)
    def _handle_stt_result(self, result):
        if result.error:
            logger.error(f"[STT] Error: {result.error}")
        logger.info(f"[STT] Result: '{result.text}'")
        self.main_window.set_listening(False)
        self.main_window.set_input_locked(False)
        if result.text:
            self.main_window.io.edit.setText(result.text)
            self._handle_user_query(result.text)
        else:
            self.main_window.io.show_status("未检测到语音")
            QTimer.singleShot(2000, self.main_window.finish_processing)
    def _handle_fullscreen_status(self, hidden):
        self.main_window.set_fullscreen_hidden(hidden)
    def _check_startup_events(self):
        enabled = self.config.weather_enabled
        logger.info(f"[Main] Startup events check. Weather enabled: {enabled}")
        if enabled:
            asyncio.run_coroutine_threadsafe(self._check_weather(), self._loop)
    async def _check_weather(self):
        import aiohttp
        logger.info("[Weather] Starting weather service (Geo-locating via IP)...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://ip-api.com/json/") as r:
                    data = await r.json()
                    city = data.get("city")
                    if not city:
                        logger.warning(f"[Weather] Location failed: {data.get('message', 'Unknown error')}")
                        return
                logger.info(f"[Weather] Located city: {city}. Fetching weather data...")
                url = f"http://api.weatherapi.com/v1/current.json?key={self.config.weather_api_key}&q={city}&lang=zh"
                async with session.get(url) as r:
                    if r.status == 200:
                        d = await r.json()
                        self.current_weather = {
                            "condition": d["current"]["condition"]["text"],
                            "temp": d["current"]["temp_c"]
                        }
                        logger.info(f"[Weather] SUCCESS: {self.current_weather['condition']}, {self.current_weather['temp']}°C")
                    else:
                        logger.error(f"[Weather] API error: Status {r.status}")
        except Exception as e:
            logger.error(f"[Weather] Service error: {e}")
    
    async def _process_startup_memory(self):
        """Process startup memory"""
        try:
            processor = StartupProcessor(self.project_root, self.config)
            await processor.process_startup()
        except Exception as e:
            logger.error(f"[Main] Error processing startup memory: {e}")
    
    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _connect_remote_sovits(self):
        try:
            pack_id = self.config.pack_manager.get_pack_json_id()
            if not pack_id:
                logger.info("[Main] No active pack, skipping remote SoVITS connection")
                return
            
            logger.info(f"[Main] Connecting to remote SoVITS with pack: {pack_id}")
            connected = await self.tts_backend.ensure_connected(pack_id)
            if connected:
                logger.info("[Main] Remote SoVITS connected successfully")
            else:
                logger.error("[Main] Failed to connect to remote SoVITS server")
        except Exception as e:
            logger.error(f"[Main] Error connecting to remote SoVITS: {e}")
    def _cleanup_temp_dir(self):
        import shutil
        temp_dir = self.project_root / "TEMP"
        if temp_dir.exists():
            for f in temp_dir.iterdir():
                try:
                    if f.is_file(): f.unlink()
                    elif f.is_dir(): shutil.rmtree(f)
                except: pass
    def _show_settings(self):
        from resona_desktop_pet.ui.settings_dialog import SettingsDialog
        if self._settings_dialog and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        self._settings_dialog = SettingsDialog(self.config, parent=self.main_window)
        self._settings_dialog.setModal(False)
        self._settings_dialog.setWindowModality(Qt.NonModal)
        self._settings_dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        self._settings_dialog.accepted.connect(self._on_settings_saved)
        self._settings_dialog.finished.connect(lambda _: setattr(self, "_settings_dialog", None))
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _on_settings_saved(self):
        logger.info("[Main] Config updated via settings dialog.")
        self.config.load()
        if self.behavior_monitor:
            self.behavior_monitor.load_triggers()
        if hasattr(self, "timer_scheduler"):
            self.timer_scheduler.refresh_config()
        if self.main_window:
            self.main_window.refresh_from_config()
    def force_exit(self):
        if self._cleanup_started:
            os._exit(0)
        self._cleanup_started = True
        try:
            if self._mocker_process:
                self._mocker_process.terminate()
        except Exception:
            pass
        try:
            if self.behavior_monitor:
                self.behavior_monitor.stop()
                self.behavior_monitor.wait(2000)
                if self.behavior_monitor.isRunning():
                    self.behavior_monitor.terminate()
        except Exception:
            pass
        try:
            if self.sovits_manager:
                self.sovits_manager.stop()
        except Exception:
            pass
        try:
            if self.stt_backend:
                self.stt_backend.cleanup()
        except Exception:
            pass
        try:
            cleanup_manager.cleanup()
        except Exception:
            pass
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        except Exception:
            pass
        os._exit(0)
    def cleanup(self):
        if self._cleanup_started:
            return
        self._cleanup_started = True

        if hasattr(self, 'memory_manager') and self.memory_manager and hasattr(self, 'llm_backend'):
            try:
                history = self.llm_backend.history.get_messages()
                if len(history) >= 2:
                    user_msg = None
                    assistant_msg = None
                    for msg in reversed(history):
                        if msg['role'] == 'assistant' and not assistant_msg:
                            assistant_msg = msg['content']
                        elif msg['role'] == 'user' and not user_msg:
                            user_msg = msg['content']
                        if user_msg and assistant_msg:
                            break
                    
                    if user_msg and assistant_msg:
                        self.memory_manager.save_temp_session(user_msg, assistant_msg)
                        logger.info("[Main] Temporary session saved for startup processing")
            except Exception as e:
                logger.error(f"[Main] Error saving temporary session: {e}")

        def _cleanup_task():
            if self._mocker_process:
                self._mocker_process.terminate()
            if self.behavior_monitor:
                self.behavior_monitor.stop()
                self.behavior_monitor.wait(2000)
                if self.behavior_monitor.isRunning():
                    self.behavior_monitor.terminate()
            if self.sovits_manager:
                self.sovits_manager.stop()
            if self.stt_backend:
                self.stt_backend.cleanup()
            cleanup_manager.cleanup()
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass

        threading.Thread(target=_cleanup_task, daemon=True).start()
    @property
    def state_path(self) -> Path:
        pack_dir = self.config.pack_manager.packs_dir / self.config.pack_manager.active_pack_id
        return pack_dir / "state.json"
    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                with open(self.state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {}
    def _save_state(self):
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4, ensure_ascii=False)
        except: pass
def is_admin():
    if sys.platform == "win32":
        try: return ctypes.windll.shell32.IsUserAnAdmin()
        except: return False
    else:
        import os
        return os.geteuid() == 0
def run_as_admin(timestamp: str = None):
    args = sys.argv[:]
    if "--timestamp" not in args and timestamp:
        args.extend(["--timestamp", timestamp])
    
    if sys.platform == "win32":
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(args), str(project_root), 1)
    else:
        try:
            os.execvp("pkexec", ["pkexec", sys.executable] + args)
        except FileNotFoundError:
            os.execvp("sudo", ["sudo", sys.executable] + args)

def main():
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--timestamp", type=str, default=None)
    args, unknown = parser.parse_known_args()

    if args.timestamp:
        timestamp = args.timestamp
    else:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    setup_logging(project_root, timestamp=timestamp)
    sys.excepthook = exception_hook

    log_dir = project_root / "logs" / timestamp
    sovits_log_file = log_dir / "sovits.log"
    llm_log_file = log_dir / "llm.log"

    config = ConfigManager(str(project_root / "config.cfg"))
    needs_admin = False
    if sys.platform == "win32":
        trigger_path = config.pack_manager.get_path("logic", "triggers")
        if trigger_path and trigger_path.exists():
            try:
                with open(trigger_path, "r", encoding="utf-8") as f:
                    triggers = json.load(f)
                    def check_sensitive(node):
                        if isinstance(node, dict):
                            if node.get('type') in ['cpu_temp', 'gpu_temp', 'url_match']: return True
                            for c in node.get('conditions', []):
                                if check_sensitive(c): return True
                        return False
                    for rule in triggers:
                        if check_sensitive(rule): needs_admin = True; break
            except: pass
    if needs_admin and not is_admin():
        run_as_admin(timestamp)
        sys.exit()

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    controller = ApplicationController(sovits_log_path=sovits_log_file, llm_log_path=llm_log_file)
    app.aboutToQuit.connect(controller.cleanup)
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
#你先别问我为什么写得这么逆天，我就问你能不能跑吧
#只要能动，里面到底是个八音盒还是个废料场真的很重要吗
#不要试图去理解我在想什么，我也不知道昨天的我在想什么，最好也不要让LLM来