from PySide6.QtCore import Qt, QRect, Signal, QEvent, QObject, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QKeyEvent, QResizeEvent, QPaintEvent, QFontDatabase, QPixmap
from PySide6.QtWidgets import QWidget, QTextEdit, QLabel, QFrame, QGraphicsDropShadowEffect
from typing import Optional
import os
from pathlib import Path

class IOOverlay(QWidget):


    submitted = Signal(str)
    text_changed = Signal(str)
    file_dropped = Signal(dict)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self._font_loaded_family = None
        self._loaded_font_path = None
        self._dialog_bg_pixmap: Optional[QPixmap] = None
        self._dialog_bg_path: Optional[str] = None
        self._cached_offsets: Optional[dict] = None
        self.user_name = "User"
        self.char_name = "Resona"
        self.busy_header: Optional[str] = None


        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self._type_next_char)
        self.full_text = ""
        self.current_char_index = 0


        self.header = QLabel(self)
        self.header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.header.setStyleSheet("color: white;")


        self.edit = QTextEdit(self)
        self.edit.setAcceptRichText(False)
        self.edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.edit.setFrameStyle(QFrame.Shape.NoFrame)
        self.edit.viewport().setAutoFillBackground(False)
        self.edit.setStyleSheet("background: transparent; color: white;")
        self.edit.setPlaceholderText("Type and press Enter...")
        self.edit.setAcceptDrops(False)
        self.edit.installEventFilter(self)
        self.edit.textChanged.connect(self._on_text_changed)


        self.body = QLabel(self)
        self.body.setVisible(False)
        self.body.setWordWrap(True)
        self.body.setStyleSheet("color: white;")
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self.to_input()

    def _on_text_changed(self):
        text = self.edit.toPlainText().strip()
        self.update_header_text()
        self.text_changed.emit(text)

    def set_names(self, user_name: str, char_name: str):
        self.user_name = user_name
        self.char_name = char_name
        self.update_header_text()

    def update_header_text(self):

        if self.busy_header:
            self.header.setText(f"【{self.busy_header}】")
            return


        if self.edit.isVisible() and self.edit.isEnabled() and self.edit.toPlainText().strip():
            name = self.user_name
        else:
            name = self.char_name
        self.header.setText(f"【{name}】")

    def set_bounds(self, r: QRect):
        self.setGeometry(r)
        self.layout_children()
        self.update_fonts()
        self.update()

    def show_status(self, text: str):
        self.to_output(text, animate=True)

    def show_output(self, text: str):
        self.to_output(text, animate=True)

    def set_busy_header(self, header: Optional[str]):

        self.busy_header = header
        self.update_header_text()

    def back_to_input_mode(self):
        self.busy_header = None
        self.to_input()

    def to_input(self):
        self.typing_timer.stop()
        self.body.setVisible(False)
        self.edit.setEnabled(True)
        self.edit.setVisible(True)
        self.edit.clear()
        self.edit.setFocus()
        self.update_header_text()
        self.layout_children()
        self.update()

    def to_output(self, text: str, animate: bool = False):
        self.edit.setEnabled(False)
        self.edit.setVisible(False)
        self.body.setVisible(True)

        self.update_header_text()
        self.layout_children()
        self.update()

        self.typing_timer.stop()
        if animate and text:
            self.full_text = text
            self.current_char_index = 0
            self.body.setText("")
            self.typing_timer.start(30)
        else:
            self.body.setText(text)

    def _type_next_char(self):
        if self.current_char_index < len(self.full_text):
            self.current_char_index += 1
            self.body.setText(self.full_text[:self.current_char_index])
        else:
            self.typing_timer.stop()

    def _get_offsets(self, cfg) -> dict:
        if self._cached_offsets is not None:
            return self._cached_offsets

        try:
            self._cached_offsets = {
                'header_x': int(cfg.get("General", "header_offset_x", "0")),
                'header_y': int(cfg.get("General", "header_offset_y", "0")),
                'text_x': int(cfg.get("General", "text_offset_x", "0")),
                'text_y': int(cfg.get("General", "text_offset_y", "0")),
            }
        except:
            self._cached_offsets = {
                'header_x': 0, 'header_y': 0,
                'text_x': 0, 'text_y': 0,
            }
        return self._cached_offsets

    def layout_children(self):
        w = self.width()
        h = self.height()

        offsets = {'header_x': 0, 'header_y': 0, 'text_x': 0, 'text_y': 0}
        try:
            if hasattr(self.parent(), 'config'):
                offsets = self._get_offsets(self.parent().config)
        except: pass

        pad = max(6, h // 20)
        header_h = max(18, h // 5)

        header_x = pad + offsets['header_x']
        header_y = pad + offsets['header_y']
        self.header.setGeometry(header_x, header_y, w - 2 * pad, header_h)

        content_top = pad + header_h
        content_h = max(12, h - content_top - pad)

        content_x = pad + offsets['text_x']
        content_y = content_top + offsets['text_y']
        content_w = w - 2 * pad
        content_h_adjusted = content_h - offsets['text_y']
        if content_h_adjusted < 12:
            content_h_adjusted = 12

        rect = QRect(content_x, content_y, content_w, content_h_adjusted)
        if self.edit.isVisible():
            self.edit.setGeometry(rect)
        if self.body.isVisible():
            self.body.setGeometry(rect)

    def update_fonts(self):

        font_scale = 1.0
        config = None
        text_color = "white"
        stroke_enabled = False
        stroke_color = "black"
        stroke_width = 0
        shadow_enabled = False
        shadow_color = "black"
        shadow_offset_x = 0
        shadow_offset_y = 0
        shadow_blur = 0
        try:
            if hasattr(self.parent(), 'config'):
                config = self.parent().config
                font_scale = config.font_scale

                tc_str = config.dialog_text_color
                if "," in tc_str:
                    tc = self._parse_color(tc_str, 100)
                    text_color = tc.name()
                elif tc_str.startswith("#"):
                    text_color = tc_str

                stroke_enabled = config.dialog_text_stroke_enabled
                if stroke_enabled:
                    sc_str = config.dialog_text_stroke_color
                    if "," in sc_str:
                        sc = self._parse_color(sc_str, 100)
                        stroke_color = sc.name()
                    elif sc_str.startswith("#"):
                        stroke_color = sc_str
                    stroke_width = config.dialog_text_stroke_width

                shadow_enabled = config.dialog_text_shadow_enabled
                if shadow_enabled:
                    shc_str = config.dialog_text_shadow_color
                    if "," in shc_str:
                        shc = self._parse_color(shc_str, 100)
                        shadow_color = shc.name()
                    elif shc_str.startswith("#"):
                        shadow_color = shc_str
                    shadow_offset_x = config.dialog_text_shadow_offset_x
                    shadow_offset_y = config.dialog_text_shadow_offset_y
                    shadow_blur = config.dialog_text_shadow_blur

        except: pass

        style = f"color: {text_color};"
        self.header.setStyleSheet(style)
        self.body.setStyleSheet(style)
        self.edit.setStyleSheet(f"background: transparent; {style}")

        if shadow_enabled and shadow_blur > 0:
            shadow_color_q = QColor(shadow_color)

            shadow_effect_header = QGraphicsDropShadowEffect(self)
            shadow_effect_header.setColor(shadow_color_q)
            shadow_effect_header.setOffset(shadow_offset_x, shadow_offset_y)
            shadow_effect_header.setBlurRadius(shadow_blur)
            self.header.setGraphicsEffect(shadow_effect_header)

            shadow_effect_body = QGraphicsDropShadowEffect(self)
            shadow_effect_body.setColor(shadow_color_q)
            shadow_effect_body.setOffset(shadow_offset_x, shadow_offset_y)
            shadow_effect_body.setBlurRadius(shadow_blur)
            self.body.setGraphicsEffect(shadow_effect_body)

            shadow_effect_edit = QGraphicsDropShadowEffect(self)
            shadow_effect_edit.setColor(shadow_color_q)
            shadow_effect_edit.setOffset(shadow_offset_x, shadow_offset_y)
            shadow_effect_edit.setBlurRadius(shadow_blur)
            self.edit.setGraphicsEffect(shadow_effect_edit)
        else:
            self.header.setGraphicsEffect(None)
            self.body.setGraphicsEffect(None)
            self.edit.setGraphicsEffect(None)

        target_font_path = None
        if config and config.dialog_font:
            font_path = Path(config.dialog_font)
            if not font_path.is_absolute():
                font_path = Path(config.config_path).parent / font_path
            target_font_path = str(font_path)

        if target_font_path != self._loaded_font_path:
            self._loaded_font_path = target_font_path
            self._font_loaded_family = None

            if target_font_path:
                if os.path.exists(target_font_path):
                    font_id = QFontDatabase.addApplicationFont(target_font_path)
                    if font_id != -1:
                        families = QFontDatabase.applicationFontFamilies(font_id)
                        if families:
                            self._font_loaded_family = families[0]
                            print(f"[IOOverlay] Loaded custom font: {self._font_loaded_family}")
                    else:
                        print(f"[IOOverlay] Failed to load font: {target_font_path}")
                else:
                    print(f"[IOOverlay] Font file not found: {target_font_path}")

        h = self.height()
        header_h = max(18, h // 5)
        
        header_pixel_size = max(12, int(header_h * 0.6 * font_scale))
        
        if self._font_loaded_family:
            font = QFont(self._font_loaded_family)
        else:
            font = self.header.font()

        font.setPixelSize(header_pixel_size)
        self.header.setFont(font)

        content_pixel_size = max(12, int(h * 0.12 * font_scale))

        if self._font_loaded_family:
            font_c = QFont(self._font_loaded_family)
        else:
            font_c = self.edit.font()

        font_c.setPixelSize(content_pixel_size)
        self.edit.setFont(font_c)
        self.body.setFont(font_c)

    def _parse_color(self, color_str: str, opacity_percent: int) -> QColor:
        alpha = int((opacity_percent / 100.0) * 255)
        alpha = max(0, min(255, alpha))

        color_str = color_str.strip()

        if color_str.startswith("#"):
            c = QColor(color_str)
            c.setAlpha(alpha)
            return c

        if "," in color_str:
            try:
                parts = [int(p.strip()) for p in color_str.split(",")]
                if len(parts) >= 3:
                    return QColor(parts[0], parts[1], parts[2], alpha)
            except: pass

        return QColor(0, 0, 0, alpha)

    def _load_dialog_background(self, cfg) -> bool:
        use_custom_str = cfg.get("General", "dialog_use_custom_image", "false")
        use_custom = use_custom_str.lower() == "true"
        if not use_custom:
            self._dialog_bg_pixmap = None
            self._dialog_bg_path = None
            return False

        image_path = cfg.get("General", "dialog_image_path", "")
        if not image_path:
            self._dialog_bg_pixmap = None
            self._dialog_bg_path = None
            return False

        if self._dialog_bg_path == image_path and self._dialog_bg_pixmap is not None:
            return True

        path = Path(image_path)
        if not path.is_absolute():
            path = Path(cfg.config_path).parent / path

        path_str = str(path)
        if not path.exists():
            print(f"[IOOverlay] Dialog background image not found: {path_str}")
            self._dialog_bg_pixmap = None
            self._dialog_bg_path = None
            return False

        pixmap = QPixmap(path_str)
        if pixmap.isNull():
            print(f"[IOOverlay] Failed to load dialog background image: {path_str}")
            self._dialog_bg_pixmap = None
            self._dialog_bg_path = None
            return False

        self._dialog_bg_pixmap = pixmap
        self._dialog_bg_path = image_path
        print(f"[IOOverlay] Loaded dialog background image: {path_str} ({pixmap.width()}x{pixmap.height()})")
        return True

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        use_image_bg = False
        try:
            if hasattr(self.parent(), 'config'):
                cfg = self.parent().config
                use_image_bg = self._load_dialog_background(cfg)
        except Exception as e:
            print(f"[IOOverlay] Error loading dialog background: {e}")

        if use_image_bg and self._dialog_bg_pixmap is not None:
            image_opacity = 100
            try:
                if hasattr(self.parent(), 'config'):
                    cfg = self.parent().config
                    opacity_str = cfg.get("General", "dialog_image_opacity", "100")
                    image_opacity = int(opacity_str)
                    image_opacity = max(0, min(100, image_opacity))
            except: pass

            painter.setOpacity(image_opacity / 100.0)

            scaled_pixmap = self._dialog_bg_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(self.rect(), scaled_pixmap)

            painter.setOpacity(1.0)
        else:
            rad = max(8, self.height() // 10)
            painter.setPen(Qt.PenStyle.NoPen)

            bg_color = QColor(0, 0, 0, 90)
            try:
                if hasattr(self.parent(), 'config'):
                    cfg = self.parent().config
                    bg_color = self._parse_color(cfg.dialog_color, cfg.dialog_opacity)
            except: pass

            painter.setBrush(bg_color)
            painter.drawRoundedRect(self.rect(), rad, rad)

    def resizeEvent(self, event: QResizeEvent):
        self.layout_children()
        self.update_fonts()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj == self.edit and event.type() == QEvent.KeyPress:
            key_event = event
            just_enter = (key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)) and \
                         not (key_event.modifiers() & (Qt.KeyboardModifier.ShiftModifier |
                                                       Qt.KeyboardModifier.ControlModifier |
                                                       Qt.KeyboardModifier.AltModifier))

            if just_enter:
                text = self.edit.toPlainText().strip()
                if text:
                    self.submitted.emit(text)
                return True

        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        print(f"[IOOverlay] dragEnterEvent")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        print(f"[IOOverlay] dropEvent")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
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
                        print(f"[IOOverlay] File dropped: {file_info}")
