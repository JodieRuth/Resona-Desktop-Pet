

from pathlib import Path
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QGroupBox, QFormLayout, QFileDialog, QMessageBox
)

from ..config import ConfigManager


class SettingsDialog(QDialog):


    def __init__(self, config: ConfigManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.project_root = Path(config.config_path).parent

        self.setWindowTitle("Resona Desktop Pet - Settings")
        self.setMinimumSize(500, 450)
        self.setStyleSheet("""
            QDialog {
                background-color: 
            }
            QLabel {
                color: 
            }
            QGroupBox {
                color: 
                border: 1px solid 
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: 
                border: 1px solid 
                border-radius: 3px;
                color: white;
                padding: 5px;
                min-height: 25px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid 
            }
            QCheckBox {
                color: white;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QPushButton {
                background-color: 
                color: white;
                border: none;
                border-radius: 3px;
                padding: 8px 20px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: 
            }
            QPushButton:pressed {
                background-color: 
            }
            QPushButton
                background-color: 
            }
            QPushButton
                background-color: 
            }
            QTabWidget::pane {
                border: 1px solid 
                border-radius: 5px;
                background-color: 
            }
            QTabBar::tab {
                background-color: 
                color: 
                padding: 8px 20px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: 
                color: white;
            }
        """)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)


        tabs = QTabWidget()
        tabs.addTab(self._create_general_tab(), "General")
        tabs.addTab(self._create_llm_tab(), "LLM")
        tabs.addTab(self._create_tts_tab(), "TTS")
        tabs.addTab(self._create_stt_tab(), "STT")
        tabs.addTab(self._create_ocr_tab(), "OCR")
        tabs.addTab(self._create_physics_tab(), "Physics")
        layout.addWidget(tabs)


        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelButton")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _create_general_tab(self) -> QWidget:

        widget = QWidget()
        layout = QVBoxLayout(widget)


        char_group = QGroupBox("Character")
        char_layout = QFormLayout(char_group)

        self.character_name_edit = QLineEdit()
        char_layout.addRow("Character Name:", self.character_name_edit)

        self.username_edit = QLineEdit()
        char_layout.addRow("Your Name:", self.username_edit)

        self.always_on_top_check = QCheckBox("Always on top")
        char_layout.addRow(self.always_on_top_check)

        self.always_show_ui_check = QCheckBox("Always show (no fade)")
        char_layout.addRow(self.always_show_ui_check)

        icon_layout = QHBoxLayout()
        self.tray_icon_path_edit = QLineEdit()
        icon_layout.addWidget(self.tray_icon_path_edit)
        browse_icon_btn = QPushButton("Browse")
        browse_icon_btn.clicked.connect(lambda: self._browse_file(self.tray_icon_path_edit, "Icon Files (*.ico *.png *.jpg)"))
        icon_layout.addWidget(browse_icon_btn)
        char_layout.addRow("Tray Icon:", icon_layout)

        layout.addWidget(char_group)


        thinking_group = QGroupBox("Thinking Text")
        thinking_layout = QFormLayout(thinking_group)

        self.thinking_enabled_check = QCheckBox("Enable thinking text")
        thinking_layout.addRow(self.thinking_enabled_check)

        self.thinking_switch_check = QCheckBox("Auto-switch thinking text")
        thinking_layout.addRow(self.thinking_switch_check)

        self.thinking_time_spin = QDoubleSpinBox()
        self.thinking_time_spin.setRange(0.1, 10.0)
        self.thinking_time_spin.setSingleStep(0.1)
        self.thinking_time_spin.setSuffix(" sec")
        thinking_layout.addRow("Show after:", self.thinking_time_spin)

        self.thinking_switch_time_spin = QDoubleSpinBox()
        self.thinking_switch_time_spin.setRange(1.0, 30.0)
        self.thinking_switch_time_spin.setSingleStep(0.5)
        self.thinking_switch_time_spin.setSuffix(" sec")
        thinking_layout.addRow("Switch interval:", self.thinking_switch_time_spin)

        layout.addWidget(thinking_group)


        history_group = QGroupBox("Conversation History")
        history_layout = QFormLayout(history_group)

        self.max_rounds_spin = QSpinBox()
        self.max_rounds_spin.setRange(0, 50)
        self.max_rounds_spin.setSpecialValueText("Disabled")
        history_layout.addRow("Max rounds:", self.max_rounds_spin)

        self.time_context_check = QCheckBox("Include time context")
        history_layout.addRow(self.time_context_check)

        self.ip_context_check = QCheckBox("Include user IP/Location")
        history_layout.addRow(self.ip_context_check)

        layout.addWidget(history_group)

        behavior_group = QGroupBox("Behavior")
        behavior_layout = QFormLayout(behavior_group)
        self.action_bring_to_front_check = QCheckBox("Bring to front on action")
        behavior_layout.addRow(self.action_bring_to_front_check)
        layout.addWidget(behavior_group)

        layout.addStretch()
        return widget

    def _browse_file(self, line_edit: QLineEdit, filter: str):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select File",
            str(self.project_root),
            filter
        )
        if file_path:
            line_edit.setText(file_path)

    def _create_llm_tab(self) -> QWidget:

        widget = QWidget()
        layout = QVBoxLayout(widget)


        model_group = QGroupBox("Model Selection")
        model_layout = QFormLayout(model_group)

        self.model_select_combo = QComboBox()
        self.model_select_combo.addItems([
            "1: OpenAI (ChatGPT)",
            "2: DeepSeek",
            "3: Claude (Anthropic)",
            "4: Kimi (Moonshot)",
            "5: Gemini (Google)",
            "6: Grok (xAI)"
        ])
        self.model_select_combo.currentIndexChanged.connect(self._on_model_changed)
        model_layout.addRow("Provider:", self.model_select_combo)

        self.llm_mode_combo = QComboBox()
        self.llm_mode_combo.addItems(["cloud", "local"])
        model_layout.addRow("Mode:", self.llm_mode_combo)

        layout.addWidget(model_group)


        api_group = QGroupBox("API Configuration")
        api_layout = QFormLayout(api_group)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("API Key:", self.api_key_edit)

        self.base_url_edit = QLineEdit()
        api_layout.addRow("Base URL:", self.base_url_edit)

        self.model_name_edit = QLineEdit()
        api_layout.addRow("Model Name:", self.model_name_edit)

        layout.addWidget(api_group)


        prompt_group = QGroupBox("Prompt")
        prompt_layout = QFormLayout(prompt_group)

        self.prompt_source_combo = QComboBox()
        self.prompt_source_combo.addItems(["file", "text"])
        prompt_layout.addRow("Source:", self.prompt_source_combo)

        prompt_file_layout = QHBoxLayout()
        self.prompt_file_edit = QLineEdit()
        prompt_file_layout.addWidget(self.prompt_file_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_prompt_file)
        prompt_file_layout.addWidget(browse_btn)
        prompt_layout.addRow("File:", prompt_file_layout)

        layout.addWidget(prompt_group)

        layout.addStretch()
        return widget

    def _create_tts_tab(self) -> QWidget:

        widget = QWidget()
        layout = QVBoxLayout(widget)


        self.tts_enabled_check = QCheckBox("Enable TTS (GPT-SoVITS)")
        layout.addWidget(self.tts_enabled_check)


        tts_group = QGroupBox("TTS Configuration")
        tts_layout = QFormLayout(tts_group)

        self.tts_device_combo = QComboBox()
        self.tts_device_combo.addItems(["cuda", "cpu"])
        tts_layout.addRow("Device:", self.tts_device_combo)

        self.tts_temperature_spin = QDoubleSpinBox()
        self.tts_temperature_spin.setRange(0.01, 1.0)
        self.tts_temperature_spin.setSingleStep(0.05)
        tts_layout.addRow("Temperature:", self.tts_temperature_spin)

        self.tts_top_p_spin = QDoubleSpinBox()
        self.tts_top_p_spin.setRange(0.1, 1.0)
        self.tts_top_p_spin.setSingleStep(0.05)
        tts_layout.addRow("Top P:", self.tts_top_p_spin)

        self.tts_speed_spin = QDoubleSpinBox()
        self.tts_speed_spin.setRange(0.5, 2.0)
        self.tts_speed_spin.setSingleStep(0.1)
        tts_layout.addRow("Speed:", self.tts_speed_spin)

        model_dir_layout = QHBoxLayout()
        self.tts_model_dir_edit = QLineEdit()
        model_dir_layout.addWidget(self.tts_model_dir_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(lambda: self._browse_directory(self.tts_model_dir_edit))
        model_dir_layout.addWidget(browse_btn)
        tts_layout.addRow("Model Dir:", model_dir_layout)

        layout.addWidget(tts_group)
        layout.addStretch()
        return widget

    def _create_stt_tab(self) -> QWidget:

        widget = QWidget()
        layout = QVBoxLayout(widget)


        self.stt_enabled_check = QCheckBox("Enable STT (Sherpa-ONNX)")
        layout.addWidget(self.stt_enabled_check)


        stt_group = QGroupBox("STT Configuration")
        stt_layout = QFormLayout(stt_group)

        self.stt_hotkey_edit = QLineEdit()
        stt_layout.addRow("Hotkey:", self.stt_hotkey_edit)

        self.stt_language_combo = QComboBox()
        self.stt_language_combo.addItems(["auto", "zh", "en", "ja", "ko", "yue"])
        stt_layout.addRow("Fixed Language:", self.stt_language_combo)

        self.stt_silence_spin = QDoubleSpinBox()
        self.stt_silence_spin.setRange(0.5, 5.0)
        self.stt_silence_spin.setSingleStep(0.1)
        self.stt_silence_spin.setSuffix(" sec")
        stt_layout.addRow("Silence threshold:", self.stt_silence_spin)

        self.stt_max_duration_spin = QDoubleSpinBox()
        self.stt_max_duration_spin.setRange(1.0, 30.0)
        self.stt_max_duration_spin.setSingleStep(0.5)
        self.stt_max_duration_spin.setSuffix(" sec")
        stt_layout.addRow("Max duration:", self.stt_max_duration_spin)

        model_dir_layout = QHBoxLayout()
        self.stt_model_dir_edit = QLineEdit()
        model_dir_layout.addWidget(self.stt_model_dir_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(lambda: self._browse_directory(self.stt_model_dir_edit))
        model_dir_layout.addWidget(browse_btn)
        stt_layout.addRow("Model Dir:", model_dir_layout)

        layout.addWidget(stt_group)
        layout.addStretch()
        return widget

    def _create_ocr_tab(self) -> QWidget:

        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.ocr_enabled_check = QCheckBox("Enable OCR")
        layout.addWidget(self.ocr_enabled_check)

        self.ocr_vlm_enabled_check = QCheckBox("Enable VLM Image Capture")
        layout.addWidget(self.ocr_vlm_enabled_check)

        ocr_group = QGroupBox("OCR Configuration")
        ocr_layout = QFormLayout(ocr_group)

        self.ocr_provider_combo = QComboBox()
        self.ocr_provider_combo.addItems(["tencent", "baidu"])
        ocr_layout.addRow("Provider:", self.ocr_provider_combo)

        self.ocr_include_process_check = QCheckBox("Include process names and window titles")
        ocr_layout.addRow(self.ocr_include_process_check)

        self.ocr_sentence_limit_spin = QSpinBox()
        self.ocr_sentence_limit_spin.setRange(0, 20)
        self.ocr_sentence_limit_spin.setToolTip("0 to disable the limit note")
        ocr_layout.addRow("Response Sentence Limit:", self.ocr_sentence_limit_spin)

        self.ocr_baidu_api_key_edit = QLineEdit()
        self.ocr_baidu_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ocr_baidu_api_key_label = QLabel("Baidu API Key:")
        ocr_layout.addRow(self.ocr_baidu_api_key_label, self.ocr_baidu_api_key_edit)

        self.ocr_baidu_secret_key_edit = QLineEdit()
        self.ocr_baidu_secret_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ocr_baidu_secret_key_label = QLabel("Baidu Secret Key:")
        ocr_layout.addRow(self.ocr_baidu_secret_key_label, self.ocr_baidu_secret_key_edit)

        self.ocr_tencent_secret_id_edit = QLineEdit()
        self.ocr_tencent_secret_id_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ocr_tencent_secret_id_label = QLabel("Tencent Secret ID:")
        ocr_layout.addRow(self.ocr_tencent_secret_id_label, self.ocr_tencent_secret_id_edit)

        self.ocr_tencent_secret_key_edit = QLineEdit()
        self.ocr_tencent_secret_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ocr_tencent_secret_key_label = QLabel("Tencent Secret Key:")
        ocr_layout.addRow(self.ocr_tencent_secret_key_label, self.ocr_tencent_secret_key_edit)

        self.ocr_provider_combo.currentIndexChanged.connect(self._on_ocr_provider_changed)
        self._update_ocr_provider_fields()

        layout.addWidget(ocr_group)
        layout.addStretch()
        return widget

    def _create_physics_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.physics_enabled_check = QCheckBox("Enable Physics")
        layout.addWidget(self.physics_enabled_check)

        physics_group = QGroupBox("Physics Configuration")
        physics_layout = QFormLayout(physics_group)

        self.physics_refresh_rate_spin = QSpinBox()
        self.physics_refresh_rate_spin.setRange(0, 240)
        self.physics_refresh_rate_spin.setSpecialValueText("Auto")
        physics_layout.addRow("Refresh Rate (0 = Auto):", self.physics_refresh_rate_spin)

        self.physics_gravity_enabled_check = QCheckBox("Enable Gravity")
        physics_layout.addRow(self.physics_gravity_enabled_check)

        self.physics_gravity_spin = QDoubleSpinBox()
        self.physics_gravity_spin.setRange(-5000.0, 5000.0)
        self.physics_gravity_spin.setSingleStep(10.0)
        physics_layout.addRow("Gravity Strength:", self.physics_gravity_spin)

        self.physics_accel_enabled_check = QCheckBox("Enable Acceleration")
        physics_layout.addRow(self.physics_accel_enabled_check)

        self.physics_accel_x_spin = QDoubleSpinBox()
        self.physics_accel_x_spin.setRange(-5000.0, 5000.0)
        self.physics_accel_x_spin.setSingleStep(10.0)
        physics_layout.addRow("Acceleration X:", self.physics_accel_x_spin)

        self.physics_accel_y_spin = QDoubleSpinBox()
        self.physics_accel_y_spin.setRange(-5000.0, 5000.0)
        self.physics_accel_y_spin.setSingleStep(10.0)
        physics_layout.addRow("Acceleration Y:", self.physics_accel_y_spin)

        self.physics_invert_forces_check = QCheckBox("Invert Gravity & Acceleration")
        physics_layout.addRow(self.physics_invert_forces_check)

        self.physics_friction_enabled_check = QCheckBox("Enable Friction")
        physics_layout.addRow(self.physics_friction_enabled_check)

        self.physics_friction_spin = QDoubleSpinBox()
        self.physics_friction_spin.setRange(0.0, 1.0)
        self.physics_friction_spin.setSingleStep(0.01)
        physics_layout.addRow("Friction (0-1):", self.physics_friction_spin)

        self.physics_bounce_enabled_check = QCheckBox("Enable Bounce")
        physics_layout.addRow(self.physics_bounce_enabled_check)

        self.physics_elasticity_spin = QDoubleSpinBox()
        self.physics_elasticity_spin.setRange(0.0, 1.0)
        self.physics_elasticity_spin.setSingleStep(0.05)
        physics_layout.addRow("Bounce Elasticity:", self.physics_elasticity_spin)

        self.physics_max_speed_spin = QDoubleSpinBox()
        self.physics_max_speed_spin.setRange(0.0, 10000.0)
        self.physics_max_speed_spin.setSingleStep(50.0)
        physics_layout.addRow("Max Speed (0 = No Limit):", self.physics_max_speed_spin)

        self.physics_drag_velocity_multiplier_spin = QDoubleSpinBox()
        self.physics_drag_velocity_multiplier_spin.setRange(0.0, 10.0)
        self.physics_drag_velocity_multiplier_spin.setSingleStep(0.1)
        physics_layout.addRow("Drag Velocity Multiplier:", self.physics_drag_velocity_multiplier_spin)

        self.physics_drag_velocity_max_spin = QDoubleSpinBox()
        self.physics_drag_velocity_max_spin.setRange(0.0, 10000.0)
        self.physics_drag_velocity_max_spin.setSingleStep(50.0)
        physics_layout.addRow("Drag Velocity Max (0 = No Limit):", self.physics_drag_velocity_max_spin)

        self.physics_collide_windows_check = QCheckBox("Collide With Other Windows")
        physics_layout.addRow(self.physics_collide_windows_check)

        self.physics_ignore_maximized_check = QCheckBox("Ignore Maximized Windows")
        physics_layout.addRow(self.physics_ignore_maximized_check)

        self.physics_ignore_fullscreen_check = QCheckBox("Ignore Fullscreen Windows")
        physics_layout.addRow(self.physics_ignore_fullscreen_check)

        self.physics_ignore_borderless_check = QCheckBox("Ignore Borderless Fullscreen Windows")
        physics_layout.addRow(self.physics_ignore_borderless_check)

        self.physics_screen_padding_spin = QSpinBox()
        self.physics_screen_padding_spin.setRange(-200, 200)
        physics_layout.addRow("Screen Padding:", self.physics_screen_padding_spin)

        layout.addWidget(physics_group)
        layout.addStretch()
        return widget

    def _load_settings(self):


        self.character_name_edit.setText(self.config.character_name)
        self.username_edit.setText(self.config.username)
        self.always_on_top_check.setChecked(self.config.always_on_top)
        self.always_show_ui_check.setChecked(self.config.always_show_ui)
        self.thinking_enabled_check.setChecked(self.config.thinking_text_enabled)
        self.thinking_switch_check.setChecked(self.config.thinking_text_switch)
        self.thinking_time_spin.setValue(self.config.thinking_text_time)
        self.thinking_switch_time_spin.setValue(self.config.thinking_text_switch_time)
        self.max_rounds_spin.setValue(self.config.max_rounds)
        self.time_context_check.setChecked(self.config.enable_time_context)
        self.ip_context_check.setChecked(self.config.enable_ip_context)
        self.action_bring_to_front_check.setChecked(self.config.action_bring_to_front)


        self.model_select_combo.setCurrentIndex(self.config.model_select - 1)
        self.llm_mode_combo.setCurrentText(self.config.llm_mode)
        self._load_llm_config()
        self.prompt_source_combo.setCurrentText(self.config.prompt_source)
        self.prompt_file_edit.setText(self.config.prompt_file_path)


        self.tts_enabled_check.setChecked(self.config.sovits_enabled)
        self.tts_device_combo.setCurrentText(self.config.sovits_device)
        self.tts_temperature_spin.setValue(self.config.sovits_temperature)
        self.tts_top_p_spin.setValue(self.config.sovits_top_p)
        self.tts_speed_spin.setValue(self.config.sovits_speed)
        self.tts_model_dir_edit.setText(self.config.sovits_model_dir)


        self.stt_enabled_check.setChecked(self.config.stt_enabled)
        self.stt_hotkey_edit.setText(self.config.stt_hotkey)
        self.stt_language_combo.setCurrentText(self.config.stt_language)
        self.stt_silence_spin.setValue(self.config.stt_silence_threshold)
        self.stt_max_duration_spin.setValue(self.config.stt_max_duration)
        self.stt_model_dir_edit.setText(self.config.stt_model_dir)

        self.ocr_enabled_check.setChecked(self.config.ocr_enabled)
        self.ocr_vlm_enabled_check.setChecked(self.config.ocr_vlm_enabled)
        self.ocr_provider_combo.setCurrentText(self.config.ocr_provider)
        self.ocr_include_process_check.setChecked(self.config.ocr_include_process_list)
        self.ocr_sentence_limit_spin.setValue(self.config.ocr_sentence_limit)
        self.ocr_baidu_api_key_edit.setText(self.config.ocr_baidu_api_key)
        self.ocr_baidu_secret_key_edit.setText(self.config.ocr_baidu_secret_key)
        self.ocr_tencent_secret_id_edit.setText(self.config.ocr_tencent_secret_id)
        self.ocr_tencent_secret_key_edit.setText(self.config.ocr_tencent_secret_key)
        self._update_ocr_provider_fields()

        self.physics_enabled_check.setChecked(self.config.physics_enabled)
        self.physics_refresh_rate_spin.setValue(int(self.config.physics_refresh_rate))
        self.physics_gravity_enabled_check.setChecked(self.config.physics_gravity_enabled)
        self.physics_gravity_spin.setValue(self.config.physics_gravity)
        self.physics_accel_enabled_check.setChecked(self.config.physics_accel_enabled)
        self.physics_accel_x_spin.setValue(self.config.physics_accel_x)
        self.physics_accel_y_spin.setValue(self.config.physics_accel_y)
        self.physics_invert_forces_check.setChecked(self.config.physics_invert_forces)
        self.physics_friction_enabled_check.setChecked(self.config.physics_friction_enabled)
        self.physics_friction_spin.setValue(self.config.physics_friction)
        self.physics_bounce_enabled_check.setChecked(self.config.physics_bounce_enabled)
        self.physics_elasticity_spin.setValue(self.config.physics_elasticity)
        self.physics_max_speed_spin.setValue(self.config.physics_max_speed)
        self.physics_drag_velocity_multiplier_spin.setValue(self.config.physics_drag_velocity_multiplier)
        self.physics_drag_velocity_max_spin.setValue(self.config.physics_drag_velocity_max)
        self.physics_collide_windows_check.setChecked(self.config.physics_collide_windows)
        self.physics_ignore_maximized_check.setChecked(self.config.physics_ignore_maximized_windows)
        self.physics_ignore_fullscreen_check.setChecked(self.config.physics_ignore_fullscreen_windows)
        self.physics_ignore_borderless_check.setChecked(self.config.physics_ignore_borderless_fullscreen)
        self.physics_screen_padding_spin.setValue(self.config.physics_screen_padding)

    def _load_llm_config(self):

        llm_config = self.config.get_llm_config()
        self.api_key_edit.setText(llm_config.get("api_key", ""))
        self.base_url_edit.setText(llm_config.get("base_url", ""))
        self.model_name_edit.setText(llm_config.get("model_name", ""))

    def _on_model_changed(self, index: int):


        self._save_current_llm_config()

        self.config.set("General", "model_select", str(index + 1))
        self._load_llm_config()

    def _save_current_llm_config(self):

        model_num = self.model_select_combo.currentIndex() + 1
        section_map = {
            1: "Model_1_OpenAI",
            2: "Model_2_DeepSeek",
            3: "Model_3_Claude",
            4: "Model_4_Kimi",
            5: "Model_5_Gemini",
            6: "Model_6_Grok",
        }
        section = section_map.get(model_num)
        if section:
            self.config.set(section, "api_key", self.api_key_edit.text())
            self.config.set(section, "base_url", self.base_url_edit.text())
            self.config.set(section, "model_name", self.model_name_edit.text())

    def _save_current_ocr_config(self):
        self.config.set("OCR", "provider", self.ocr_provider_combo.currentText())
        self.config.set("OCR", "include_process_list", str(self.ocr_include_process_check.isChecked()).lower())
        self.config.set("OCR", "sentence_limit", str(self.ocr_sentence_limit_spin.value()))
        self.config.set("OCR", "baidu_api_key", self.ocr_baidu_api_key_edit.text())
        self.config.set("OCR", "baidu_secret_key", self.ocr_baidu_secret_key_edit.text())
        self.config.set("OCR", "tencent_secret_id", self.ocr_tencent_secret_id_edit.text())
        self.config.set("OCR", "tencent_secret_key", self.ocr_tencent_secret_key_edit.text())

    def _on_ocr_provider_changed(self):
        self._save_current_ocr_config()
        self._update_ocr_provider_fields()

    def _update_ocr_provider_fields(self):
        provider = self.ocr_provider_combo.currentText()
        baidu_visible = provider == "baidu"
        tencent_visible = provider == "tencent"

        self.ocr_baidu_api_key_label.setVisible(baidu_visible)
        self.ocr_baidu_api_key_edit.setVisible(baidu_visible)
        self.ocr_baidu_secret_key_label.setVisible(baidu_visible)
        self.ocr_baidu_secret_key_edit.setVisible(baidu_visible)

        self.ocr_tencent_secret_id_label.setVisible(tencent_visible)
        self.ocr_tencent_secret_id_edit.setVisible(tencent_visible)
        self.ocr_tencent_secret_key_label.setVisible(tencent_visible)
        self.ocr_tencent_secret_key_edit.setVisible(tencent_visible)

    def _save_settings(self):

        try:

            self.config.set("General", "CharacterName", self.character_name_edit.text())
            self.config.set("Custom", "Username", self.username_edit.text())
            self.config.set("General", "always_on_top", str(self.always_on_top_check.isChecked()).lower())
            self.config.set("General", "always_show_ui", str(self.always_show_ui_check.isChecked()).lower())
            self.config.set("General", "ThinkingText", str(self.thinking_enabled_check.isChecked()).lower())
            self.config.set("General", "ThinkingTextSwitch", str(self.thinking_switch_check.isChecked()).lower())
            self.config.set("General", "ThinkingTextTime", str(self.thinking_time_spin.value()))
            self.config.set("General", "ThinkingTextSwitchTime", str(self.thinking_switch_time_spin.value()))
            self.config.set("History", "max_rounds", str(self.max_rounds_spin.value()))
            self.config.set("Time", "enable_time_context", "1" if self.time_context_check.isChecked() else "0")
            self.config.set("Prompt", "enable_ip_context", str(self.ip_context_check.isChecked()).lower())
            self.config.set("Behavior", "action_bring_to_front", str(self.action_bring_to_front_check.isChecked()).lower())

            self.config.set("General", "model_select", str(self.model_select_combo.currentIndex() + 1))
            self.config.set("General", "llm_mode", self.llm_mode_combo.currentText())
            self._save_current_llm_config()
            self.config.set("Prompt", "source", self.prompt_source_combo.currentText())
            self.config.set("Prompt", "file_path", self.prompt_file_edit.text())


            self.config.set("SoVITS", "enabled", "1" if self.tts_enabled_check.isChecked() else "0")
            self.config.set("SoVITS", "device", self.tts_device_combo.currentText())
            self.config.set("SoVITS", "temperature", str(self.tts_temperature_spin.value()))
            self.config.set("SoVITS", "top_p", str(self.tts_top_p_spin.value()))
            self.config.set("SoVITS", "speed", str(self.tts_speed_spin.value()))
            self.config.set("SoVITS", "model_dir", self.tts_model_dir_edit.text())


            self.config.set("STT", "enabled", "1" if self.stt_enabled_check.isChecked() else "0")
            self.config.set("STT", "hotkey", self.stt_hotkey_edit.text())
            self.config.set("STT", "language", self.stt_language_combo.currentText())
            self.config.set("STT", "silence_threshold", str(self.stt_silence_spin.value()))
            self.config.set("STT", "max_duration", str(self.stt_max_duration_spin.value()))
            self.config.set("STT", "model_dir", self.stt_model_dir_edit.text())

            self.config.set("OCR", "enabled", str(self.ocr_enabled_check.isChecked()).lower())
            self.config.set("OCR", "vlm_enabled", str(self.ocr_vlm_enabled_check.isChecked()).lower())
            self.config.set("OCR", "provider", self.ocr_provider_combo.currentText())
            self.config.set("OCR", "include_process_list", str(self.ocr_include_process_check.isChecked()).lower())
            self.config.set("OCR", "sentence_limit", str(self.ocr_sentence_limit_spin.value()))
            self.config.set("OCR", "baidu_api_key", self.ocr_baidu_api_key_edit.text())
            self.config.set("OCR", "baidu_secret_key", self.ocr_baidu_secret_key_edit.text())
            self.config.set("OCR", "tencent_secret_id", self.ocr_tencent_secret_id_edit.text())
            self.config.set("OCR", "tencent_secret_key", self.ocr_tencent_secret_key_edit.text())

            self.config.set("Physics", "enabled", str(self.physics_enabled_check.isChecked()).lower())
            self.config.set("Physics", "refresh_rate", str(self.physics_refresh_rate_spin.value()))
            self.config.set("Physics", "gravity_enabled", str(self.physics_gravity_enabled_check.isChecked()).lower())
            self.config.set("Physics", "gravity", str(self.physics_gravity_spin.value()))
            self.config.set("Physics", "accel_enabled", str(self.physics_accel_enabled_check.isChecked()).lower())
            self.config.set("Physics", "accel_x", str(self.physics_accel_x_spin.value()))
            self.config.set("Physics", "accel_y", str(self.physics_accel_y_spin.value()))
            self.config.set("Physics", "invert_forces", str(self.physics_invert_forces_check.isChecked()).lower())
            self.config.set("Physics", "friction_enabled", str(self.physics_friction_enabled_check.isChecked()).lower())
            self.config.set("Physics", "friction", str(self.physics_friction_spin.value()))
            self.config.set("Physics", "bounce_enabled", str(self.physics_bounce_enabled_check.isChecked()).lower())
            self.config.set("Physics", "elasticity", str(self.physics_elasticity_spin.value()))
            self.config.set("Physics", "max_speed", str(self.physics_max_speed_spin.value()))
            self.config.set("Physics", "drag_velocity_multiplier", str(self.physics_drag_velocity_multiplier_spin.value()))
            self.config.set("Physics", "drag_velocity_max", str(self.physics_drag_velocity_max_spin.value()))
            self.config.set("Physics", "collide_windows", str(self.physics_collide_windows_check.isChecked()).lower())
            self.config.set("Physics", "ignore_maximized_windows", str(self.physics_ignore_maximized_check.isChecked()).lower())
            self.config.set("Physics", "ignore_fullscreen_windows", str(self.physics_ignore_fullscreen_check.isChecked()).lower())
            self.config.set("Physics", "ignore_borderless_fullscreen", str(self.physics_ignore_borderless_check.isChecked()).lower())
            self.config.set("Physics", "screen_padding", str(self.physics_screen_padding_spin.value()))

            self.config.save()

            QMessageBox.information(self, "Success", "Settings saved successfully!")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    def _browse_prompt_file(self):

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Prompt File",
            str(self.project_root / "prompts"),
            "Text Files (*.txt);;All Files (*.*)"
        )
        if file_path:

            try:
                rel_path = Path(file_path).relative_to(self.project_root)
                self.prompt_file_edit.setText(f"./{rel_path}")
            except ValueError:
                self.prompt_file_edit.setText(file_path)

    def _browse_directory(self, line_edit: QLineEdit):

        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Directory",
            str(self.project_root)
        )
        if dir_path:
            try:
                rel_path = Path(dir_path).relative_to(self.project_root)
                line_edit.setText(f"./{rel_path}")
            except ValueError:
                line_edit.setText(dir_path)
