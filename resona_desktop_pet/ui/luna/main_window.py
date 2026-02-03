import os
import sys
import json
import random
import time
import ctypes
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QPoint, QRect, QPropertyAnimation, QEasingCurve, QObject
from PySide6.QtGui import QMouseEvent, QWheelEvent, QPixmap, QCursor, QGuiApplication, QAction, QActionGroup, QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMenu, QGraphicsOpacityEffect, QApplication
from resona_desktop_pet.config import ConfigManager
from .character_view import CharacterView
from .io_overlay import IOOverlay

class MainWindow(QWidget):
    request_query = Signal(str)
    replay_requested = Signal()
    pack_changed = Signal(str)
    settings_requested = Signal()
    file_dropped = Signal(dict)  
    def __init__(self, config: ConfigManager, parent: QWidget = None):
        super().__init__(parent)
        self.config = config
        
        self.topmost_timer = QTimer(self)
        self.topmost_timer.setInterval(2500)
        self.topmost_timer.timeout.connect(self._reinforce_topmost)
        
        self.stats = {
            "hover_start_time": 0.0,
            "press_start_time": 0.0,
            "drag_start_time": 0.0,
            "last_click_times": [], 
            "total_clicks": 0,
            "is_hovering": False,
            "is_pressing": False
        }
        self.input_hard_locked = False
        self.faded = False
        self.manual_hidden = False
        self.fullscreen_hidden = False
        self.is_processing = False
        self.is_listening = False
        self.is_speaking = False
        self.is_displaying_text = False
        self.fade_hover_recovery_sec = 0.0
        self.project_root = Path(self.config.config_path).parent
        
        self.setObjectName("MainRoot")
        self.character = CharacterView(self)
        self.io = IOOverlay(self)
        self.io.set_names(self.config.username, self.config.character_name)
        self.io.raise_()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.character, 0, Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)

        self._apply_window_settings()

        self.character.setup(self.project_root, self.config.default_outfit)
        self.character.set_emotion("<E:smile>", deterministic=True)
        self.sync_window_to_sprite()
        img_rect = self.character.image_rect()
        if img_rect.width() > 0 and img_rect.height() > 0:
            target_w = self.config.sprite_width
            target_h = self.config.sprite_height
            scale_w = target_w / img_rect.width() if target_w > 0 else 999.0
            scale_h = target_h / img_rect.height() if target_h > 0 else 999.0
            initial_scale = min(scale_w, scale_h)
            if initial_scale == 999.0:
                initial_scale = 1.0
            self.character.set_scale(initial_scale)
            self.ui_scale = initial_scale
        else:
            self.ui_scale = 1.0
        self.character.setCursor(Qt.CursorShape.OpenHandCursor)
        self.installEventFilter(self)
        self.character.installEventFilter(self)
        self.io.installEventFilter(self)
        self.char_opacity = QGraphicsOpacityEffect(self.character)
        self.char_opacity.setOpacity(1.0)
        self.character.setGraphicsEffect(self.char_opacity)
        self.fade_anim = QPropertyAnimation(self.char_opacity, b"opacity", self)
        self.fade_anim.setDuration(220)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.setInterval(int(self.config.idle_fade_delay * 1000))
        self.idle_timer.timeout.connect(self.on_idle_timeout)
        self.faded = False
        self.fade_hover_recovery_sec = 0.0
        self.input_hard_locked = False
        self.dragging = False
        self.dragging_started = False
        self.drag_offset = QPoint()
        self.drag_mod = Qt.KeyboardModifier.NoModifier 
        self.thinking_texts = []
        self.load_thinking_texts()
        self.listening_texts = []
        self.load_listening_texts()
        self.thinking_timer = QTimer(self)
        self.thinking_timer.setSingleShot(True)
        self.thinking_timer.timeout.connect(self.show_thinking_text)
        self.thinking_switch_timer = QTimer(self)
        self.thinking_switch_timer.timeout.connect(self.switch_thinking_text)
        self.text_display_timer = QTimer(self)
        self.text_display_timer.setSingleShot(True)
        self.text_display_timer.timeout.connect(self.finish_processing)
        self.io.submitted.connect(self.on_query_submitted)
        self.io.text_changed.connect(self.on_input_text_changed)
        self.io.file_dropped.connect(self.on_file_dropped)
        self.character.rightClicked.connect(self.show_context_menu)
        
        QTimer.singleShot(0, self.sync_window_to_sprite)
        self.dialogue = self.DialogueAdapter(self)
        self.sprite = self.SpriteAdapter(self)

        self.setAcceptDrops(True)
        self.character.setAcceptDrops(True)
        self.io.setAcceptDrops(True)

    class DialogueAdapter:
        def __init__(self, window):
            self.window = window
            self.io = window.io
            self.input_field = self.io.edit 
        def set_text(self, text: str, animate: bool = False):
            if text == "Listening...":
                self.io.show_status(text)
            else:
                self.io.show_output(text) 
        def set_enabled(self, enabled: bool):
            if enabled:
                self.io.back_to_input_mode()
        def show_name(self, name: str):
            if "Thinking" in name or "Recording" in name:
                self.io.set_busy_header(name)
            else:
                self.io.set_busy_header(None)
                self.io.char_name = name
                self.io.update_header_text()
            self.io.header.update()
        def clear_text(self):
            self.io.edit.clear()

    class SpriteAdapter:
        def __init__(self, window):
            self.window = window
        def set_emotion(self, emotion: str):
            self.window.set_emotion(emotion)
        def get_thinking_sprite(self):
            self.window.set_emotion("<E:thinking>")

    def load_thinking_texts(self):
        thinking_path = self.config.pack_manager.get_path("logic", "thinking")
        self.thinking_texts = []
        if thinking_path and thinking_path.exists():
            try:
                with open(thinking_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        if data and isinstance(data[0], dict):
                            self.thinking_texts = [item.get("text", "") for item in data if isinstance(item, dict)]
                        else:
                            self.thinking_texts = [str(item) for item in data]
                print(f"[UI] Loaded {len(self.thinking_texts)} thinking texts")
            except Exception as e:
                print(f"Error loading thinking texts: {e}")

    def load_listening_texts(self):
        listening_path = self.config.pack_manager.get_path("logic", "listening")
        self.listening_texts = []
        if listening_path and listening_path.exists():
            try:
                with open(listening_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        if data and isinstance(data[0], dict):
                            self.listening_texts = [item.get("text", "") for item in data if isinstance(item, dict)]
                        else:
                            self.listening_texts = [str(item) for item in data]
                print(f"[UI] Loaded {len(self.listening_texts)} listening texts")
            except Exception as e:
                print(f"Error loading listening texts: {e}")

    def on_input_text_changed(self, text: str):
        if not self.is_processing and not self.is_listening:
            if text.strip():
                if self.character.current_emotion != "<E:thinking>":
                    self.set_emotion("<E:thinking>")
            else:
                if self.character.current_emotion != "<E:smile>":
                    self.set_emotion("<E:smile>")

    def start_thinking(self):
        if self.is_listening: return
        self.is_processing = True
        self.cancel_idle_fade()
        self.set_emotion("<E:thinking>")
        status_name = f"[{self.config.character_name}] Thinking..."
        self.dialogue.show_name(status_name)
        if self.config.thinking_text_enabled:
            self.show_thinking_text()
            if self.config.thinking_text_switch:
                self.thinking_switch_timer.stop()
                self.thinking_switch_timer.start(int(self.config.thinking_text_switch_time * 1000))

    def on_query_submitted(self, text: str):
        if self.is_listening: return
        self.is_processing = True
        self.cancel_idle_fade()
        self.request_query.emit(text)
        self.set_emotion("<E:thinking>")
        status_name = f"[{self.config.character_name}] Thinking..."
        self.dialogue.show_name(status_name)
        if self.config.thinking_text_enabled:
            self.show_thinking_text() 
            if self.config.thinking_text_switch:
                self.thinking_switch_timer.stop()
                self.thinking_switch_timer.start(int(self.config.thinking_text_switch_time * 1000))
            
    def show_thinking_text(self):
        if self.is_listening or not self.is_processing: return
        if self.thinking_texts:
            text = random.choice(self.thinking_texts)
            self.io.show_status(text)
            if self.config.thinking_text_switch:
                self.thinking_switch_timer.stop()
                self.thinking_switch_timer.start(int(self.config.thinking_text_switch_time * 1000))
        else:
            self.io.show_status("Thinking...")
                
    def switch_thinking_text(self):
        if self.is_listening or not self.is_processing: return
        if self.thinking_texts:
            text = random.choice(self.thinking_texts)
            self.io.show_status(text)
            if self.config.thinking_text_switch:
                self.thinking_switch_timer.stop()
                self.thinking_switch_timer.start(int(self.config.thinking_text_switch_time * 1000))

    def show_listening_text(self):
        
        self.thinking_timer.stop()
        self.thinking_switch_timer.stop()
        if self.config.listening_text_enabled and self.listening_texts:
            text = random.choice(self.listening_texts)
            self.io.show_status(text)
        else:
            self.io.show_status("Listening...")

    def set_listening(self, listening: bool, username: str = "User"):
        self.is_listening = listening
        if listening:

            self.is_processing = False
            self.thinking_timer.stop()
            self.thinking_switch_timer.stop()
            self.cancel_idle_fade()
            self.show_listening_text()
            status_name = f"[{username}] Recording..."
            self.dialogue.show_name(status_name)
        else:
            self.schedule_idle_fade()
            self.dialogue.show_name(self.config.character_name)

    def set_speaking(self, speaking: bool):
        self.is_speaking = speaking
        if speaking:
            self.cancel_idle_fade()
        else:
            self.schedule_idle_fade()

    def set_input_locked(self, locked: bool):
        self.io.edit.setReadOnly(locked)
        if locked:
            self.io.edit.clear()
            self.io.edit.setPlaceholderText("Listening...")
        else:
            self.io.edit.setPlaceholderText("Type and press Enter...")

    def set_emotion(self, emotion_tag: str):
        self.character.set_emotion(emotion_tag)
        self.sync_window_to_sprite()

    def show_response(self, text: str, emotion: str):
        self.is_processing = False 
        self.is_displaying_text = True
        self.thinking_timer.stop()
        self.thinking_switch_timer.stop()
        self.dialogue.show_name(self.config.character_name)
        self.set_emotion(emotion)
        self.io.show_output(text)

    def show_response_with_timeout(self, text: str, emotion: str):
        self.is_processing = False
        self.is_displaying_text = True
        self.thinking_timer.stop()
        self.thinking_switch_timer.stop()
        self.cancel_idle_fade()
        self.show_response(text, emotion)
        reading_time = self.config.base_display_time + (len(text) * self.config.text_read_speed)
        reading_time = max(1.5, reading_time)
        self.text_display_timer.start(int(reading_time * 1000))

    def show_behavior_response_with_timeout(self, text: str, emotion: str):
        self.is_processing = False
        self.is_displaying_text = True
        self.cancel_idle_fade()
        self.show_response(text, emotion)
        reading_time = max(2.0, len(text) * self.config.text_read_speed * self.config.behavior_text_read_multiplier)
        self.text_display_timer.start(int(reading_time * 1000))

    def finish_processing(self):
        self.is_processing = False
        self.is_displaying_text = False
        self.is_speaking = False
        self.set_input_locked(False)
        self.io.back_to_input_mode()
        self.thinking_timer.stop()
        self.thinking_switch_timer.stop()
        self.text_display_timer.stop()
        self.set_emotion("<E:smile>")
        self.schedule_idle_fade()
        
    def on_audio_complete(self):
        QTimer.singleShot(1500, self.finish_processing)

    def reset_to_default(self):
        self.finish_processing()
        
    def sync_window_to_sprite(self):
        def do_resize():
            self.character.adjustSize()
            self.setFixedSize(self.character.sizeHint())
        self.keep_bottom_right_anchor(do_resize)
        self.update_io_geometry()
        self._reinforce_topmost()
        
    def keep_bottom_right_anchor(self, do_resize_func):
        br = self.frameGeometry().bottomRight()
        do_resize_func()
        fr = self.frameGeometry()
        new_tl = br - QPoint(fr.width() - 1, fr.height() - 1)
        self.move(new_tl)
        
    def apply_scale(self, s: float):
        self.ui_scale = s
        def resize_task():
            self.character.set_scale(s)
            self.character.adjustSize()
            self.setFixedSize(self.character.sizeHint())
        self.keep_bottom_right_anchor(resize_task)
        self.update_io_geometry()
        self._reinforce_topmost()

    def _reinforce_topmost(self):
        if self.manual_hidden or self.fullscreen_hidden or not self.isVisible():
            return
        if self.config.always_on_top and sys.platform == "win32":
            try:
                hwnd = self.winId()
                if not isinstance(hwnd, int):
                    hwnd = int(hwnd)
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            except:
                pass

    def _apply_window_settings(self):
        flags = Qt.WindowType.FramelessWindowHint
        if self.config.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        
        current_flags = self.windowFlags()
        if flags != current_flags:
            self.setWindowFlags(flags)
            if self.isVisible():
                super().show()
                self._reinforce_topmost()
                self.sync_window_to_sprite()
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DropSiteRegistered, True)
        
        if not hasattr(self, '_drag_drop_initialized'):
            self.setAcceptDrops(True)
            self.character.setAcceptDrops(True)
            self.io.setAcceptDrops(True)
            self._drag_drop_initialized = True
        
        if not self.isVisible() and not self.manual_hidden:
            self.show()
            self.raise_()
            self._reinforce_topmost()
        elif self.isVisible():
            self.raise_()
            self._reinforce_topmost()
            if self.config.always_on_top:
                if not self.topmost_timer.isActive():
                    self.topmost_timer.start()
            else:
                self.topmost_timer.stop()

    def _reapply_drag_drop(self):
        self.setAcceptDrops(True)
        self.setAttribute(Qt.WidgetAttribute.WA_DropSiteRegistered, True)
        self.character.setAcceptDrops(True)
        self.io.setAcceptDrops(True)

    def refresh_from_config(self):
        img_rect = self.character.image_rect()
        if img_rect.width() > 0 and img_rect.height() > 0:
            target_w = self.config.sprite_width
            target_h = self.config.sprite_height
            scale_w = target_w / (img_rect.width() / self.ui_scale)
            scale_h = target_h / (img_rect.height() / self.ui_scale)
            new_scale = min(scale_w, scale_h)
            self.apply_scale(new_scale)
        self.io.set_names(self.config.username, self.config.character_name)
        
        self._apply_window_settings()
        
        self.load_thinking_texts()
        self.load_listening_texts()
        self.update_io_geometry()
        
    def check_idle_fade_allowed(self) -> bool:
        if self.config.always_show_ui or self.manual_hidden or self.fullscreen_hidden:
            return False
        if self.is_processing or self.is_listening or self.is_speaking or self.is_displaying_text:
            return False
        if self.io.edit.hasFocus():
            return False
        if QApplication.activeModalWidget():
            return False
        return True

    def update_io_geometry(self):
        img_rect = self.character.image_rect()
        if img_rect.isEmpty():
            self.io.set_bounds(QRect())
            return
        char_pos = self.character.pos()
        img_x = char_pos.x() + img_rect.x()
        img_y = char_pos.y() + img_rect.y()
        img_w = img_rect.width()
        img_h = img_rect.height()
        conf_w = self.config.dialogue_width
        conf_h = self.config.dialogue_height
        w = conf_w if conf_w > 0 else int(img_w * 0.6)
        h = conf_h if conf_h > 0 else int(img_h * 0.25)
        h = max(60, h)
        x = img_x + (img_w - w) // 2
        y = img_y + img_h - h + 5
        box = QRect(x, y, w, h)
        box.adjust(0, 4, 0, -4)
        self.io.set_bounds(box)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        event_type = event.type()
        
        if event_type in (QEvent.DragEnter, QEvent.DragMove, QEvent.DragLeave, QEvent.Drop):
            return super().eventFilter(obj, event)
        
        now = time.time()
        

        is_input_event = event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonRelease, 
                                          QEvent.MouseMove, QEvent.Wheel, QEvent.KeyPress, QEvent.KeyRelease)
        if self.input_hard_locked and is_input_event:
            return True

        if obj == self.character:
            if event.type() == QEvent.Enter:
                self.stats["is_hovering"] = True
                self.stats["hover_start_time"] = now
            elif event.type() == QEvent.Leave:
                self.stats["is_hovering"] = False
                self.stats["hover_leave_time"] = now
            
            
            if self.faded and self.fade_hover_recovery_sec > 0 and self.stats["is_hovering"]:
                if (now - self.stats["hover_start_time"]) >= self.fade_hover_recovery_sec:
                    self.cancel_idle_fade()
                    self.fade_hover_recovery_sec = 0.0

            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.stats["is_pressing"] = True
                    self.stats["press_start_time"] = now
                    self.stats["last_click_times"].append(now)
                    self.stats["last_click_times"] = self.stats["last_click_times"][-20:] 
                    self.stats["total_clicks"] += 1
                    if hasattr(self, "controller") and self.controller:
                        self.controller.state["total_clicks"] = self.stats["total_clicks"]
                        self.controller._save_state()
            elif event.type() == QEvent.MouseButtonRelease:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.stats["is_pressing"] = False
        w = obj if isinstance(obj, QWidget) else None
        on_self = (obj == self)
        on_character = (obj == self.character)
        on_overlay = (w == self.io or self.io.isAncestorOf(w)) if w else False
        is_relevant_widget = on_self or on_character or on_overlay
        if on_self and event.type() == QEvent.MouseMove:
            me = event 
            last_pos = getattr(self, "_last_mouse_pos", QPoint(-999, -999))
            curr_pos = me.pos()
            self._last_mouse_pos = curr_pos
            if (curr_pos - last_pos).manhattanLength() > 2:
                if self.faded and self.io.geometry().contains(curr_pos):
                    self.cancel_idle_fade()
                elif is_relevant_widget:
                    self.cancel_idle_fade()
        if is_relevant_widget:
            if event.type() == QEvent.MouseButtonPress:
                self.cancel_idle_fade()
            elif event.type() == QEvent.Enter:
                self.cancel_idle_fade()
            elif event.type() == QEvent.Leave:
                QTimer.singleShot(100, self.schedule_idle_fade)
        if event.type() == QEvent.Wheel and (on_character or on_overlay):
            we = event 
            mods = we.modifiers()
            if mods & Qt.KeyboardModifier.AltModifier:
                delta = we.angleDelta().y() or we.angleDelta().x()
                direction = 1 if delta > 0 else -1 if delta < 0 else 0
                if direction != 0:
                    s = self.character.get_scale() + direction * 0.05
                    s = max(0.5, min(s, 1.0))
                    self.apply_scale(s)
                return True
        if on_self or on_character:
            if event.type() == QEvent.MouseButtonPress:
                me = event 
                if me.button() == Qt.MouseButton.LeftButton:
                    want_drag = (self.drag_mod == Qt.KeyboardModifier.NoModifier) or (me.modifiers() & self.drag_mod)
                    if want_drag:
                        self.dragging = True
                        self.dragging_started = False
                        self.drag_offset = me.globalPosition().toPoint() - self.frameGeometry().topLeft()
                        self.character.setCursor(Qt.CursorShape.ClosedHandCursor)
                        return True
            elif event.type() == QEvent.MouseMove:
                if self.dragging:
                    me = event 
                    cur = me.globalPosition().toPoint()
                    thresh = QApplication.startDragDistance()
                    if not self.dragging_started:
                        delta = cur - (self.drag_offset + self.frameGeometry().topLeft())
                        if delta.manhattanLength() < thresh:
                            return True
                        self.dragging_started = True
                    self.move(cur - self.drag_offset)
                    return True
            elif event.type() == QEvent.MouseButtonRelease:
                if self.dragging:
                    self.dragging = False
                    self.dragging_started = False
                    self.character.setCursor(Qt.CursorShape.OpenHandCursor)
                    return True
        if on_character and event.type() == QEvent.Resize:
            self.update_io_geometry()
        return super().eventFilter(obj, event)

    def on_idle_timeout(self):
        if not self.check_idle_fade_allowed():
            self.idle_timer.start()
            return
        self.faded = True
        self.io.setVisible(False)
        self.fade_to(self.config.idle_opacity)
        
    def set_hard_lock(self, locked: bool, highlight: bool = False):
        self.input_hard_locked = locked
        if locked:
            self.io.setVisible(False)
            if highlight:
                self.fade_to(1.0)
                self.char_opacity.setOpacity(1.0)
            self.character.setCursor(Qt.CursorShape.ForbiddenCursor)
        else:
            self.io.setVisible(True)
            self.character.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_fade_recovery(self, sec: float):
        if sec > 0:
            self.faded = True
            self.fade_hover_recovery_sec = sec
        else:
            self.fade_hover_recovery_sec = 0.0

    def cancel_idle_fade(self):
        self.idle_timer.stop()
        self.fade_hover_recovery_sec = 0.0
        if self.faded:
            self.faded = False
            if not self.input_hard_locked:
                self.io.setVisible(True)
            self.fade_to(1.0)
            
    def schedule_idle_fade(self):
        if not self.check_idle_fade_allowed():
            return
        if not self.idle_timer.isActive():
            self.idle_timer.start()
            
    def fade_to(self, target: float):
        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.char_opacity.opacity())
        self.fade_anim.setEndValue(target)
        self.fade_anim.start()
        
    def set_fullscreen_hidden(self, hidden: bool):
        self.fullscreen_hidden = hidden
        self._update_visibility()
        
    def manual_hide(self):
        self.manual_hidden = True
        self._update_visibility()
        
    def manual_show(self):
        if not self.manual_hidden:
            return
        self.manual_hidden = False
        self.cancel_idle_fade()
        self._apply_window_settings()

    def _reset_stays_on_top(self):
        if not self.manual_hidden and not self.config.always_on_top:
            current_flags = self.windowFlags()
            if current_flags & Qt.WindowType.WindowStaysOnTopHint:
                self.setWindowFlags(current_flags & ~Qt.WindowType.WindowStaysOnTopHint)
                self.show()

    def _update_visibility(self):
        should_hide = self.manual_hidden or self.fullscreen_hidden
        if should_hide:
            if self.isVisible():
                super().hide()
        else:
            if not self.isVisible():
                super().show()
                self._reinforce_topmost()

    def safe_set_outfit(self, outfit: str):
        try:
            self.character.set_outfit(outfit)
        except Exception as e:
            print(f"Error switching outfit: {e}")
            
    def show_context_menu(self):
        menu = QMenu(self)
        menu.addAction("Replay Last Response", self.replay_requested.emit)
        menu.addSeparator()
        settings_action = menu.addAction("Settings", self.settings_requested.emit)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(40, 40, 40, 230);
                border: 1px solid 
                border-radius: 5px;
                padding: 5px;
            }
            QMenu::item {
                color: white;
                padding: 8px 20px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: rgba(100, 100, 100, 200);
            }
            QMenu::separator {
                height: 1px;
                background: 
                margin: 5px 10px;
            }
        """ )
        outfit_menu = menu.addMenu("Change Outfit")
        self.populate_outfit_menu(outfit_menu)
        pack_menu = menu.addMenu("Change Character Pack")
        self.populate_pack_menu(pack_menu)
        menu.addSeparator()
        drag_menu = menu.addMenu("Drag Binding")
        self.populate_drag_menu(drag_menu)
        menu.addSeparator()
        hide_action = menu.addAction("Hide (Background)")
        hide_action.triggered.connect(self.manual_hide)
        menu.addAction("Close", self.close)
        menu.exec(QCursor.pos())
        
    def populate_outfit_menu(self, menu: QMenu):
        outfits = self.character.get_available_outfits()
        grp = QActionGroup(menu)
        grp.setExclusive(True)
        for outfit in outfits:
            action = menu.addAction(outfit)
            action.setCheckable(True)
            action.setChecked(outfit == self.character.current_outfit)
            action.triggered.connect(lambda checked, o=outfit: self.safe_set_outfit(o))
            grp.addAction(action)

    def populate_pack_menu(self, menu: QMenu):
        packs = self.config.pack_manager.get_available_packs()
        active_id = self.config.pack_manager.active_pack_id
        grp = QActionGroup(menu)
        grp.setExclusive(True)
        for p_id in packs:
            action = menu.addAction(p_id)
            action.setCheckable(True)
            action.setChecked(p_id == active_id)
            action.triggered.connect(lambda checked, pid=p_id: self.pack_changed.emit(pid))
            grp.addAction(action)

    def populate_drag_menu(self, menu: QMenu):
        group = QActionGroup(menu)
        group.setExclusive(True)
        opts = [("Alt", Qt.KeyboardModifier.AltModifier), 
                ("Ctrl", Qt.KeyboardModifier.ControlModifier),
                ("Shift", Qt.KeyboardModifier.ShiftModifier),
                ("None", Qt.KeyboardModifier.NoModifier)]
        for label, mod in opts:
            action = QAction(label, menu)
            action.setCheckable(True)
            action.setChecked(self.drag_mod == mod)
            action.triggered.connect(lambda checked, m=mod: self.set_drag_mod(m))
            group.addAction(action)
            menu.addAction(action)
            
    def set_drag_mod(self, mod):
        self.drag_mod = mod

    @property
    def is_busy(self) -> bool:
        return self.is_processing or self.is_speaking or self.is_listening
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            print(f"[UI] dragEnterEvent received URLs: {[u.toLocalFile() for u in event.mimeData().urls()]}")
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            print(f"[UI] dropEvent received URLs")
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    if os.path.isfile(file_path):
                        path = Path(file_path)
                        file_info = {
                            "path": str(path),
                            "name": path.name,
                            "stem": path.stem,
                            "ext": path.suffix.lower() if path.suffix else ""
                        }
                        self.file_dropped.emit(file_info)
                        print(f"[UI] File dropped: {file_info}")
            event.acceptProposedAction()

    def on_file_dropped(self, file_info: dict):
        self.file_dropped.emit(file_info)

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            try:
                hwnd = int(self.winId())
                ctypes.windll.shell32.DragAcceptFiles(hwnd, True)
                
                GWL_EXSTYLE = -20
                WS_EX_ACCEPT_FILES = 0x00000010
                current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, current_style | WS_EX_ACCEPT_FILES)
            except Exception as e:
                pass
        if not hasattr(self, '_initial_position_set'):
            screen = QGuiApplication.primaryScreen().availableGeometry()
            self.move(screen.bottomRight() - QPoint(self.width() + 24, self.height() + 24))
            self._initial_position_set = True
        self.sync_window_to_sprite()
        self._reinforce_topmost()

    def closeEvent(self, event):
        QApplication.instance().quit()
        super().closeEvent(event)

    def nativeEvent(self, event_type, message):
        if event_type == "windows_dispatcher_MSG":
            msg = ctypes.wintypes.MSG.from_address(message.__int__())
            if msg.message == 0x0233:
                hdrop = msg.wParam
                file_count = ctypes.windll.shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)
                for i in range(file_count):
                    buf_len = 260
                    buf = ctypes.create_unicode_buffer(buf_len)
                    ctypes.windll.shell32.DragQueryFileW(hdrop, i, buf, buf_len)
                    file_path = buf.value
                    if os.path.isfile(file_path):
                        path = Path(file_path)
                        file_info = {
                            "path": str(path),
                            "name": path.name,
                            "stem": path.stem,
                            "ext": path.suffix.lower() if path.suffix else ""
                        }
                        print(f"[UI] Windows native drop: {file_info}")
                        self.on_file_dropped(file_info)
                ctypes.windll.shell32.DragFinish(hdrop)
                return True, 0
        return super().nativeEvent(event_type, message)
