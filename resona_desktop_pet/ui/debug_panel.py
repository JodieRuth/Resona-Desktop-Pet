import json
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QComboBox, QPushButton, QTextEdit)
from PySide6.QtCore import Qt, Signal
from ..backend.llm_backend import LLMResponse

class DebugPanel(QWidget):
    request_manual_response = Signal(object)

    def __init__(self, pack_manager, config):
        super().__init__()
        self.pack_manager = pack_manager
        self.config = config
        self._init_ui()
        
    def _init_ui(self):
        self.setWindowTitle("Resona Dev Control Panel")
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(400, 500)
        
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("Emotion:"))
        self.emotion_combo = QComboBox()
        emotions = self.pack_manager.get_available_emotions()
        if not emotions:
            emotions = ["<E:smile>", "<E:serious>", "<E:angry>", "<E:sad>", "<E:thinking>", 
                        "<E:surprised>", "<E:dislike>", "<E:smirk>", "<E:embarrassed>"]
        self.emotion_combo.addItems(emotions)
        layout.addWidget(self.emotion_combo)
        
        layout.addWidget(QLabel("TTS Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["ja", "zh", "en", "ko"])
        default_lang = "ja"
        if self.config.use_pack_settings:
            default_lang = self.pack_manager.pack_data.get("tts_language", "ja")
        self.lang_combo.setCurrentText(default_lang)
        layout.addWidget(self.lang_combo)
        
        layout.addWidget(QLabel("Text Display (UI Bubble):"))
        self.display_edit = QTextEdit()
        self.display_edit.setPlaceholderText("What the user sees...")
        self.display_edit.setFixedHeight(80)
        layout.addWidget(self.display_edit)
        
        layout.addWidget(QLabel("Text TTS (Voice):"))
        self.tts_edit = QTextEdit()
        self.tts_edit.setPlaceholderText("What the character says...")
        self.tts_edit.setFixedHeight(80)
        layout.addWidget(self.tts_edit)
        
        self.sync_btn = QPushButton("Sync Display to TTS")
        self.sync_btn.clicked.connect(lambda: self.tts_edit.setPlainText(self.display_edit.toPlainText()))
        layout.addWidget(self.sync_btn)
        
        self.send_btn = QPushButton("EXECUTE (Thinking -> Speak)")
        self.send_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; height: 40px;")
        self.send_btn.clicked.connect(self._on_send)
        layout.addWidget(self.send_btn)
        
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(self.clear_btn)

        self.setLayout(layout)

    def _on_clear(self):
        self.display_edit.clear()
        self.tts_edit.clear()

    def _on_send(self):
        response = LLMResponse()
        response.emotion = self.emotion_combo.currentText()
        response.text_display = self.display_edit.toPlainText()
        response.text_tts = self.tts_edit.toPlainText()
        
        manual_data = {
            "response": response,
            "tts_lang": self.lang_combo.currentText()
        }
        
        self.request_manual_response.emit(manual_data)
        
    def update_emotions(self):
        self.emotion_combo.clear()
        emotions = self.pack_manager.get_available_emotions()
        self.emotion_combo.addItems(emotions)
