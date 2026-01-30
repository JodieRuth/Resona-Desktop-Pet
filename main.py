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
from resona_desktop_pet.backend import LLMBackend, TTSBackend, STTBackend
from resona_desktop_pet.backend.sovits_manager import SoVITSManager
from resona_desktop_pet.ui.luna.main_window import MainWindow
from resona_desktop_pet.ui.tray_icon import TrayIcon
from resona_desktop_pet.cleanup_manager import cleanup_manager
from resona_desktop_pet.behavior_monitor import BehaviorMonitor
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
log_file = log_dir / f"app_{timestamp}.log"
sovits_log_file = log_dir / f"sovits_{timestamp}.log"
llm_log_file = log_dir / f"llm_{timestamp}.log"
import logging
def setup_dedicated_logger(name, file_path, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.FileHandler(file_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
    logger.addHandler(handler)
    logger.propagate = False 
    return logger
def exception_hook(exctype, value, tb):
    traceback.print_exception(exctype, value, tb)
    logging.error("Uncaught exception:", exc_info=(exctype, value, tb))
    sys.exit(1)
sys.excepthook = exception_hook
sovits_logger = setup_dedicated_logger("SoVITS", sovits_log_file)
llm_logger = setup_dedicated_logger("LLM", llm_log_file)
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
sys.stdout = TeeLogger(log_file, sys.stdout)
sys.stderr = sys.stdout
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', handlers=[logging.StreamHandler(sys.stdout)], force=True)
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
class ApplicationController(QObject):
    llm_response_ready = Signal(object)
    tts_ready = Signal(object)
    stt_result_ready = Signal(object)
    request_stt_start = Signal()
    request_global_show = Signal()
    def __init__(self, sovits_log_path: Optional[Path] = None):
        super().__init__()
        self.config = ConfigManager()
        self.config.print_all_configs()
        pm = self.config.pack_manager
        log(f"[Debug] PackManager Active ID: {pm.active_pack_id}")
        log(f"[Debug] PackManager Data Loaded: {bool(pm.pack_data)}")
        if pm.pack_data:
            log(f"[Debug] Character Name from Pack: {pm.get_info('character', {}).get('name')}")
        else:
            log("[Debug] CRITICAL: Pack data is empty! Check pack.json path and ID.")
        self.project_root = Path(self.config.config_path).parent
        self._cleanup_temp_dir()



        self.gpu_vendor = "Unknown"
        self.can_monitor_gpu = True
        try:
            import subprocess
            raw_out = subprocess.check_output("wmic path win32_VideoController get name", shell=True, stderr=subprocess.STDOUT)
            try:
                output = raw_out.decode("utf-8")
            except UnicodeDecodeError:
                output = raw_out.decode("gbk", errors="ignore")
            
            output_up = output.upper()
            if "AMD" in output_up or "RADEON" in output_up:
                self.gpu_vendor = "AMD"
                self.can_monitor_gpu = False
                log("[Main] AMD GPU detected. Disabling GPU monitoring features to prevent crashes.")
            elif "NVIDIA" in output_up:
                self.gpu_vendor = "NVIDIA"
                log("[Main] NVIDIA GPU detected. GPU monitoring enabled.")
        except Exception as e:
            log(f"[Main] GPU detection skipped or failed: {e}")

        self._stt_ready = False
        self._last_llm_response = None
        self._trigger_cooldown_end = 0
        self._post_busy_cooldown_end = 0
        self._last_busy_state = False
        self._pending_triggers = []
        self._is_chain_executing = False 
        self.current_weather = {} 
        self.interaction_locked = False
        self.state = self._load_state()
        if self.config.sovits_enabled:
            self.sovits_manager = SoVITSManager(
                self.project_root,
                self.config.sovits_api_port,
                self.config.sovits_device,
                self.config.sovits_model_version
            )
            if not self.sovits_manager.start(timeout=60, kill_existing=self.config.sovits_kill_existing):
                QMessageBox.critical(None, "SoVITS Error", "无法启动 GPT-SoVITS 服务，请检查配置。")
                sys.exit(1)
        self.llm_backend = LLMBackend(self.config, log_path=llm_log_file)
        self.tts_backend = TTSBackend(self.config, sovits_log_path=sovits_log_path)
        self.stt_backend = STTBackend(self.config)
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        self.audio_player = AudioPlayer(self)
        self.audio_player.playback_finished.connect(self._on_audio_finished)
        self.main_window = MainWindow(self.config)
        self.main_window.controller = self 
        
        self.tray_icon = TrayIcon(self.main_window)
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
        self.behavior_monitor.start()
        self._mocker_process = None
        if self.config.debug_trigger:
            import subprocess
            mocker_script = self.project_root / "tools" / "sensor_mocker.py"
            log(f"[Debug] debugtrigger is ENABLED. Starting sensor mocker: {mocker_script}")
            self._mocker_process = subprocess.Popen([sys.executable, str(mocker_script)], cwd=str(self.project_root))
        self.main_window.pack_changed.connect(self._handle_pack_change)
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
    def _handle_user_query(self, text: str):
        if not text.strip(): return
        log(f"[Main] User query received: {text}")
        watchdog_time = (self.config.sovits_timeout + 10) * 1000
        self._busy_watchdog.start(watchdog_time)
        self.main_window.start_thinking()
        asyncio.run_coroutine_threadsafe(self._query_llm(text), self._loop)
    async def _query_llm(self, text: str):
        response = await self.llm_backend.query(text)
        self.llm_response_ready.emit(response)
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
        self.main_window.show_response(self._current_text, self._current_emotion)
        if result.error:
            self._show_error_response("sovits_timeout_error", result.error)
            return
        if result.audio_path:
            self.audio_player.play(result.audio_path)
        else:
            QTimer.singleShot(2000, self.main_window.finish_processing)
    def _on_audio_finished(self):
        log("[Main] Audio playback finished.")
        self.main_window.set_speaking(False)
        self.main_window.on_audio_complete()
        self._busy_watchdog.stop()
    def _trigger_voice_response(self, text, emotion, voice_file=None, is_behavior=False, tts_text=None, tts_lang=None):
        v_path = None
        if voice_file:
            pack_audio_path = self.config.pack_manager.get_path("audio", "event_dir")
            v_path = (pack_audio_path / voice_file) if pack_audio_path else Path(voice_file)
        if v_path and v_path.exists():
            log(f"[Main] Playing pre-recorded: {v_path}")
            self.main_window.set_speaking(True)
            self.main_window.show_response(text, emotion)
            self.audio_player.play(str(v_path))
        elif self.config.sovits_enabled and not is_behavior:
            log("[Main] Handing over to SoVITS synthesis chain.")
            self.main_window.set_speaking(True)
            asyncio.run_coroutine_threadsafe(self._generate_tts(tts_text or text, emotion, language=tts_lang), self._loop)
        else:
            log("[Main] No audio source available, showing text response with timeout.")
            self.main_window.show_behavior_response_with_timeout(text, emotion)
    async def _generate_tts(self, text: str, emotion: str, language: Optional[str] = None):
        if not language and self.config.use_pack_settings:
            language = self.config.pack_manager.get_info("tts_language", "ja")
        
        result = await self.tts_backend.synthesize(text, emotion, language=language)
        self.tts_ready.emit(result)
    def _handle_behavior_trigger(self, actions: list):
        if not actions or self.main_window.manual_hidden: return
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
        if self._last_busy_state and not self.main_window.is_busy:
            self._post_busy_cooldown_end = now + self.config.post_busy_delay
        self._last_busy_state = self.main_window.is_busy
        if self._pending_triggers and not self.is_busy and now >= self._post_busy_cooldown_end and now >= self._trigger_cooldown_end:
            log("[Main] Executing pending trigger from queue.")
            trigger = self._pending_triggers.pop(0)
            self._trigger_cooldown_end = now + self.config.trigger_cooldown
            self._execute_actions_chain(trigger)
    def _execute_actions_chain(self, actions):
        self._is_chain_executing = True 
        self._current_sequence = actions
        self._current_sequence_idx = 0
        
        self._current_chain_callback = None
        
        def execute_next():
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
                QTimer.singleShot(int(action.get("sec", 1.0) * 1000), execute_next)
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
            if action.get("sec"): QTimer.singleShot(int(action.get("sec")*1000), lambda: mw.fade_to(1.0))
        elif atype == "lock_interaction":
            duration = action.get("sec", 0.0)
            if duration > 0:
                self.interaction_locked = True
                mw.set_hard_lock(True, highlight=True)
                QTimer.singleShot(int(duration * 1000), self._unlock_interaction)
        elif atype == "exit_app":
            log("[Main] Exit action triggered.")
            self.cleanup()
            QApplication.quit()
    def _handle_pack_change(self, pack_id: str):
        log(f"[Main] Switching pack to {pack_id}")
        self.main_window.hide()
        self.config.pack_manager.set_active_pack(pack_id)
        pdata = self.config.pack_manager.pack_data
        new_name = pdata.get("character", {}).get("name", "Unknown")
        new_outfit = pdata.get("character", {}).get("outfits", [{}])[0].get("id", "default")
        raw_prompt_rel = pdata.get("logic", {}).get("prompts", [{}])[0].get("path", "")
        self.config.set("General", "active_pack", pack_id)
        self.config.set("General", "CharacterName", new_name)
        self.config.set("General", "default_outfit", new_outfit)
        self.config.set("Prompt", "file_path", Path(raw_prompt_rel).name)
        self.config.save()
        if self.config.sovits_enabled:
            self.sovits_manager.stop()
            self.sovits_manager.start(timeout=60, kill_existing=True)
        self.behavior_monitor.load_triggers()
        self.main_window.load_thinking_texts()
        self.main_window.load_listening_texts()
        self.main_window.manual_show()
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
        from resona_desktop_pet.ui.simple_settings import SimpleSettingsDialog
        if SimpleSettingsDialog(self.config).exec():
            log("[Main] Config updated via settings dialog.")
            self.config.load()
            self.behavior_monitor.load_triggers()
    def cleanup(self):
        if self._mocker_process: self._mocker_process.terminate()
        if self.behavior_monitor: self.behavior_monitor.stop()
        if self.sovits_manager: self.sovits_manager.stop()
        self.stt_backend.cleanup()
        cleanup_manager.cleanup()
        self._loop.call_soon_threadsafe(self._loop.stop)
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
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), str(project_root), 1)
def main():
    config = ConfigManager()
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
