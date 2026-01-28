import asyncio
import json
import random
import re
from pathlib import Path
from typing import Optional, Dict, List, Callable
from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve,
    Signal, QObject, QSize
)
from PySide6.QtGui import (
    QPixmap, QColor, QFont, QFontMetrics,
    QMouseEvent, QAction, QCursor
)
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QVBoxLayout, QHBoxLayout,
    QFrame, QMenu, QApplication, QGraphicsOpacityEffect,
    QGridLayout
)
from ..config import ConfigManager
class AsyncHelper(QObject):
    result_ready = Signal(object)
    def __init__(self):
        super().__init__()
        self._loop = None
    def run_async(self, coro, callback=None):
        async def wrapper():
            result = await coro
            self.result_ready.emit(result)
            if callback:
                callback(result)
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
        import threading
        def run():
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(wrapper())
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
class DialogueBox(QFrame):
    text_submitted = Signal(str)
    input_focused = Signal(bool)
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self._typing_timer = QTimer()
        self._typing_timer.timeout.connect(self._type_next_char)
        self._full_text = ""
        self._current_index = 0
        self._busy_name: Optional[str] = None
        self._setup_ui()
    def _setup_ui(self):
        self.setObjectName("dialogueBox")
        self.setStyleSheet("""
            #dialogueBox {
                background-color: rgba(0, 0, 0, 80);
                border-radius: 10px;
                border: 2px solid rgba(255, 255, 255, 100);
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)
        font_scale = self.config.font_scale
        name_font_size = int(14 * font_scale)
        text_font_size = int(13 * font_scale)
        self.name_label = QLabel(self.config.character_name)
        self.name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label.setStyleSheet(f"""
            color: #FFD700;
            font-size: {name_font_size}px;
            font-weight: bold;
            font-family: "Yu Gothic UI", "Microsoft YaHei", sans-serif;
        """)
        layout.addWidget(self.name_label)
        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.text_label.setMinimumHeight(60)
        self.text_label.setStyleSheet(f"""
            color: white;
            font-size: {text_font_size}px;
            font-family: "Yu Gothic UI", "Microsoft YaHei", sans-serif;
            padding: 5px;
        """)
        layout.addWidget(self.text_label)
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type here...")
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(255, 255, 255, 30);
                border: 1px solid rgba(255, 255, 255, 80);
                border-radius: 5px;
                color: white;
                padding: 8px;
                font-size: {text_font_size}px;
                font-family: "Yu Gothic UI", "Microsoft YaHei", sans-serif;
            }}
            QLineEdit:focus {{
                border: 1px solid #FFD700;
                background-color: rgba(255, 255, 255, 50);
            }}
            QLineEdit:disabled {{
                background-color: rgba(100, 100, 100, 50);
                color: #888888;
            }}
        """)
        self.input_field.returnPressed.connect(self._on_submit)
        self.input_field.textChanged.connect(self._on_text_changed)
        self.input_field.installEventFilter(self)
        layout.addWidget(self.input_field)
        self.setFixedWidth(self.config.dialogue_width)
        self.setMinimumHeight(self.config.dialogue_height)
    def _update_name_display(self):
        if self._busy_name:
            self.name_label.setText(self._busy_name)
        elif self.input_field.text().strip():
            self.name_label.setText(self.config.username)
        else:
            self.name_label.setText(self.config.character_name)
    def _on_text_changed(self, text: str):
        if not self.input_field.isEnabled():
            return
        self._update_name_display()
        if text.strip():
            self.input_focused.emit(True)
        else:
            self.input_focused.emit(False)
    def eventFilter(self, obj, event):
        if obj == self.input_field:
            if event.type() == event.Type.FocusIn:
                if self.input_field.text().strip():
                    self._update_name_display()
                    self.input_focused.emit(True)
            elif event.type() == event.Type.FocusOut:
                if self.input_field.isEnabled():
                    self._update_name_display()
                    self.input_focused.emit(False)
        return super().eventFilter(obj, event)
    def _on_submit(self):
        text = self.input_field.text().strip()
        if text:
            self.input_field.clear()
            self.text_submitted.emit(text)
    def set_text(self, text: str, animate: bool = True):
        self._typing_timer.stop()
        self._full_text = text
        self._current_index = 0
        if animate and text:
            self.text_label.setText("")
            self._typing_timer.start(30)
        else:
            self.text_label.setText(text)
    def _type_next_char(self):
        if self._current_index < len(self._full_text):
            self._current_index += 1
            self.text_label.setText(self._full_text[:self._current_index])
        else:
            self._typing_timer.stop()
    def set_enabled(self, enabled: bool):
        self.input_field.setEnabled(enabled)
        if enabled:
            self.input_field.setFocus()
    def clear_text(self):
        self._typing_timer.stop()
        self.text_label.setText("")
        self._full_text = ""
        self.input_field.clear()
        self._update_name_display()
    def show_name(self, name: str, is_status: bool = False):
        if is_status:
            self._busy_name = name
        else:
            self._busy_name = None
        self._update_name_display()
        self.name_label.update()
class CharacterSprite(QLabel):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.project_root = Path(config.config_path).parent
        self.current_outfit = "risona_outfit_00"
        self.current_emotion = "<E:smile>"
        self.emotion_map: Dict[str, List[str]] = {}
        self._load_outfit(self.current_outfit)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        QTimer.singleShot(0, self._load_initial_sprite)
    def _load_initial_sprite(self):
        self.set_default_sprite()
    def _get_outfit_path(self, outfit: str) -> Path:
        return self.project_root / "resona_desktop_pet" / "ui" / "assets" / "modes" / outfit
    def _load_outfit(self, outfit: str) -> bool:
        outfit_path = self._get_outfit_path(outfit)
        sum_json = outfit_path / "sum.json"
        if not sum_json.exists():
            return False
        with open(sum_json, "r", encoding="utf-8") as f:
            self.emotion_map = json.load(f)
        self.current_outfit = outfit
        return True
    def get_available_outfits(self) -> List[str]:
        modes_path = self.project_root / "resona_desktop_pet" / "ui" / "assets" / "modes"
        outfits = []
        if modes_path.exists():
            for item in modes_path.iterdir():
                if item.is_dir() and (item / "sum.json").exists():
                    outfits.append(item.name)
        return sorted(outfits)
    def set_outfit(self, outfit: str) -> bool:
        if self._load_outfit(outfit):
            self.set_emotion(self.current_emotion)
            return True
        return False
    def set_emotion(self, emotion: str, deterministic: bool = False) -> bool:
        self.current_emotion = emotion
        sprites = self.emotion_map.get(emotion, [])
        if not sprites:
            base_emotion = emotion.split("|")[0] if "|" in emotion else emotion
            sprites = self.emotion_map.get(base_emotion, [])
        if not sprites:
            return self.set_default_sprite()
        if sprites:
            if deterministic:
                def digit_sum(s):
                    match = re.search(r'(\d+)(?:\.[^.]+)?$', s)
                    if not match:
                        match = re.search(r'(\d+)', s)
                    if match:
                        return sum(int(d) for d in match.group(1))
                    return 999999
                sprite_name = min(sprites, key=digit_sum)
            else:
                sprite_name = random.choice(sprites)
            return self._load_sprite(sprite_name)
        return False
    def set_default_sprite(self) -> bool:
        return self.set_emotion("<E:smile>", deterministic=True)
    def get_thinking_sprite(self) -> bool:
        return self.set_emotion("<E:thinking>")
    def _load_sprite(self, sprite_name: str) -> bool:
        outfit_path = self._get_outfit_path(self.current_outfit)
        for ext in [".png", ".jpg", ".webp"]:
            sprite_path = outfit_path / f"{sprite_name}{ext}"
            if sprite_path.exists():
                pixmap = QPixmap(str(sprite_path))
                if not pixmap.isNull():
                    scaled = pixmap.scaled(
                        self.config.sprite_width, self.config.sprite_height,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    self.setPixmap(scaled)
                    return True
        return False
class MainWindow(QWidget):
    request_thinking_text = Signal()
    request_query = Signal(str)
    replay_requested = Signal()
    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.project_root = Path(config.config_path).parent
        self._drag_position: Optional[QPoint] = None
        self._mouse_inside = False
        self._fade_timer = QTimer()
        self._thinking_timer = QTimer()
        self._thinking_text_timer = QTimer()
        self._response_clear_timer = QTimer()
        self._inactivity_timer = QTimer()
        self._thinking_texts: List[str] = []
        self._listening_texts: List[str] = []
        self._is_processing = False
        self._input_has_focus = False
        self._async_helper = AsyncHelper()
        self._setup_window()
        self._setup_ui()
        self._setup_timers()
        self.load_thinking_texts()
        self.load_listening_texts()
    def _setup_window(self):
        flags = Qt.WindowType.FramelessWindowHint
        if self.config.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        
        if self.config.show_in_taskbar:
            flags |= Qt.WindowType.Window
        else:
            flags |= Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setWindowTitle(self.config.character_name)
        icon_path = Path(self.config.tray_icon_path)
        if icon_path.exists():
            from PySide6.QtGui import QIcon
            self.setWindowIcon(QIcon(str(icon_path)))
    def _setup_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sprite = CharacterSprite(self.config, self)
        layout.addWidget(self.sprite, 0, 0, Qt.AlignmentFlag.AlignCenter)
        diag_layout = QVBoxLayout()
        diag_layout.setContentsMargins(0, 0, 0, 0)
        self.dialogue = DialogueBox(self.config, self)
        self.dialogue.text_submitted.connect(self._on_text_submitted)
        self.dialogue.input_focused.connect(self._on_input_focus_changed)
        diag_layout.addStretch(1)
        diag_layout.addWidget(self.dialogue, alignment=Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(diag_layout, 0, 0)
        self._dialogue_visible = True
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self.opacity_effect)
        self.resize(self.config.sprite_width, self.config.sprite_height)
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - self.width() - 50, screen.height() - self.height() - 100)
    def _setup_timers(self):
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._fade_out)
        self._thinking_timer.setSingleShot(True)
        self._thinking_timer.timeout.connect(self._show_thinking_text)
        self._thinking_text_timer.timeout.connect(self._switch_thinking_text)
        self._response_clear_timer.setSingleShot(True)
        self._response_clear_timer.timeout.connect(self._clear_response)
        self._inactivity_timer.setSingleShot(True)
        self._inactivity_timer.timeout.connect(self._clear_response)
    def load_thinking_texts(self):
        json_path = self.config.pack_manager.get_path("logic", "thinking")
        self._thinking_texts = []
        if json_path and json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._thinking_texts = [item["text"] for item in data]
            except Exception as e:
                print(f"[UI] Error loading thinking texts: {e}")
    def load_listening_texts(self):
        json_path = self.config.pack_manager.get_path("logic", "listening")
        self._listening_texts = []
        if json_path and json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._listening_texts = [item["text"] for item in data]
            except Exception as e:
                print(f"[UI] Error loading listening texts: {e}")
    def _on_text_submitted(self, text: str):
        if self._is_processing:
            return
        self._inactivity_timer.stop()
        self._is_processing = True
        self.dialogue.set_enabled(False)
        self.sprite.get_thinking_sprite()
        self.dialogue.show_name(f"[{self.config.character_name}] Thinking...", is_status=True)
        self._stop_fade_animation()
        self.opacity_effect.setOpacity(1.0)
        if not self._dialogue_visible:
            self.dialogue.show()
            self._dialogue_visible = True
        if self.config.thinking_text_enabled:
            self._thinking_timer.start(int(self.config.thinking_text_time * 1000))
        self.request_query.emit(text)
    def start_thinking(self):
        if self._is_processing:
            return
        self._inactivity_timer.stop()
        self._is_processing = True
        self.dialogue.set_enabled(False)
        self.sprite.get_thinking_sprite()
        self.dialogue.show_name(f"[{self.config.character_name}] Thinking...", is_status=True)
        self._stop_fade_animation()
        self.opacity_effect.setOpacity(1.0)
        if not self._dialogue_visible:
            self.dialogue.show()
            self._dialogue_visible = True
        if self.config.thinking_text_enabled:
            self._thinking_timer.start(int(self.config.thinking_text_time * 1000))
    def _on_input_focus_changed(self, focused: bool):
        self._input_has_focus = focused
        if focused:
            if self.dialogue.input_field.text().strip() and not self._is_processing:
                if self.sprite.current_emotion != "<E:thinking>":
                    self.sprite.get_thinking_sprite()
            self._inactivity_timer.stop()
        elif not self._is_processing:
            self.sprite.set_emotion("<E:smile>")
            self._inactivity_timer.start(self.config.dialogue_clear_timeout * 1000)
    def _show_thinking_text(self):
        if self._is_processing and self._thinking_texts:
            text = random.choice(self._thinking_texts)
            self.dialogue.set_text(text, animate=False)
            self.dialogue.show_name(f"[{self.config.character_name}] Thinking...", is_status=True)
            if self.config.thinking_text_switch:
                self._thinking_text_timer.start(
                    int(self.config.thinking_text_switch_time * 1000)
                )
    def _switch_thinking_text(self):
        if self._is_processing and self._thinking_texts:
            text = random.choice(self._thinking_texts)
            self.dialogue.set_text(text, animate=False)
            self.dialogue.show_name(f"[{self.config.character_name}] Thinking...", is_status=True)
            if self.config.thinking_text_switch:
                self._thinking_text_timer.start(
                    int(self.config.thinking_text_switch_time * 1000)
                )
    def _stop_fade_animation(self):
        if hasattr(self, '_fade_animation') and self._fade_animation.state() == QPropertyAnimation.State.Running:
            self._fade_animation.stop()
    def show_response(self, text: str, emotion: str = "<E:smile>"):
        self._thinking_timer.stop()
        self._thinking_text_timer.stop()
        self.sprite.set_emotion(emotion)
        self.dialogue.show_name(self.config.character_name, is_status=False)
        self.dialogue.set_text(text, animate=True)
        self._stop_fade_animation()
        self.opacity_effect.setOpacity(1.0)
        if not self._dialogue_visible:
            self.dialogue.show()
            self._dialogue_visible = True
    def show_response_with_timeout(self, text, emotion=None):
        self.show_response(text, emotion)
        base = self.config.base_display_time
        speed = self.config.text_read_speed
        duration_ms = int((base + len(text) * speed) * 1000)
        self._response_clear_timer.start(duration_ms)
    def show_behavior_response_with_timeout(self, text: str, emotion: str = "<E:smile>"):
        timeout = self.config.dialogue_clear_timeout * self.config.behavior_text_read_multiplier
        self.show_response_with_timeout(text, emotion)
    def set_speaking(self, speaking: bool):
        if speaking:
            self._thinking_timer.stop()
            self._thinking_text_timer.stop()
            if self._is_processing:
                self.dialogue.set_text("", animate=False)
        self._is_processing = speaking
    def set_listening(self, listening: bool, username: str = "User"):
        if listening:
            self._thinking_timer.stop()
            self._thinking_text_timer.stop()
            self.sprite.set_emotion("<E:thinking>")
            text = "Listening..."
            if self.config.listening_text_enabled and self._listening_texts:
                text = random.choice(self._listening_texts)
            self.dialogue.set_text(text, animate=False)
            self.dialogue.show_name(f"[{username}] Recording...", is_status=True)
            if not self._dialogue_visible:
                self.dialogue.show()
                self._dialogue_visible = True
            self._stop_fade_animation()
            self.opacity_effect.setOpacity(1.0)
        else:
            self.sprite.set_emotion("<E:smile>")
            self.dialogue.show_name(self.config.character_name, is_status=False)
    def set_input_locked(self, locked: bool):
        self.dialogue.set_enabled(not locked)
    def set_fullscreen_hidden(self, hidden: bool):
        if hidden:
            self.hide()
        else:
            self.show()
    def manual_show(self):
        self.show()
        self.activateWindow()
        self.raise_()
        self._stop_fade_animation()
        self.opacity_effect.setOpacity(1.0)
        if not self._dialogue_visible:
            self.dialogue.show()
            self._dialogue_visible = True
    def on_audio_complete(self):
        self._response_clear_timer.start(2000)
    def _clear_response(self):
        self._is_processing = False
        self.dialogue.clear_text()
        self.dialogue.set_enabled(True)
        self.sprite.set_default_sprite()
        if not self._mouse_inside:
            self._fade_out()
    def finish_processing(self):
        self._response_clear_timer.start(2000)
    def enterEvent(self, event):
        self._mouse_inside = True
        self._fade_timer.stop()
        self._fade_in()
        super().enterEvent(event)
    def leaveEvent(self, event):
        self._mouse_inside = False
        self._fade_timer.start(int(self.config.idle_fade_delay * 1000))
        super().leaveEvent(event)
    def _fade_out(self):
        if self._mouse_inside or self._is_processing or self._input_has_focus:
            return
        if self.config.always_show_ui:
            return
        self._stop_fade_animation()
        animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        animation.setDuration(300)
        animation.setStartValue(self.opacity_effect.opacity())
        animation.setEndValue(self.config.idle_opacity)
        animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        animation.start()
        self._fade_animation = animation
        if self._dialogue_visible:
            self.dialogue.hide()
            self._dialogue_visible = False
    def _fade_in(self):
        self._stop_fade_animation()
        animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        animation.setDuration(200)
        animation.setStartValue(self.opacity_effect.opacity())
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        animation.start()
        self._fade_animation = animation
        if not self._dialogue_visible:
            self.dialogue.show()
            self._dialogue_visible = True
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)
    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_position is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_position)
        super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_position = None
        super().mouseReleaseEvent(event)
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(40, 40, 40, 230);
                border: 1px solid #555;
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
                background: #555;
                margin: 5px 10px;
            }
        """)
        outfit_menu = menu.addMenu("Switch Outfit")
        outfits = self.sprite.get_available_outfits()
        for outfit in outfits:
            action = outfit_menu.addAction(outfit)
            action.setCheckable(True)
            action.setChecked(outfit == self.sprite.current_outfit)
            action.triggered.connect(lambda checked, o=outfit: self.sprite.set_outfit(o))
        menu.addSeparator()
        replay_action = menu.addAction("Replay Last Response")
        replay_action.triggered.connect(self.replay_requested.emit)
        menu.addSeparator()
        minimize_action = menu.addAction("Minimize to Tray")
        minimize_action.triggered.connect(self.hide)
        menu.addSeparator()
        exit_action = menu.addAction("Exit")
        exit_action.triggered.connect(QApplication.quit)
        menu.exec(event.globalPos())