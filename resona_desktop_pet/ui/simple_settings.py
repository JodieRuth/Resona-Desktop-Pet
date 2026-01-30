

from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QScrollArea, QWidget,
    QLabel, QLineEdit, QPushButton, QFormLayout, QGroupBox,
    QMessageBox, QCheckBox, QComboBox
)

from ..config import ConfigManager

class SimpleSettingsDialog(QDialog):
    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.resize(600, 700)
        

        main_layout = QVBoxLayout(self)
        

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        self.form_layout = QFormLayout(content_widget)
        self.form_layout.setSpacing(15)
        
        self.fields = {}
        
        self._add_section("General Settings")
        self._add_text("General", "CharacterName", "Character Name", "Name displayed in the dialog box.")
        self._add_text("Custom", "Username", "User Name", "Your name displayed when talking.")
        self._add_bool("General", "use_pack_settings", "Use Pack Settings", "Override Name, User Name, Prompt and TTS Language with pack defaults.")
        self._add_bool("General", "always_show_ui", "Always Show UI", "If checked, UI will never fade out.")
        self._add_bool("General", "always_on_top", "Always on Top", "If checked, the pet will stay above other windows.")
        self._add_text("General", "global_show_hotkey", "Show Hotkey", "Global hotkey to show/focus the pet (e.g. ctrl+alt+0).")
        
        self._add_section("Window & UI Size")
        self._add_text("General", "width", "Window Width", "Main window sprite width.")
        self._add_text("General", "height", "Window Height", "Main window sprite height.")
        self._add_text("General", "dialogue_width", "Dialogue Width", "Width of the dialogue box.")
        self._add_text("General", "dialogue_height", "Dialogue Height", "Minimum height of the dialogue box.")
        self._add_text("General", "font_scale", "Font Scale", "Multiplier for all UI text (e.g. 1.2).")
        
        self._add_section("Trigger & Behavior")
        self._add_bool("Behavior", "enabled", "Enable Behavior Monitor", "React to windows/processes.")
        self._add_text("Behavior", "interval", "Check Interval (s)", "How often to check windows.")
        self._add_text("Behavior", "trigger_cooldown", "Global Cooldown (s)", "Wait time between triggers.")
        self._add_text("Behavior", "post_busy_delay", "Post-Busy Delay (s)", "Wait time after busy state ends.")
        
        self._add_section("LLM (Chat Model)")
        self._add_combo("General", "model_select", "Model Provider", [
            ("1", "1: OpenAI"),
            ("2", "2: DeepSeek"),
            ("3", "3: Claude"),
            ("4", "4: Kimi"),
            ("5", "5: Gemini"),
            ("6", "6: Grok")
        ], "Select which provider to use.")
        self._add_combo("General", "llm_mode", "Run Mode", [("cloud", "Cloud API"), ("local", "Local")], "Use Cloud API or Local Python.")
        

        current_model = self.config.model_select
        section_map = {
            1: "Model_1_OpenAI", 2: "Model_2_DeepSeek", 3: "Model_3_Claude",
            4: "Model_4_Kimi", 5: "Model_5_Gemini", 6: "Model_6_Grok"
        }
        active_section = section_map.get(current_model, "Model_1_OpenAI")
        self._add_text(active_section, "api_key", f"API Key ({active_section})", "API Key for the selected provider.")
        self._add_text(active_section, "base_url", "Base URL", "Optional API Base URL.")
        self._add_text(active_section, "model_name", "Model Name", "Specific model version string.")
        
        self._add_section("Prompt")
        self._add_text("Prompt", "file_path", "Prompt File", "Path to the system prompt text file.")

        self._add_section("TTS (Voice Generation)")
        self._add_bool("SoVITS", "enabled", "Enable SoVITS", "Enable GPT-SoVITS voice synthesis.")
        self._add_text("SoVITS", "api_port", "API Port", "Local port for SoVITS server.")
        self._add_text("SoVITS", "model_dir", "Model Dir", "Directory containing .ckpt and .pth files.")
        
        self._add_section("STT (Voice Input)")
        self._add_bool("STT", "enabled", "Enable STT", "Enable voice input.")
        self._add_text("STT", "hotkey", "Hotkey", "Key combination to start/stop recording (e.g. ctrl+shift+i).")
        self._add_combo("STT", "language", "Fixed Language", [
            ("auto", "Auto Detect"),
            ("zh", "Chinese"),
            ("en", "English"),
            ("ja", "Japanese"),
            ("ko", "Korean"),
            ("yue", "Cantonese")
        ], "Explicitly fix the STT recognition language.")
        self._add_text("STT", "max_duration", "Max Duration (s)", "Max recording time per turn.")

        self._add_section("Weather")
        self._add_bool("Weather", "enabled", "Enable Weather", "Check weather on startup.")
        self._add_text("Weather", "api_key", "WeatherAPI Key", "Key from weatherapi.com.")

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save & Reload")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

    def _add_section(self, title):
        label = QLabel(title)
        label.setStyleSheet("font-weight: bold; font-size: 14px; margin-top: 10px; color: #aaa;")
        self.form_layout.addRow(label)

    def _add_text(self, section, key, label, desc):
        widget = QLineEdit()
        val = self.config.get(section, key)
        widget.setText(str(val) if val is not None else "")
        widget.setPlaceholderText(desc)
        widget.setToolTip(desc)
        self.form_layout.addRow(f"{label}:", widget)
        self.fields[(section, key)] = widget

    def _add_bool(self, section, key, label, desc):
        widget = QCheckBox()
        val = self.config.getboolean(section, key)
        widget.setChecked(val)
        widget.setToolTip(desc)
        self.form_layout.addRow(f"{label}:", widget)
        self.fields[(section, key)] = widget

    def _add_combo(self, section, key, label, options, desc):
        widget = QComboBox()
        for data, text in options:
            widget.addItem(text, data)
        
        current_val = str(self.config.get(section, key))
        index = widget.findData(current_val)
        if index >= 0:
            widget.setCurrentIndex(index)
            
        widget.setToolTip(desc)
        self.form_layout.addRow(f"{label}:", widget)
        self.fields[(section, key)] = widget

    def _save(self):
        try:
            for (section, key), widget in self.fields.items():
                if isinstance(widget, QLineEdit):
                    val = widget.text().strip()
                    self.config.set(section, key, val)
                elif isinstance(widget, QCheckBox):
                    self.config.set(section, key, "true" if widget.isChecked() else "false")
                elif isinstance(widget, QComboBox):
                    self.config.set(section, key, str(widget.currentData()))
            
            self.config.save()
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save: {e}")

