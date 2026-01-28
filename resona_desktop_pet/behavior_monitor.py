import json
import time
import random
import ctypes
import psutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
from PySide6.QtCore import QThread, Signal
class WindowInfo:
    def __init__(self, hwnd, pid, title, process_name, rect, url=None):
        self.hwnd = hwnd; self.pid = pid; self.title = title
        self.process_name = process_name.lower(); self.rect = rect; self.url = url
class BehaviorMonitor(QThread):
    fullscreen_status_changed = Signal(bool)
    trigger_matched = Signal(list) 
    def __init__(self, config_manager, controller):
        super().__init__()
        self.config = config_manager
        self.controller = controller
        self.project_root = Path(config_manager.config_path).parent
        self.running = True
        self.triggers = []
        self.app_start_time = time.time()
        self.global_history = {} 
        self.trigger_counts = {} 
        self.pid_history = {}
        self.triggered_pids = set() 
        self.rule_hit_states = {}   
        self.last_cycle_idle = 0.0
        self.is_fullscreen = False
        self.is_first_run = True
        self.last_clip_text = self._get_clipboard()
        self.last_music_title = "" 
        self.load_triggers()
    def load_triggers(self):
        trigger_path = self.config.pack_manager.get_path("logic", "triggers")
        if trigger_path and trigger_path.exists():
            try:
                with open(trigger_path, "r", encoding="utf-8") as f:
                    self.triggers = json.load(f)
                logging.info(f"[Behavior] Loaded {len(self.triggers)} triggers from pack.")
            except Exception as e:
                logging.error(f"[Behavior] Load failed: {e}")
    def stop(self):
        self.running = False
    def run(self):
        while self.running:
            try:
                if self.config.behavior_enabled:
                    self._perform_checks(is_startup=self.is_first_run)
                    self.is_first_run = False
            except Exception as e:
                logging.error(f"[Behavior] Loop error: {e}")
            time.sleep(self.config.behavior_interval)
    def _perform_checks(self, is_startup=False):
        now = time.time()
        if self.config.getboolean("General", "debugtrigger", fallback=False):
            mock_path = self.project_root / "TEMP" / "mock_data.json"
            if mock_path.exists():
                try:
                    with open(mock_path, "r", encoding="utf-8") as f:
                        m = json.load(f)
                    hw_stats = {"cpu_temp": m.get("cpu_temp"), "gpu_temp": m.get("gpu_temp"), "cpu_usage": m.get("cpu_usage"), "gpu_usage": m.get("gpu_usage")}
                    win_info = WindowInfo(0, 0, m.get("win_title"), m.get("win_pname"), (0,0,0,0), m.get("win_url"))
                    clip_text = m.get("clip_text", "")
                    music_title = m.get("music_title", "")
                    self._process_rule_matching(now, win_info, float(m.get("idle_sec", 0)), hw_stats, clip_text, m.get("weather", {}), is_startup, m.get("date"), m.get("time"), music_title=music_title)
                    self.last_clip_text = clip_text
                    return 
                except: pass
        try:
            current_pids = {}
            for p in psutil.process_iter(['name', 'pid', 'create_time']):
                try:
                    pid = p.info['pid']; pn = p.info['name'].lower()
                    current_pids[pid] = pn
                    if pid not in self.pid_history:
                        self.pid_history[pid] = {"name": pn, "start_time": p.info['create_time']}
                except: continue
            self.active_processes = set(current_pids.values())
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            win_info = self._get_window_info(hwnd)
            idle_time = self._get_idle_time()
            hw_stats = self._get_hardware_stats()
            curr_clip = self._get_clipboard()
            clip_changed_text = curr_clip if curr_clip != self.last_clip_text else ""
            curr_music = self._get_cloudmusic_title()
            music_changed_text = curr_music if curr_music != self.last_music_title else ""
            weather = getattr(self.controller, "current_weather", {})
            if win_info:
                fs = self._is_fullscreen(win_info)
                if fs != self.is_fullscreen:
                    self.is_fullscreen = fs
                    self.fullscreen_status_changed.emit(fs)
            self._process_rule_matching(now, win_info, idle_time, hw_stats, curr_clip, weather, is_startup, 
                                      clip_changed=clip_changed_text, music_title=curr_music, music_changed=music_changed_text)
            self.last_cycle_idle = idle_time
            self.last_clip_text = curr_clip
            self.last_music_title = curr_music
        except Exception as e:
            logging.error(f"[Behavior] Check failed: {e}")
    def _process_rule_matching(self, now, win, idle, hw, clip, weather, is_startup, m_date=None, m_time=None, clip_changed="", music_title="", music_changed=""):
        is_debug = self.config.getboolean("General", "debugtrigger", fallback=False)
        is_recovering = (idle < 1.0 and self.last_cycle_idle > 1.0)
        recovery_duration = self.last_cycle_idle if is_recovering else 0.0
        for rule in self.triggers:
            if not rule.get("enabled", True): continue
            if rule.get("startup_only") and not is_startup: continue
            rule_id = str(rule.get("id", "default"))
            gid = rule.get("trigger_group_id", rule_id)
            if not is_debug:
                if now - self.global_history.get(gid, 0) < rule.get("cooldown", 5): continue
                if self.trigger_counts.get(gid, 0) >= rule.get("max_triggers", 9999): continue
                if now - getattr(self, "_last_any_trigger_time", 0) < self.config.trigger_cooldown: continue
            ui = getattr(self.controller.main_window, "stats", {})
            matched = self._check_recursive_logic(rule, win, idle, recovery_duration, hw, ui, clip, weather, rule_id, m_date, m_time, clip_changed, music_title, music_changed)
            if matched:
                if not is_debug and random.random() > rule.get("probability", 1.0): continue
                logging.info(f"[Behavior] Trigger Matched: {rule_id}")
                self.global_history[gid] = now
                self._last_any_trigger_time = now
                self.trigger_counts[gid] = self.trigger_counts.get(gid, 0) + 1
                self.trigger_matched.emit(rule.get("actions", []))
                break 
    def _check_recursive_logic(self, node, win, idle, recovery, hw, ui, clip, weather, rid, m_date, m_time, clip_changed, music_title, music_changed, path="root") -> bool:
        logic = node.get("logic", "AND").upper()
        conds = node.get("conditions", [])
        if not conds: return False
        results = []
        for i, c in enumerate(conds):
            c_path = f"{path}_{i}"
            if "logic" in c:
                res = self._check_recursive_logic(c, win, idle, recovery, hw, ui, clip, weather, rid, m_date, m_time, clip_changed, music_title, music_changed, c_path)
            else:
                res, _ = self._test_single_condition_v6(c, win, idle, recovery, hw, ui, clip, weather, m_date, m_time, clip_changed, music_title, music_changed)
            if logic == "CUMULATIVE":
                if res: self.rule_hit_states.setdefault(rid, {})[c_path] = True
                results.append(self.rule_hit_states.get(rid, {}).get(c_path, False))
            else:
                results.append(res)
        if logic == "AND": return all(results)
        if logic == "OR": return any(results)
        if logic == "CUMULATIVE": return all(results)
        return False
    def _test_single_condition_v6(self, c, win, idle, recovery, hw, ui, clip, weather, m_date, m_time, clip_changed, music_title, music_changed):
        t = c.get("type")
        res, pids = False, []
        if t == "cpu_temp": res = hw["cpu_temp"] > c.get("gt", 0)
        elif t == "gpu_temp": res = hw["gpu_temp"] > c.get("gt", 0)
        elif t == "cpu_usage": res = hw["cpu_usage"] > c.get("gt", 0)
        elif t == "gpu_usage": res = hw["gpu_usage"] > c.get("gt", 0)
        elif t in ["process_active", "process_background"]:
            wl = [p.lower() for p in c.get("pnames", [c.get("pname", "")]) if p]
            targets = [win.pid] if (t == "process_active" and win and win.process_name in wl) else []
            if t == "process_background":
                targets = [pid for pid, info in self.pid_history.items() if info["name"] in wl]
            if c.get("only_new") and not m_date:
                targets = [p for p in targets if self.pid_history[p]["start_time"] > self.app_start_time]
            if targets: res, pids = True, targets
        elif t == "clip_match":
            target_text = clip_changed if not m_date else clip 
            res = any(kw.lower() in target_text.lower() for kw in c.get("keywords", [])) if target_text else False
        elif t == "music_match":
            target_text = music_changed if c.get("only_on_change", True) and not m_date else music_title
            res = any(kw.lower() in target_text.lower() for kw in c.get("keywords", [])) if target_text else False
        elif t == "url_match": res = any(kw.lower() in (win.url or "").lower() for kw in c.get("keywords", [])) if win else False
        elif t == "title_match": res = any(kw.lower() in win.title.lower() for kw in c.get("keywords", [])) if win else False
        elif t == "weather_match": res = any(kw in (weather.get("condition", "") if weather else "") for kw in c.get("keywords", []))
        elif t == "hover_duration": res = ui.get("is_hovering") and (time.time() - ui.get("hover_start_time", 0)) > c.get("sec", 0)
        elif t == "leave_duration": res = not ui.get("is_hovering") and (time.time() - ui.get("hover_leave_time", 0)) > c.get("sec", 0)
        elif t == "long_press": res = ui.get("is_pressing") and (time.time() - ui.get("press_start_time", 0)) > c.get("sec", 0)
        elif t == "click_count":
            recent = [x for x in ui.get("last_click_times", []) if (time.time() - x) < c.get("duration", 5)]
            res = len(recent) >= c.get("count", 1)
        elif t == "idle_recovery": res = recovery > c.get("sec", 0)
        elif t == "idle_duration": res = idle > c.get("sec", 0)
        elif t == "fullscreen": res = self.is_fullscreen
        elif t == "date_match":
            d = m_date if m_date else datetime.now().strftime("%m-%d")
            res = d == c.get("date", "")
        elif t == "time_range":
            try:
                curr_t = m_time if m_time else datetime.now().strftime("%H:%M")
                now_t = datetime.strptime(curr_t, "%H:%M").time()
                s, e = c.get("range", "").split("-")
                res = datetime.strptime(s, "%H:%M").time() <= now_t <= datetime.strptime(e, "%H:%M").time()
            except: res = False
        return res, pids
    def _get_idle_time(self):
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = LASTINPUTINFO(); lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
        return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) / 1000.0
    def _get_window_info(self, hwnd) -> Optional[WindowInfo]:
        if not hwnd: return None
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            p = psutil.Process(pid.value); pname = p.name().lower()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
            rect = ctypes.wintypes.RECT(); ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
            url = None
            if self.config.use_ui_automation and pname in ["chrome.exe", "msedge.exe"]:
                try:
                    import uiautomation as auto
                    ctrl = auto.ControlFromHandle(hwnd)
                    edit = ctrl.EditControl(Name="地址和搜索栏") or ctrl.EditControl(Name="Address and search bar")
                    if edit: url = edit.GetValuePattern().Value
                except: pass
            return WindowInfo(hwnd, pid.value, buff.value, pname, (rect.left, rect.top, rect.right, rect.bottom), url)
        except: return None
    def _get_hardware_stats(self):
        stats = {"cpu_temp": 0.0, "gpu_temp": 0.0, "cpu_usage": 0.0, "gpu_usage": 0.0}
        try:
            stats["cpu_usage"] = psutil.cpu_percent()
            if hasattr(psutil, "sensors_temperatures"):
                t = psutil.sensors_temperatures()
                if 'coretemp' in t: stats["cpu_temp"] = t['coretemp'][0].current
        except: pass

        if not getattr(self.controller, "can_monitor_gpu", True):
            return stats

        try:
            import pynvml
            pynvml.nvmlInit()
            h = pynvml.nvmlDeviceGetHandleByIndex(0)
            stats["gpu_temp"] = pynvml.nvmlDeviceGetTemperature(h, 0)
            stats["gpu_usage"] = pynvml.nvmlDeviceGetUtilizationRates(h).gpu
            pynvml.nvmlShutdown()
        except:
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    stats["gpu_temp"] = gpus[0].temperature
                    stats["gpu_usage"] = gpus[0].load * 100
            except: pass
        return stats
    def _get_clipboard(self):
        if not self.config.monitor_clipboard: return ""
        try:
            import pyperclip
            return pyperclip.paste() or ""
        except: return ""
    def _is_fullscreen(self, info: WindowInfo) -> bool:
        sw = ctypes.windll.user32.GetSystemMetrics(0); sh = ctypes.windll.user32.GetSystemMetrics(1)
        ww, wh = info.rect[2]-info.rect[0], info.rect[3]-info.rect[1]
        return (ww >= sw and wh >= sh) if info.process_name not in ["explorer.exe", "taskbar"] else False
    def _get_cloudmusic_title(self) -> str:
        if not self.config.monitor_music: return ""
        title = ""
        def callback(hwnd, _):
            nonlocal title
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                p = psutil.Process(pid.value)
                if p.name().lower() == "cloudmusic.exe":
                    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                        t = buff.value
                        if t and " - " in t:
                            title = t
                            return False 
            except: pass
            return True
        EnumWindows = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
        ctypes.windll.user32.EnumWindows(EnumWindows(callback), 0)
        return title
