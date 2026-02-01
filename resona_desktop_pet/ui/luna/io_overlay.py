from PySide6.QtCore import Qt, QRect, Signal, QEvent, QObject, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QKeyEvent, QResizeEvent, QPaintEvent
from PySide6.QtWidgets import QWidget, QTextEdit, QLabel, QFrame
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
        
    def layout_children(self):
        w = self.width()
        h = self.height()
        
        pad = max(6, h // 20)
        header_h = max(18, h // 5)
        
        self.header.setGeometry(pad, pad, w - 2 * pad, header_h)
        
        content_top = pad + header_h
        content_h = max(12, h - content_top - pad)
        
        rect = QRect(pad, content_top, w - 2 * pad, content_h)
        if self.edit.isVisible():
            self.edit.setGeometry(rect)
        if self.body.isVisible():
            self.body.setGeometry(rect)
            
    def update_fonts(self):

        font_scale = 1.0
        try:

            if hasattr(self.parent(), 'config'):
                font_scale = self.parent().config.font_scale
        except: pass

        h = self.height()
        header_h = max(18, h // 5)
        
        header_pixel_size = max(12, int(header_h * 0.6 * font_scale))
        font = self.header.font()
        font.setPixelSize(header_pixel_size)
        self.header.setFont(font)
        
        content_pixel_size = max(12, int(h * 0.12 * font_scale))
        font_c = self.edit.font()
        font_c.setPixelSize(content_pixel_size)
        self.edit.setFont(font_c)
        self.body.setFont(font_c)
        
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        rad = max(8, self.height() // 10)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        
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
                        print(f"[IOOverlay] 文件拖入: {file_info}")
