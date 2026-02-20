import sys
import os
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
from resona_desktop_pet.backend import LLMBackend, TTSBackend, STTBackend, MCPManager
from resona_desktop_pet.backend.sovits_manager import SoVITSManager
from resona_desktop_pet.ui.luna.main_window import MainWindow
from resona_desktop_pet.ui.tray_icon import TrayIcon
from resona_desktop_pet.cleanup_manager import cleanup_manager
from resona_desktop_pet.behavior_monitor import BehaviorMonitor
log_dir = project_root / "logs"
log_dir.mkdir(exist_ok=True)
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = log_dir / f"app_{timestamp}.log"
sovits_log_file = log_dir / f"sovits_{timestamp}.log"
llm_log_file = log_dir / f"llm_{timestamp}.log"
import logging
def setup_dedicated_logger(name, file_path, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.FileHandler(file_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
        logger.addHandler(handler)
    logger.propagate = False
    return logger

def get_sovits_logger():
    return setup_dedicated_logger("SoVITS", sovits_log_file)

def get_llm_logger():
    return setup_dedicated_logger("LLM", llm_log_file)

def exception_hook(exctype, value, tb):
    traceback.print_exception(exctype, value, tb)
    logging.error("Uncaught exception:", exc_info=(exctype, value, tb))

sys.excepthook = exception_hook
# sovits_logger = setup_dedicated_logger("SoVITS", sovits_log_file)
# llm_logger = setup_dedicated_logger("LLM", llm_log_file)
class TeeLogger:
    def __init__(self, filename, terminal):
        self.terminal = terminal
        self.log_file = open(filename, "a", encoding="utf-8", buffering=1)
    def write(self, message):
        self.terminal.write(message)
        self.log_file.write(message)
    def flush(self):
        self.terminal.flush()
        self.log_file.flush()
def log(message):
    logging.info(message)
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
            log(f"[Timer] Failed to read {path}: {e}")
        return []

    def _write_json(self, path: Path, data: list):
        try:
            if path.parent and not path.parent.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log(f"[Timer] Failed to write {path}: {e}")

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
        return {
            "id": task_id,
            "created_at": float(entry.get("created_at", now)),
            "due_at": due_at,
            "emotion": entry.get("emotion", "<E:smile>"),
            "text_display": entry.get("text_display", ""),
            "text_tts": entry.get("text_tts", ""),
            "audio_path": entry.get("audio_path", ""),
            "status": entry.get("status", "pending")
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
                    log(f"[Timer] Pre-synthesize queued. id={task.get('id')} due_at={task.get('due_at')}")
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
            if now >= due_at:
                log(f"[Timer] Task due. id={task.get('id')} status={status} audio={bool(task.get('audio_path'))} busy={busy}")
                if busy or not self._ready_to_trigger(now):
                    log(f"[Timer] Task delayed (busy or cooldown). id={task.get('id')}")
                    task["status"] = "ready"
                    task.setdefault("ready_since", now)
                    kept.append(task)
                    updated = True
                    continue
                if self._trigger_task(task):
                    log(f"[Timer] Task triggered and removed. id={task.get('id')}")
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
        text = task.get("text_display", "")
        emotion = task.get("emotion", "<E:smile>")
        task_id = task.get("id")
        audio_path = task.get("audio_path")
        if audio_path:
            path = Path(audio_path)
            if path.exists():
                log(f"[Timer] Playing pre-synth audio. id={task_id} path={path}")
                self.controller._trigger_voice_response(text, emotion, voice_file=str(path), is_behavior=False)
                return True
            log(f"[Timer] Audio path missing. id={task_id} path={path}")
        timed_out = False
        if self.pre_synthesize:
            if self._synth_inflight_id is not None:
                if task_id and self._synth_inflight_id == task_id:
                    now = time.time()
                    started_at = self._synth_inflight_started_at or now
                    timeout_sec = max(5.0, float(self.config.sovits_timeout) + 5.0)
                    elapsed = now - started_at
                    if elapsed >= timeout_sec:
                        log(f"[Timer] Synth timeout, falling back to text. id={task_id} waited={elapsed:.1f}s")
                        self._synth_inflight_id = None
                        self._synth_inflight_started_at = None
                        self._synth_inflight_last_log_at = None
                        timed_out = True
                    else:
                        last_log_at = self._synth_inflight_last_log_at or 0.0
                        if now - last_log_at >= 5.0:
                            log(f"[Timer] Awaiting synth result. id={task_id} waited={elapsed:.1f}s")
                            self._synth_inflight_last_log_at = now
                        return False
                if self._synth_inflight_id is not None:
                    log(f"[Timer] Synth busy with another task. id={task_id} inflight={self._synth_inflight_id}")
                    return False
            if not timed_out and self._tts_idle(time.time()) and not self.controller.main_window.is_busy:
                log(f"[Timer] Trigger requests synth. id={task_id}")
                self._start_synthesize(task)
                return False
        self.controller.main_window.show_behavior_response_with_timeout(text, emotion)
        log(f"[Timer] Trigger fell back to text. id={task_id}")
        return True

    async def _synthesize_task(self, task: dict):
        self.controller._mark_tts_activity()
        text = task.get("text_tts") or task.get("text_display") or ""
        emotion = task.get("emotion", "<E:smile>")
        result = await self.controller.tts_backend.synthesize(text, emotion)
        return result

    def _start_synthesize(self, task: dict):
        task_id = task.get("id")
        if not task_id:
            return
        self._synth_inflight_id = task_id
        self._synth_inflight_started_at = time.time()
        self._synth_inflight_last_log_at = self._synth_inflight_started_at
        log(f"[Timer] Synth start. id={task_id} text_tts_len={len(task.get('text_tts') or '')}")
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
                task["status"] = task.get("status", "pending")
                log(f"[Timer] Synth done. id={task_id} path={result.audio_path}")
            else:
                task["status"] = "failed"
                task["error"] = error or getattr(result, "error", "unknown_error")
                log(f"[Timer] Synth failed. id={task_id} error={task.get('error')}")
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
    def __init__(self, sovits_log_path: Optional[Path] = None):
        super().__init__()
        self.config = ConfigManager(str(project_root / "config.cfg"))
        self.config.print_all_configs()
        pm = self.config.pack_manager
        log(f"[Debug] PackManager Active ID: {pm.active_pack_id}")
        log(f"[Debug] PackManager Data Loaded: {bool(pm.pack_data)}")

        pm.load_plugins(self.config.plugins_enabled)

        if pm.pack_data:
            log(f"[Debug] Character Name from Pack: {pm.get_info('character', {}).get('name')}")
        else:
            log("[Debug] CRITICAL: Pack data is empty! Check pack.json path and ID.")
        self.project_root = Path(self.config.config_path).parent
        self._cleanup_temp_dir()
        self._tts_activity_at = time.time()

        self.gpu_vendor = "Unknown"
        self.can_monitor_gpu = True
        try:
            import subprocess
            log("[Main] GPU detection starting (using pnputil)...")
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
                log("[Main] GPU detection timed out on pnputil.")
            except Exception as ps_e:
                if not output.strip():
                    log(f"[Main] GPU detection failed (pnputil): {ps_e}")

            output_up = output.upper()
            has_nvidia = "NVIDIA" in output_up
            has_amd = "AMD" in output_up or "RADEON" in output_up

            if has_nvidia:
                self.gpu_vendor = "NVIDIA"
                self.can_monitor_gpu = True
                log("[Main] NVIDIA GPU detected. GPU monitoring enabled.")
                if has_amd:
                    log("[Main] Hybrid GPU system (NVIDIA + AMD) detected. Monitoring NVIDIA dGPU.")
            elif has_amd:
                self.gpu_vendor = "AMD"
                self.can_monitor_gpu = False
                log("[Main] AMD GPU detected (No NVIDIA dGPU). Disabling GPU monitoring to prevent crashes.")
                if self.config.sovits_device == "cuda":
                    log("[Main] AMD GPU detected but SoVITS device is 'cuda'. Forcing to 'cpu' for compatibility.")
                    self.config.set("SoVITS", "device", "cpu")
                    self.config.save()
            else:
                log("[Main] No known discrete GPU detected (Intel or Unknown). GPU monitoring disabled.")
                self.can_monitor_gpu = False
        except Exception as e:
            log(f"[Main] GPU detection skipped or failed: {e}")

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
        if self.config.sovits_enabled:
            log("[Main] SoVITS startup begin.")
            self.sovits_manager = SoVITSManager(
                self.project_root,
                self.config.sovits_api_port,
                self.config.sovits_device,
                self.config.sovits_model_version
            )
            if not self.sovits_manager.start(timeout=60, kill_existing=self.config.sovits_kill_existing):
                QMessageBox.critical(None, "SoVITS Error", "无法启动 GPT-SoVITS 服务，请检查配置。")
                sys.exit(1)
        self.mcp_manager = MCPManager(self.config)
        self.llm_backend = LLMBackend(self.config, log_path=llm_log_file, mcp_manager=self.mcp_manager)
        self.tts_backend = TTSBackend(self.config, sovits_log_path=sovits_log_path)
        self.stt_backend = STTBackend(self.config)
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        if self.config.mcp_enabled:
            log("[Main] MCP startup begin.")
            future = asyncio.run_coroutine_threadsafe(self.mcp_manager.start(), self._loop)
            try:
                future.result(timeout=self.config.mcp_startup_timeout + 5)
            except Exception as e:
                log(f"[Main] MCP startup failed: {e}")
        self.audio_player = AudioPlayer(self)
        self.audio_player.playback_finished.connect(self._on_audio_finished)
        self.main_window = MainWindow(self.config)
        self.main_window.controller = self
        self.timer_scheduler = TimerScheduler(self)

        self.tray_icon = TrayIcon(self.main_window)
        self.tray_icon.add_menu_action("Replay Last Response", self._replay_last_response)
        self.tray_icon.show()

        self.debug_panel = None
        if self.config.debug_panel:
            try:
                from resona_desktop_pet.ui.debug_panel import DebugPanel
                self.debug_panel = DebugPanel(self.config.pack_manager, self.config)
                self.debug_panel.request_manual_response.connect(self.handle_manual_debug_response)
                QTimer.singleShot(1000, lambda: self._add_debug_to_tray())
            except Exception as e:
                log(f"[Main] Failed to initialize DebugPanel: {e}")

        self.main_window.stats["total_clicks"] = self.state.get("total_clicks", 0)
        self.behavior_monitor = BehaviorMonitor(self.config, self)
        self.behavior_monitor.fullscreen_status_changed.connect(self._handle_fullscreen_status)
        self.behavior_monitor.trigger_matched.connect(self._handle_behavior_trigger)
        self.main_window.file_dropped.connect(self.behavior_monitor.on_file_dropped)
        self.behavior_monitor.start()
        self._mocker_process = None
        if self.config.debug_trigger:
            import subprocess
            mocker_script = self.project_root / "tools" / "sensor_mocker.py"
            log(f"[Debug] debugtrigger is ENABLED. Starting sensor mocker: {mocker_script}")
            self._mocker_process = subprocess.Popen([sys.executable, str(mocker_script)], cwd=str(self.project_root))
        self.main_window.pack_changed.connect(self._handle_pack_change)
        self.main_window._pack_change_handler_connected = True
        log("[PackSwitch] pack_changed signal connected")
        self.pack_switch_ready.connect(self._finalize_ui_after_pack_change, Qt.QueuedConnection)
        self.main_window.request_query.connect(self._handle_user_query)
        self.main_window.replay_requested.connect(self._replay_last_response)
        self.main_window.settings_requested.connect(self._show_settings)
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
        QTimer.singleShot(2000, self._check_startup_events)
        QTimer.singleShot(1000, self._init_hotkeys)
        QTimer.singleShot(500, self.main_window.manual_show)
    @property
    def is_busy(self) -> bool:
        return self._is_chain_executing or self.main_window.is_busy or self.interaction_locked
    def _init_hotkeys(self):
        try:
            import keyboard
            g_hotkey = self.config.global_show_hotkey
            log(f"[Main] Registering global show hotkey: {g_hotkey}")
            keyboard.add_hotkey(g_hotkey, lambda: self.request_global_show.emit())
        except Exception as e:
            log(f"[Main] Failed to register global show hotkey: {e}")

        if self.config.stt_enabled:
            log("[Main] Initializing STT hotkey and loading model...")
            self.stt_backend.register_hotkey(lambda: self.request_stt_start.emit())
            asyncio.run_coroutine_threadsafe(self._async_init_stt(), self._loop)

    def _add_debug_to_tray(self):
        try:
            from resona_desktop_pet.ui.tray_icon import TrayIcon
            if hasattr(self, 'tray_icon'):
                self.tray_icon.add_menu_action("Dev Control Panel", self.debug_panel.show)
        except Exception as e:
            log(f"[Main] Tray integration for debug panel failed: {e}")

    def handle_manual_debug_response(self, data):
        response = data["response"]
        setattr(response, 'tts_lang', data.get("tts_lang", "ja"))

        log(f"[DebugPanel] Manual response received: {response.emotion} | {response.text_display}")

        self.main_window.start_thinking()

        QTimer.singleShot(1500, lambda: self.llm_response_ready.emit(response))

    async def _async_init_stt(self):
        success = await self.stt_backend.load_model()
        if success:
            log("[Main] STT Model loaded and ready.")
            self._stt_ready = True
        else:
            log("[Main] STT Model loading FAILED.")
    def _force_unlock(self):
        if self.is_busy:
            log("[Watchdog] BUSY state timeout! Force unlocking to prevent freeze.")
            self._is_chain_executing = False
            self.main_window.finish_processing()
    def _mark_tts_activity(self):
        self._tts_activity_at = time.time()
    def _handle_user_query(self, text: str):
        if not text.strip(): return
        log(f"[Main] User query received: {text}")
        watchdog_time = (self.config.sovits_timeout + 10) * 1000
        self._busy_watchdog.start(watchdog_time)
        self.main_window.start_thinking()
        asyncio.run_coroutine_threadsafe(self._query_llm(text), self._loop)
    async def _query_llm(self, text: str):
        get_llm_logger()
        
        try:
            response = await self.llm_backend.query(text)
            self.llm_response_ready.emit(response)
        except Exception as e:
            log(f"[Main] LLM query failed: {e}")
            from resona_desktop_pet.backend.llm_backend import LLMResponse
            self.llm_response_ready.emit(LLMResponse(error=str(e)))

    def _handle_llm_response(self, response):
        self._last_llm_response = response
        log(f"[Main] LLM response returned. Error={response.error}")
        if response.error:
            self._show_error_response("llm_generic_error", response.error)
            return
        self._current_text = response.text_display
        self._current_emotion = response.emotion
        tts_lang_for_trigger = getattr(response, 'tts_lang', None)
        self._trigger_voice_response(response.text_display, response.emotion, None, tts_text=response.text_tts, tts_lang=tts_lang_for_trigger)
    def _handle_tts_ready(self, result):
        log(f"[Main] TTS synthesized ready. Success={not result.error}")
        if self._drop_tts_results or self._pack_switch_pending:
            log("[Main] Dropping TTS result due to pack switch.")
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
            log("[Main] Audio playback finished.")
            self._mark_tts_activity()
            self.main_window.set_speaking(False)
            self.main_window.on_audio_complete()
            self._busy_watchdog.stop()
        except OverflowError as e:
            log(f"[Main] OverflowError in _on_audio_finished: {e}")
            self._is_chain_executing = False
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
                log(f"[Main] Direct path not found: {v_path}. Searching for '{search_name}' in {pack_audio_path}...")
                matches = list(pack_audio_path.rglob(search_name))
                if matches:
                    v_path = matches[0]
                    log(f"[Main] Found match via recursive search: {v_path}")
        
        if v_path and v_path.exists():
            log(f"[Main] Playing pre-recorded: {v_path}")
            self.main_window.set_speaking(True)
            self.main_window.show_response(text, emotion)
            self._mark_tts_activity()
            self.audio_player.play(str(v_path))
        elif self.config.sovits_enabled and not is_behavior:
            log("[Main] Handing over to SoVITS synthesis chain.")
            self.main_window.set_speaking(True)
            self._mark_tts_activity()
            asyncio.run_coroutine_threadsafe(self._generate_tts(tts_text or text, emotion, language=tts_lang), self._loop)
        else:
            log("[Main] No audio source available, showing text response with timeout.")
            self.main_window.show_behavior_response_with_timeout(text, emotion)
    async def _generate_tts(self, text: str, emotion: str, language: Optional[str] = None):
        get_sovits_logger()
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
            log("[Main] Executing pending trigger from queue.")
            trigger = self._pending_triggers.pop(0)
            self._trigger_cooldown_end = now + self.config.trigger_cooldown
            self._execute_actions_chain(trigger)
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
                    log(f"[Main] Delay action 参数错误: {action.get('sec')}, 错误: {e}")

                    execute_next()
                return

            if action.get("type") == "speak":
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
            log("[Main] Exit action triggered.")
            self.force_exit()
        else:
            if self.config.plugins_enabled:
                pm = self.config.pack_manager
                if atype in pm.plugin_action_map:
                    pid = pm.plugin_action_map[atype]
                    module = pm.loaded_plugins.get(pid)
                    if module:
                        log(f"[Main] Forwarding action '{atype}' to plugin '{pid}'")
                        params = action.get("params", [])
                        threading.Thread(target=module.execute_action, args=(atype, params), daemon=True).start()
    def _handle_pack_change(self, pack_id: str):
        log(f"[PackSwitch] Start: requested={pack_id} current_active={self.config.pack_manager.active_pack_id} project_root={self.project_root}")
        self._cancel_action_chain()
        self.main_window.hide()
        if hasattr(self, "timer_scheduler"):
            self.timer_scheduler.reset()
        
        self.config.pack_manager.set_active_pack(pack_id)
        self.config.pack_manager.load_plugins(self.config.plugins_enabled)
        
        if hasattr(self, 'llm_backend'):
            log(f"[PackSwitch] Clearing conversation history for new pack: {pack_id}")
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
        log(f"[PackSwitch] Pack data: active_pack_id={self.config.pack_manager.active_pack_id} name={new_name} default_outfit={new_outfit} prompt_rel={raw_prompt_rel}")
        
        self.config.set("General", "active_pack", pack_id)
        self.config.set("General", "CharacterName", new_name)
        self.config.set("General", "default_outfit", new_outfit)
        self.config.set("Prompt", "file_path", Path(raw_prompt_rel).name)
        
        self.config.save()
        self.config.load()
        if not self.config.sovits_enabled:
            try:
                log(f"[PackSwitch] Pre-refresh config: active_pack={self.config.get('General','active_pack','')} default_outfit={self.config.default_outfit}")
                self.main_window.refresh_from_config()
                self.main_window.manual_show()
            except Exception as e:
                print(f"[PackSwitch] ERROR during pre-refresh: {e}")
                traceback.print_exc()
        else:
            log("[PackSwitch] Deferring UI refresh until SoVITS ready")
        
        log("[PackSwitch] Reloading backends")
        self.tts_backend.reload_config()
        self.llm_backend.history.clear()
        self.behavior_monitor.load_triggers()

        self._pack_switch_pending = True
        self._pack_switch_deadline = time.time() + 75
        if not self._pack_switch_wait_timer.isActive():
            self._pack_switch_wait_timer.start()
        log(f"[PackSwitch] Wait start: pending={self._pack_switch_pending} deadline={self._pack_switch_deadline} sovits_enabled={self.config.sovits_enabled}")

        if self.config.sovits_enabled:
            def wait_for_sovits_then_show():
                if self.sovits_manager.is_running():
                    print("[PackSwitch] SoVITS is already running, skipping restart.")
                    self.tts_backend.reload_config()
                    self.pack_switch_ready.emit()
                    return

                print("[PackSwitch] Starting SoVITS and waiting for API...")
                try:
                    success = self.sovits_manager.start(timeout=60, kill_existing=True)
                    print(f"[PackSwitch] SoVITS start finished. Success={success}")
                    self.pack_switch_ready.emit()
                except Exception as e:
                    print(f"[PackSwitch] CRITICAL ERROR in wait_for_sovits_then_show: {e}")
                    traceback.print_exc()
                    self.pack_switch_ready.emit()
            
            thread = threading.Thread(target=wait_for_sovits_then_show, daemon=True)
            print(f"[PackSwitch] Starting background thread: {thread.name}")
            thread.start()
        else:
            print("[PackSwitch] SoVITS disabled, emitting signal directly.")
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
        print("[PackSwitch] Finalizing UI refresh (triggered by signal)...")
        try:
            if self._pack_switch_wait_timer.isActive():
                self._pack_switch_wait_timer.stop()
            self._pack_switch_pending = False
            self._drop_tts_results = False
            self.config.load()
            if hasattr(self, "timer_scheduler"):
                self.timer_scheduler.refresh_config()
            print(f"[PackSwitch] Finalize config: active_pack={self.config.get('General','active_pack','')} default_outfit={self.config.default_outfit}")
            self.main_window.refresh_from_config()
            
            if hasattr(self, 'tray_icon'):
                self.tray_icon.hide()
                self.tray_icon.show()
                
            self.main_window.manual_show()
            print("[PackSwitch] Pack switch UI refresh complete.")
        except Exception as e:
            print(f"[PackSwitch] ERROR during UI finalize: {e}")
            traceback.print_exc()
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
        log("[Main] Replaying last response...")
        self.main_window.start_thinking()
        self._handle_llm_response(self._last_llm_response)
    def _handle_stt_request(self):
        if not self._stt_ready: return
        if self.stt_backend.is_recording():
            self.stt_backend.stop_recording()
            return
        log("[STT] Recording started...")
        self.main_window.set_input_locked(True)
        self.main_window.set_listening(True, username=self.config.username)
        asyncio.run_coroutine_threadsafe(self.stt_backend.start_recording(on_complete=lambda r: self.stt_result_ready.emit(r)), self._loop)
    def _handle_stt_result(self, result):
        if result.error:
            log(f"[STT] Error: {result.error}")
        log(f"[STT] Result: '{result.text}'")
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
        log(f"[Main] Startup events check. Weather enabled: {enabled}")
        if enabled:
            asyncio.run_coroutine_threadsafe(self._check_weather(), self._loop)
    async def _check_weather(self):
        import aiohttp
        log("[Weather] Starting weather service (Geo-locating via IP)...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://ip-api.com/json/") as r:
                    data = await r.json()
                    city = data.get("city")
                    if not city:
                        log(f"[Weather] Location failed: {data.get('message', 'Unknown error')}")
                        return
                log(f"[Weather] Located city: {city}. Fetching weather data...")
                url = f"http://api.weatherapi.com/v1/current.json?key={self.config.weather_api_key}&q={city}&lang=zh"
                async with session.get(url) as r:
                    if r.status == 200:
                        d = await r.json()
                        self.current_weather = {
                            "condition": d["current"]["condition"]["text"],
                            "temp": d["current"]["temp_c"]
                        }
                        log(f"[Weather] SUCCESS: {self.current_weather['condition']}, {self.current_weather['temp']}°C")
                    else:
                        log(f"[Weather] API error: Status {r.status}")
        except Exception as e:
            log(f"[Weather] Service error: {e}")
    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
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
        log("[Main] Config updated via settings dialog.")
        self.config.load()
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
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False
def run_as_admin():
    args = sys.argv[:]
    if "--log-file" not in args:
        args.extend(["--log-file", str(log_file)])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(args), str(project_root), 1)

def main():
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--log-file", type=str, default=None)
    args, unknown = parser.parse_known_args()

    global log_file, sovits_log_file, llm_log_file
    if args.log_file:
        log_file = Path(args.log_file)
        ts_part = log_file.stem.replace("app_", "")
        sovits_log_file = log_dir / f"sovits_{ts_part}.log"
        llm_log_file = log_dir / f"llm_{ts_part}.log"
        
    if not isinstance(sys.stdout, TeeLogger):
        sys.stdout = TeeLogger(log_file, sys.stdout)
        sys.stderr = sys.stdout
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', handlers=[logging.StreamHandler(sys.stdout)], force=True)

    config = ConfigManager(str(project_root / "config.cfg"))
    needs_admin = False
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
    if needs_admin and sys.platform == 'win32' and not is_admin():
        run_as_admin()
        sys.exit()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    controller = ApplicationController(sovits_log_path=sovits_log_file)
    app.aboutToQuit.connect(controller.cleanup)
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
