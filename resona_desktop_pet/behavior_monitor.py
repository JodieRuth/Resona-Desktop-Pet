import json
import time
import random
import ctypes
import psutil
import logging
import ctypes.wintypes
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
        self._last_mock_data = {}
        self.plugin_status_cache = {}
        self.dropped_file_cache = None  
        self.load_triggers()

    def on_file_dropped(self, file_info: dict):
        """处理UI层发出的文件拖入信号"""
        self.dropped_file_cache = file_info
        logging.info(f"[Behavior] 文件拖入: name={file_info.get('name')}, ext={file_info.get('ext')}")

    def _poll_plugins(self):
        pm = self.config.pack_manager
        if not self.config.plugins_enabled:
            self.plugin_status_cache = {}
            return

        if not hasattr(pm, 'loaded_plugins'):
            return

        current_time = time.time()
        if not hasattr(self, '_last_plugin_log_time'):
            self._last_plugin_log_time = 0

        for pid, module in pm.loaded_plugins.items():
            try:
                if hasattr(module, "check_status"):
                    result = module.check_status()
                    self.plugin_status_cache[pid] = result

                    prev_status = getattr(self, '_prev_plugin_status', {}).get(pid)
                    if prev_status != result or (current_time - self._last_plugin_log_time) > 60:
                        if result[0]:
                            logging.info(f"[Behavior] 插件状态: {pid} = {result[1]}")
                        self._prev_plugin_status = {**getattr(self, '_prev_plugin_status', {}), pid: result}
                        self._last_plugin_log_time = current_time
            except Exception as e:
                logging.error(f"[Behavior] Plugin {pid} check failed: {e}")
                self.plugin_status_cache[pid] = (False, "error", 0.0)

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
        self._poll_plugins()

        if self.config.debug_trigger:
            mock_path = self.project_root / "TEMP" / "mock_data.json"
            if mock_path.exists():
                try:
                    with open(mock_path, "r", encoding="utf-8") as f:
                        m = json.load(f)

                    if m == self._last_mock_data:
                        logging.debug("[Behavior] Mock 数据无变化，跳过检查")
                        return

                    is_fs = m.get("is_fullscreen", False)
                    if is_fs != self.is_fullscreen:
                        self.is_fullscreen = is_fs
                        self.fullscreen_status_changed.emit(is_fs)

                    current_pids = {}
                    for p in psutil.process_iter(['name', 'pid', 'create_time']):
                        try:
                            pid = p.info['pid']; pn = p.info['name'].lower()
                            current_pids[pid] = pn
                            if pid not in self.pid_history:
                                self.pid_history[pid] = {"name": pn, "start_time": p.info['create_time']}
                        except: continue
                    self.active_processes = set(current_pids.values())

                    clip_text = m.get("clip_text", "")
                    clip_changed_text = clip_text if clip_text != self._last_mock_data.get("clip_text") else ""

                    curr_music = m.get("music_title", "")
                    music_changed_text = curr_music if curr_music != self._last_mock_data.get("music_title") else ""

                    self._last_mock_data = m.copy()

                    hw_stats = {"cpu_temp": m.get("cpu_temp"), "gpu_temp": m.get("gpu_temp"), "cpu_usage": m.get("cpu_usage"), "gpu_usage": m.get("gpu_usage")}
                    win_info = WindowInfo(0, 0, m.get("win_title"), m.get("win_pname"), (0,0,0,0), m.get("win_url"))

                    logging.debug(f"[Behavior] 使用 mock 数据检查: plugins={m.get('plugins', {})}")
                    
                    mock_uptime = m.get("process_uptime")
                    mock_battery = m.get("battery", {})
                    mock_file_drop = m.get("file_drop", {})
                    
                    self._process_rule_matching(now, win_info, float(m.get("idle_sec", 0)), hw_stats, clip_text, m.get("weather", {}), is_startup, m.get("date"), m.get("time"),
                                              clip_changed=clip_changed_text, music_title=curr_music, music_changed=music_changed_text,
                                              mock_uptime=mock_uptime, mock_battery=mock_battery, mock_file_drop=mock_file_drop)
                    self.last_clip_text = clip_text

                    if "plugins" in m:
                        for pid, vals in m["plugins"].items():
                            self.plugin_status_cache[pid] = tuple(vals)
                            logging.debug(f"[Behavior] Mock 插件状态: {pid} = {vals}")
                    return
                except Exception as e:
                    logging.error(f"[Behavior] Mock 数据读取失败: {e}")

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
    def _process_rule_matching(self, now, win, idle, hw, clip, weather, is_startup, m_date=None, m_time=None, clip_changed="", music_title="", music_changed="", mock_uptime=None, mock_battery=None, mock_file_drop=None):
        is_debug = self.config.debug_trigger
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
            matched = self._check_recursive_logic(rule, win, idle, recovery_duration, hw, ui, clip, weather, rule_id, m_date, m_time, clip_changed, music_title, music_changed, mock_uptime=mock_uptime, mock_battery=mock_battery, mock_file_drop=mock_file_drop)
            if matched:
                if not is_debug and random.random() > rule.get("probability", 1.0): continue
                logging.info(f"[Behavior] Trigger Matched: {rule_id}")
                self.global_history[gid] = now
                self._last_any_trigger_time = now
                self.trigger_counts[gid] = self.trigger_counts.get(gid, 0) + 1
                self.trigger_matched.emit(rule.get("actions", []))
                break
    def _check_recursive_logic(self, node, win, idle, recovery, hw, ui, clip, weather, rid, m_date, m_time, clip_changed, music_title, music_changed, mock_uptime=None, mock_battery=None, mock_file_drop=None, path="root") -> bool:
        logic = node.get("logic", "AND").upper()
        conds = node.get("conditions", [])
        if not conds: return False
        results = []
        for i, c in enumerate(conds):
            c_path = f"{path}_{i}"
            if "logic" in c:
                res = self._check_recursive_logic(c, win, idle, recovery, hw, ui, clip, weather, rid, m_date, m_time, clip_changed, music_title, music_changed, mock_uptime=mock_uptime, mock_battery=mock_battery, mock_file_drop=mock_file_drop, c_path=c_path)
            else:
                res, _ = self._test_single_condition_v6(c, win, idle, recovery, hw, ui, clip, weather, m_date, m_time, clip_changed, music_title, music_changed, mock_uptime=mock_uptime, mock_battery=mock_battery, mock_file_drop=mock_file_drop)
            if logic == "CUMULATIVE":
                if res: self.rule_hit_states.setdefault(rid, {})[c_path] = True
                results.append(self.rule_hit_states.get(rid, {}).get(c_path, False))
            else:
                results.append(res)
        if logic == "AND": return all(results)
        if logic == "OR": return any(results)
        if logic == "CUMULATIVE": return all(results)
        return False
    def _test_single_condition_v6(self, c, win, idle, recovery, hw, ui, clip, weather, m_date, m_time, clip_changed, music_title, music_changed, mock_uptime=None, mock_battery=None, mock_file_drop=None):
        t = c.get("type")
        res, pids = False, []
        is_debug = mock_uptime is not None
        if t == "cpu_temp": res = hw["cpu_temp"] > c.get("gt", 0)
        elif t == "gpu_temp": res = hw["gpu_temp"] > c.get("gt", 0)
        elif t == "cpu_usage": res = hw["cpu_usage"] > c.get("gt", 0)
        elif t == "gpu_usage": res = hw["gpu_usage"] > c.get("gt", 0)
        elif t in ["process_active", "process_background"]:
            wl = [p.lower() for p in c.get("pnames", [c.get("pname", "")]) if p]
            in_mock = m_date is not None
            if t == "process_active":
                targets = [win.pid] if (win and win.process_name in wl) else []
            else:
                targets = [pid for pid, info in self.pid_history.items() if info["name"] in wl]
                if in_mock and win and win.process_name in wl:
                    if win.pid not in targets:
                        targets.append(win.pid)
            if c.get("only_new") and not in_mock:
                targets = [p for p in targets if self.pid_history[p]["start_time"] > self.app_start_time]
            if targets: res, pids = True, targets
        elif t == "clip_match":
            in_mock = m_date is not None
            target_text = clip_changed if not in_mock else clip
            res = any(kw.lower() in target_text.lower() for kw in c.get("keywords", [])) if target_text else False
        elif t == "music_match":
            in_mock = m_date is not None
            target_text = music_changed if (c.get("only_on_change", True) and not in_mock) else music_title
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
        elif t == "plugin_check" or (hasattr(self.config.pack_manager, 'plugin_trigger_map') and t in self.config.pack_manager.plugin_trigger_map):

            plugin_map = getattr(self.config.pack_manager, 'plugin_trigger_map', {})
            pid = c.get("plugin_id") or plugin_map.get(t)
            if pid in self.plugin_status_cache:
                status = self.plugin_status_cache[pid]
                res = True
                if t == "plugin_check":
                    if "expect_bool" in c:
                        res = res and (status[0] == c["expect_bool"])
                    if "match_text" in c:
                        res = res and (c["match_text"].lower() in status[1].lower())
                    if "gt_value" in c:
                        res = res and (status[2] > c["gt_value"])
                    if "lt_value" in c:
                        res = res and (status[2] < c["lt_value"])
                else:

                    res = status[0]
                if res:
                    logging.info(f"[Behavior] 插件触发: {t} -> {pid}, status={status}")
            else:
                res = False
        elif t == "is_machine_explosion":

            plugin_map = getattr(self.config.pack_manager, 'plugin_trigger_map', {})
            pid = plugin_map.get(t)
            if pid in self.plugin_status_cache:
                status = self.plugin_status_cache[pid]
                res = status[0]
                if res:
                    logging.info(f"[Behavior] 检测到机器爆炸: {status}")
            else:
                res = False
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
        elif t == "process_uptime":
            pname = c.get("pname", "")
            if not pname.endswith(".exe"):
                pname = pname + ".exe"
            if is_debug and mock_uptime is not None:
                uptime = mock_uptime
                gt = c.get("gt", 0)
                lt = c.get("lt")
                if lt is not None:
                    res = gt < uptime < lt
                else:
                    res = uptime > gt
                if res and c.get("log", False):
                    logging.info(f"[Behavior] Mock进程存活: {pname} 已运行 {uptime}s")
            else:
                targets = [pid for pid, info in self.pid_history.items() if info["name"].lower() == pname.lower()]
                if targets:
                    uptime = time.time() - self.pid_history[targets[0]]["start_time"]
                    gt = c.get("gt", 0)
                    lt = c.get("lt")
                    if lt is not None:
                        res = gt < uptime < lt
                    else:
                        res = uptime > gt
                    if res and c.get("log", False):
                        logging.info(f"[Behavior] 进程存活: {pname} 已运行 {uptime:.1f}s")
                else:
                    res = False
        elif t == "battery_level":
            if is_debug and mock_battery:
                percent = mock_battery.get("level", 0)
                charging = mock_battery.get("charging", False)
                gt = c.get("gt")
                lt = c.get("lt")
                expect_charging = c.get("charging")
                if expect_charging is not None:
                    res = (charging == expect_charging) and (
                        (gt is not None and percent > gt) if gt is not None else True
                    ) and (
                        (lt is not None and percent < lt) if lt is not None else True
                    )
                else:
                    if gt is not None and lt is not None:
                        res = gt < percent < lt
                    elif gt is not None:
                        res = percent > gt
                    elif lt is not None:
                        res = percent < lt
                    else:
                        res = True
                if res and c.get("log", False):
                    logging.info(f"[Behavior] Mock电池: {percent}%, 充电中={charging}")
            else:
                try:
                    import psutil
                    battery = psutil.sensors_battery()
                    if battery is not None:
                        percent = battery.percent
                        gt = c.get("gt")
                        lt = c.get("lt")
                        charging = battery.power_plugged
                        if c.get("charging") is not None:
                            res = (charging == c["charging"]) and (
                                (gt is not None and percent > gt) if gt is not None else True
                            ) and (
                                (lt is not None and percent < lt) if lt is not None else True
                            )
                        else:
                            if gt is not None and lt is not None:
                                res = gt < percent < lt
                            elif gt is not None:
                                res = percent > gt
                            elif lt is not None:
                                res = percent < lt
                            else:
                                res = True
                        if res and c.get("log", False):
                            logging.info(f"[Behavior] 电池: {percent}%, 充电中={charging}")
                    else:
                        res = False
                except: res = False
        elif t == "file_drop":
            if is_debug and mock_file_drop:
                file_ext = mock_file_drop.get("ext", "")
                file_name = mock_file_drop.get("name", "")
                exts = [e.lower() for e in c.get("exts", [])]
                name_keywords = [k.lower() for k in c.get("name_keywords", [])]
                ext_match = not exts or file_ext in exts
                name_match = not name_keywords or any(kw in file_name.lower() for kw in name_keywords)
                res = ext_match and name_match
                if res and c.get("log", False):
                    logging.info(f"[Behavior] Mock文件拖入匹配: {file_name}")
            elif self.dropped_file_cache:
                file_ext = self.dropped_file_cache.get("ext", "")
                file_name = self.dropped_file_cache.get("name", "")
                exts = [e.lower() for e in c.get("exts", [])]
                name_keywords = [k.lower() for k in c.get("name_keywords", [])]
                ext_match = not exts or file_ext in exts
                name_match = not name_keywords or any(kw in file_name.lower() for kw in name_keywords)
                res = ext_match and name_match
                if res and c.get("log", False):
                    logging.info(f"[Behavior] 文件拖入匹配: {file_name}")
            else:
                res = False
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
        try:
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        except (OverflowError, ValueError) as e:
            logging.warning(f"[Behavior] GetWindowThreadProcessId 失败: {e}")
            return None
        try:
            p = psutil.Process(pid.value); pname = p.name().lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OverflowError) as e:
            logging.warning(f"[Behavior] Process 查询失败: {e}")
            return None
        try:
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
        try:
            if info.process_name in ["explorer.exe", "taskbar"]:
                return False
            
            hwnd = info.hwnd
            if not hwnd:
                return False
            
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            exstyle = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            
            if exstyle & WS_EX_TOOLWINDOW:
                return False
            
            monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)
            if not monitor:
                return False
            
            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint),
                           ("rcMonitor", ctypes.wintypes.RECT),
                           ("rcWork", ctypes.wintypes.RECT),
                           ("dwFlags", ctypes.c_uint)]
            
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(MONITORINFO)
            ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(mi))
            
            work_left = mi.rcWork.left
            work_top = mi.rcWork.top
            work_right = mi.rcWork.right
            work_bottom = mi.rcWork.bottom
            
            win_left = info.rect[0]
            win_top = info.rect[1]
            win_right = info.rect[2]
            win_bottom = info.rect[3]
            
            if (win_left == work_left and win_top == work_top and 
                win_right == work_right and win_bottom == work_bottom):
                return True
            
            return False
        except (OverflowError, ValueError, AttributeError):
            return False
    def _get_cloudmusic_title(self) -> str:
        if not self.config.monitor_music: return ""
        title = ""
        def callback(hwnd, _):
            nonlocal title
            pid = ctypes.c_ulong()
            try:
                ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            except (OverflowError, ValueError):
                return True
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
