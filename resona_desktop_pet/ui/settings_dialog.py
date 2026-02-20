

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
        self.current_model_num = -1

        self.setWindowTitle("Resona Desktop Pet - Settings")
        self.setMinimumSize(980, 900)
        self.resize(980, 900)
        self.setStyleSheet("""
            QDialog {
                background-color: #1f1f1f;
            }
            QLabel {
                color: #e6e6e6;
            }
            QGroupBox {
                color: #e6e6e6;
                border: 1px solid #3a3a3a;
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
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 3px;
                color: #ffffff;
                padding: 5px;
                min-height: 25px;
            }
            QSpinBox::up-button, QSpinBox::down-button,
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
                width: 0px;
                height: 0px;
                border: none;
            }
            QSpinBox::up-arrow, QSpinBox::down-arrow,
            QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {
                width: 0px;
                height: 0px;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #5a5a5a;
            }
            QCheckBox {
                color: #ffffff;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QPushButton {
                background-color: #3a3a3a;
                color: #ffffff;
                border: none;
                border-radius: 3px;
                padding: 8px 20px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2f2f2f;
            }
            QTabWidget::pane {
                border: 1px solid #3a3a3a;
                border-radius: 5px;
                background-color: #242424;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #cfcfcf;
                padding: 8px 20px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #3a3a3a;
                color: #ffffff;
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
        tabs.addTab(self._create_appearance_tab(), "Appearance")
        tabs.addTab(self._create_behavior_tab(), "Behavior")
        tabs.addTab(self._create_llm_tab(), "LLM")
        tabs.addTab(self._create_tts_tab(), "TTS")
        tabs.addTab(self._create_stt_tab(), "STT")
        tabs.addTab(self._create_ocr_tab(), "OCR")
        tabs.addTab(self._create_weather_tab(), "Weather")
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

    def _make_form_layout(self, parent: QWidget) -> QFormLayout:
        layout = QFormLayout(parent)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(10)
        layout.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.setFormAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        return layout

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        char_group = QGroupBox("Character")
        char_layout = self._make_form_layout(char_group)

        self.character_name_edit = QLineEdit()
        char_layout.addRow("Character Name:", self.character_name_edit)

        self.username_edit = QLineEdit()
        char_layout.addRow("Your Name:", self.username_edit)

        self.use_pack_settings_check = QCheckBox("Use Pack Settings")
        self.use_pack_settings_check.setToolTip("Override Name, User Name, Prompt and TTS Language with pack defaults.")
        char_layout.addRow(self.use_pack_settings_check)

        self.always_on_top_check = QCheckBox("Always on top")
        char_layout.addRow(self.always_on_top_check)

        self.always_show_ui_check = QCheckBox("Always show (no fade)")
        char_layout.addRow(self.always_show_ui_check)
        
        self.global_show_hotkey_edit = QLineEdit()
        self.global_show_hotkey_edit.setPlaceholderText("e.g. ctrl+alt+0")
        char_layout.addRow("Show/Focus Hotkey (need restart):", self.global_show_hotkey_edit)

        icon_layout = QHBoxLayout()
        self.tray_icon_path_edit = QLineEdit()
        icon_layout.addWidget(self.tray_icon_path_edit)
        browse_icon_btn = QPushButton("Browse")
        browse_icon_btn.clicked.connect(lambda: self._browse_file(self.tray_icon_path_edit, "Icon Files (*.ico *.png *.jpg)"))
        icon_layout.addWidget(browse_icon_btn)
        char_layout.addRow("Tray Icon (need restart):", icon_layout)

        layout.addWidget(char_group)

        thinking_group = QGroupBox("Thinking Text")
        thinking_layout = self._make_form_layout(thinking_group)

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
        history_layout = self._make_form_layout(history_group)

        self.max_rounds_spin = QSpinBox()
        self.max_rounds_spin.setRange(0, 50)
        self.max_rounds_spin.setSpecialValueText("Disabled")
        history_layout.addRow("Max rounds:", self.max_rounds_spin)

        self.time_context_check = QCheckBox("Include time context")
        history_layout.addRow(self.time_context_check)

        self.ip_context_check = QCheckBox("Include user IP/Location")
        history_layout.addRow(self.ip_context_check)

        layout.addWidget(history_group)

        layout.addStretch()
        return widget

    def _create_appearance_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        size_group = QGroupBox("Window Size")
        size_layout = self._make_form_layout(size_group)
        
        self.width_spin = QSpinBox()
        self.width_spin.setRange(100, 2000)
        self.width_spin.setSingleStep(10)
        size_layout.addRow("Window Width:", self.width_spin)
        
        self.height_spin = QSpinBox()
        self.height_spin.setRange(100, 2000)
        self.height_spin.setSingleStep(10)
        size_layout.addRow("Window Height:", self.height_spin)
        
        layout.addWidget(size_group)
        
        ui_group = QGroupBox("Dialogue UI")
        ui_layout = self._make_form_layout(ui_group)
        
        self.dialogue_width_spin = QSpinBox()
        self.dialogue_width_spin.setRange(100, 1000)
        self.dialogue_width_spin.setSingleStep(10)
        ui_layout.addRow("Dialogue Width:", self.dialogue_width_spin)
        
        self.dialogue_height_spin = QSpinBox()
        self.dialogue_height_spin.setRange(50, 500)
        self.dialogue_height_spin.setSingleStep(10)
        ui_layout.addRow("Dialogue Min Height:", self.dialogue_height_spin)
        
        self.font_scale_spin = QDoubleSpinBox()
        self.font_scale_spin.setRange(0.5, 3.0)
        self.font_scale_spin.setSingleStep(0.1)
        ui_layout.addRow("Font Scale:", self.font_scale_spin)
        
        self.dialog_color_edit = QLineEdit()
        self.dialog_color_edit.setPlaceholderText("RGB (0,0,0) or Hex (#000000)")
        ui_layout.addRow("Dialog Color:", self.dialog_color_edit)
        
        self.dialog_opacity_spin = QSpinBox()
        self.dialog_opacity_spin.setRange(0, 100)
        self.dialog_opacity_spin.setSuffix("%")
        ui_layout.addRow("Dialog Opacity:", self.dialog_opacity_spin)
        
        self.dialog_text_color_edit = QLineEdit()
        self.dialog_text_color_edit.setPlaceholderText("RGB (255,255,255) or Hex (#FFFFFF)")
        ui_layout.addRow("Text Color:", self.dialog_text_color_edit)
        
        font_layout = QHBoxLayout()
        self.dialog_font_edit = QLineEdit()
        self.dialog_font_edit.setPlaceholderText("Leave empty for system default")
        font_layout.addWidget(self.dialog_font_edit)
        browse_font_btn = QPushButton("Browse")
        browse_font_btn.clicked.connect(lambda: self._browse_file(self.dialog_font_edit, "Font Files (*.ttf *.otf)"))
        font_layout.addWidget(browse_font_btn)
        ui_layout.addRow("Font File:", font_layout)
        
        layout.addWidget(ui_group)
        
        layout.addStretch()
        return widget

    def _create_behavior_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        behavior_group = QGroupBox("Behavior Monitor")
        behavior_layout = self._make_form_layout(behavior_group)
        
        self.behavior_enabled_check = QCheckBox("Enable Behavior Monitor")
        behavior_layout.addRow(self.behavior_enabled_check)
        
        self.behavior_interval_spin = QDoubleSpinBox()
        self.behavior_interval_spin.setRange(0.1, 60.0)
        self.behavior_interval_spin.setSingleStep(0.5)
        self.behavior_interval_spin.setSuffix(" sec")
        behavior_layout.addRow("Check Interval:", self.behavior_interval_spin)
        
        self.action_bring_to_front_check = QCheckBox("Bring to front on action")
        behavior_layout.addRow(self.action_bring_to_front_check)
        
        self.trigger_cooldown_spin = QDoubleSpinBox()
        self.trigger_cooldown_spin.setRange(0.0, 300.0)
        self.trigger_cooldown_spin.setSingleStep(1.0)
        self.trigger_cooldown_spin.setSuffix(" sec")
        behavior_layout.addRow("Global Trigger Cooldown:", self.trigger_cooldown_spin)
        
        self.post_busy_delay_spin = QDoubleSpinBox()
        self.post_busy_delay_spin.setRange(0.0, 60.0)
        self.post_busy_delay_spin.setSingleStep(0.5)
        self.post_busy_delay_spin.setSuffix(" sec")
        behavior_layout.addRow("Post-Busy Delay:", self.post_busy_delay_spin)
        
        layout.addWidget(behavior_group)
        
        layout.addStretch()
        return widget

    def _create_weather_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        weather_group = QGroupBox("Weather Configuration")
        weather_layout = self._make_form_layout(weather_group)
        
        self.weather_enabled_check = QCheckBox("Enable Weather Check")
        weather_layout.addRow(self.weather_enabled_check)
        
        self.weather_api_key_edit = QLineEdit()
        self.weather_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        weather_layout.addRow("WeatherAPI Key:", self.weather_api_key_edit)
        
        layout.addWidget(weather_group)
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
        model_layout = self._make_form_layout(model_group)

        self.model_select_combo = QComboBox()
        self.model_select_combo.addItems([
            "1: OpenAI (ChatGPT)",
            "2: DeepSeek",
            "3: Claude (Anthropic)",
            "4: Kimi (Moonshot)",
            "5: Gemini (Google)",
            "6: Grok (xAI)",
            "7: Qwen (Aliyun)",
            "8: GitHub Models",
            "9: OpenAI Compatible"
        ])
        self.model_select_combo.currentIndexChanged.connect(self._on_model_changed)
        model_layout.addRow("Provider (need restart):", self.model_select_combo)

        self.llm_mode_combo = QComboBox()
        self.llm_mode_combo.addItems(["cloud", "local"])
        model_layout.addRow("Mode (need restart):", self.llm_mode_combo)

        layout.addWidget(model_group)


        api_group = QGroupBox("API Configuration")
        api_layout = self._make_form_layout(api_group)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_layout.addRow("API Key (need restart):", self.api_key_edit)

        self.base_url_edit = QLineEdit()
        api_layout.addRow("Base URL (need restart):", self.base_url_edit)

        self.model_name_edit = QLineEdit()
        api_layout.addRow("Model Name (need restart):", self.model_name_edit)

        layout.addWidget(api_group)


        prompt_group = QGroupBox("Prompt")
        prompt_layout = self._make_form_layout(prompt_group)

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
        tts_layout = self._make_form_layout(tts_group)

        self.tts_device_combo = QComboBox()
        self.tts_device_combo.addItems(["cuda", "cpu"])
        tts_layout.addRow("Device (need restart):", self.tts_device_combo)

        self.tts_temperature_spin = QDoubleSpinBox()
        self.tts_temperature_spin.setRange(0.01, 1.0)
        self.tts_temperature_spin.setSingleStep(0.05)
        tts_layout.addRow("Temperature:", self.tts_temperature_spin)

        self.tts_top_p_spin = QDoubleSpinBox()
        self.tts_top_p_spin.setRange(0.1, 1.0)
        self.tts_top_p_spin.setSingleStep(0.05)
        tts_layout.addRow("Top P:", self.tts_top_p_spin)

        self.tts_top_k_spin = QSpinBox()
        self.tts_top_k_spin.setRange(1, 200)
        tts_layout.addRow("Top K:", self.tts_top_k_spin)

        self.tts_speed_spin = QDoubleSpinBox()
        self.tts_speed_spin.setRange(0.5, 2.0)
        self.tts_speed_spin.setSingleStep(0.1)
        tts_layout.addRow("Speed:", self.tts_speed_spin)

        self.tts_text_split_combo = QComboBox()
        self.tts_text_split_combo.addItems(["cut0", "cut1", "cut2", "cut3", "cut4", "cut5"])
        tts_layout.addRow("Text Split Method:", self.tts_text_split_combo)

        self.tts_fragment_interval_spin = QDoubleSpinBox()
        self.tts_fragment_interval_spin.setRange(0.0, 5.0)
        self.tts_fragment_interval_spin.setSingleStep(0.05)
        self.tts_fragment_interval_spin.setSuffix(" sec")
        tts_layout.addRow("Fragment Interval:", self.tts_fragment_interval_spin)

        model_dir_layout = QHBoxLayout()
        self.tts_model_dir_edit = QLineEdit()
        model_dir_layout.addWidget(self.tts_model_dir_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(lambda: self._browse_directory(self.tts_model_dir_edit))
        model_dir_layout.addWidget(browse_btn)
        tts_layout.addRow("Model Dir (need restart):", model_dir_layout)

        layout.addWidget(tts_group)
        layout.addStretch()
        return widget

    def _create_stt_tab(self) -> QWidget:

        widget = QWidget()
        layout = QVBoxLayout(widget)


        self.stt_enabled_check = QCheckBox("Enable STT (Sherpa-ONNX)")
        layout.addWidget(self.stt_enabled_check)


        stt_group = QGroupBox("STT Configuration")
        stt_layout = self._make_form_layout(stt_group)

        self.stt_hotkey_edit = QLineEdit()
        stt_layout.addRow("Hotkey (need restart):", self.stt_hotkey_edit)

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
        stt_layout.addRow("Model Dir (need restart):", model_dir_layout)

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
        ocr_layout = self._make_form_layout(ocr_group)

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
        physics_layout = self._make_form_layout(physics_group)

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
        self.use_pack_settings_check.setChecked(self.config.use_pack_settings)
        self.always_on_top_check.setChecked(self.config.always_on_top)
        self.always_show_ui_check.setChecked(self.config.always_show_ui)
        self.global_show_hotkey_edit.setText(self.config.global_show_hotkey)
        self.tray_icon_path_edit.setText(self.config.get("General", "tray_icon_path", ""))

        self.thinking_enabled_check.setChecked(self.config.thinking_text_enabled)
        self.thinking_switch_check.setChecked(self.config.thinking_text_switch)
        self.thinking_time_spin.setValue(self.config.thinking_text_time)
        self.thinking_switch_time_spin.setValue(self.config.thinking_text_switch_time)
        self.max_rounds_spin.setValue(self.config.max_rounds)
        self.time_context_check.setChecked(self.config.enable_time_context)
        self.ip_context_check.setChecked(self.config.enable_ip_context)
        
        self.width_spin.setValue(self.config.sprite_width)
        self.height_spin.setValue(self.config.sprite_height)
        self.dialogue_width_spin.setValue(self.config.dialogue_width)
        self.dialogue_height_spin.setValue(self.config.dialogue_height)
        self.font_scale_spin.setValue(self.config.font_scale)
        self.dialog_color_edit.setText(self.config.dialog_color)
        self.dialog_opacity_spin.setValue(self.config.dialog_opacity)
        self.dialog_font_edit.setText(self.config.dialog_font)
        self.dialog_text_color_edit.setText(self.config.dialog_text_color)
        
        self.behavior_enabled_check.setChecked(self.config.behavior_enabled)
        self.behavior_interval_spin.setValue(self.config.behavior_interval)
        self.action_bring_to_front_check.setChecked(self.config.action_bring_to_front)
        self.trigger_cooldown_spin.setValue(self.config.trigger_cooldown)
        self.post_busy_delay_spin.setValue(self.config.post_busy_delay)
        
        self.weather_enabled_check.setChecked(self.config.weather_enabled)
        self.weather_api_key_edit.setText(self.config.weather_api_key)


        self.model_select_combo.blockSignals(True)
        self.model_select_combo.setCurrentIndex(self.config.model_select - 1)
        self.current_model_num = self.config.model_select
        self.model_select_combo.blockSignals(False)
        self.llm_mode_combo.setCurrentText(self.config.llm_mode)
        self._load_llm_config()
        self.prompt_source_combo.setCurrentText(self.config.prompt_source)
        self.prompt_file_edit.setText(self.config.prompt_file_path)


        self.tts_enabled_check.setChecked(self.config.sovits_enabled)
        self.tts_device_combo.setCurrentText(self.config.sovits_device)
        self.tts_temperature_spin.setValue(self.config.sovits_temperature)
        self.tts_top_p_spin.setValue(self.config.sovits_top_p)
        self.tts_top_k_spin.setValue(self.config.sovits_top_k)
        self.tts_speed_spin.setValue(self.config.sovits_speed)
        self.tts_text_split_combo.setCurrentText(self.config.sovits_text_split_method)
        self.tts_fragment_interval_spin.setValue(self.config.sovits_fragment_interval)
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
        if self.current_model_num != -1:
            self._save_current_llm_config(self.current_model_num)

        self.current_model_num = index + 1
        self.config.set("General", "model_select", str(index + 1))
        self._load_llm_config()

    def _save_current_llm_config(self, model_num=None):
        if model_num is None:
            model_num = self.model_select_combo.currentIndex() + 1
        self.section_map = {
            1: "Model_1_OpenAI",
            2: "Model_2_DeepSeek",
            3: "Model_3_Claude",
            4: "Model_4_Kimi",
            5: "Model_5_Gemini",
            6: "Model_6_Grok",
            7: "Model_7_Qwen",
            8: "Model_8_GitHub",
            9: "Model_9_OpenAI_Compatible",
        }
        
        if hasattr(self.config, 'config'):
            for i in range(7, 10):
                prefix = f"Model_{i}"
                for section in self.config.config.sections():
                    if section.startswith(prefix):
                        self.section_map[i] = section
                        break
        section = self.section_map.get(model_num)
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
            self.config.set("General", "use_pack_settings", str(self.use_pack_settings_check.isChecked()).lower())
            self.config.set("General", "always_on_top", str(self.always_on_top_check.isChecked()).lower())
            self.config.set("General", "always_show_ui", str(self.always_show_ui_check.isChecked()).lower())
            self.config.set("General", "global_show_hotkey", self.global_show_hotkey_edit.text())
            self.config.set("General", "tray_icon_path", self.tray_icon_path_edit.text())
            
            self.config.set("General", "ThinkingText", str(self.thinking_enabled_check.isChecked()).lower())
            self.config.set("General", "ThinkingTextSwitch", str(self.thinking_switch_check.isChecked()).lower())
            self.config.set("General", "ThinkingTextTime", str(self.thinking_time_spin.value()))
            self.config.set("General", "ThinkingTextSwitchTime", str(self.thinking_switch_time_spin.value()))
            self.config.set("History", "max_rounds", str(self.max_rounds_spin.value()))
            self.config.set("Time", "enable_time_context", "1" if self.time_context_check.isChecked() else "0")
            self.config.set("Prompt", "enable_ip_context", str(self.ip_context_check.isChecked()).lower())
            
            self.config.set("General", "width", str(self.width_spin.value()))
            self.config.set("General", "height", str(self.height_spin.value()))
            self.config.set("General", "dialogue_width", str(self.dialogue_width_spin.value()))
            self.config.set("General", "dialogue_height", str(self.dialogue_height_spin.value()))
            self.config.set("General", "font_scale", str(self.font_scale_spin.value()))
            self.config.set("General", "dialog_color", self.dialog_color_edit.text())
            self.config.set("General", "dialog_opacity", str(self.dialog_opacity_spin.value()))
            self.config.set("General", "dialog_font", self.dialog_font_edit.text())
            self.config.set("General", "dialog_text_color", self.dialog_text_color_edit.text())
            
            self.config.set("Behavior", "enabled", str(self.behavior_enabled_check.isChecked()).lower())
            self.config.set("Behavior", "interval", str(self.behavior_interval_spin.value()))
            self.config.set("Behavior", "action_bring_to_front", str(self.action_bring_to_front_check.isChecked()).lower())
            self.config.set("Behavior", "trigger_cooldown", str(self.trigger_cooldown_spin.value()))
            self.config.set("Behavior", "post_busy_delay", str(self.post_busy_delay_spin.value()))
            
            self.config.set("Weather", "enabled", str(self.weather_enabled_check.isChecked()).lower())
            self.config.set("Weather", "api_key", self.weather_api_key_edit.text())

            self.config.set("General", "model_select", str(self.model_select_combo.currentIndex() + 1))
            self.config.set("General", "llm_mode", self.llm_mode_combo.currentText())
            self._save_current_llm_config()
            self.config.set("Prompt", "source", self.prompt_source_combo.currentText())
            self.config.set("Prompt", "file_path", self.prompt_file_edit.text())


            self.config.set("SoVITS", "enabled", "1" if self.tts_enabled_check.isChecked() else "0")
            self.config.set("SoVITS", "device", self.tts_device_combo.currentText())
            self.config.set("SoVITS", "temperature", str(self.tts_temperature_spin.value()))
            self.config.set("SoVITS", "top_p", str(self.tts_top_p_spin.value()))
            self.config.set("SoVITS", "top_k", str(self.tts_top_k_spin.value()))
            self.config.set("SoVITS", "speed", str(self.tts_speed_spin.value()))
            self.config.set("SoVITS", "text_split_method", self.tts_text_split_combo.currentText())
            self.config.set("SoVITS", "fragment_interval", str(self.tts_fragment_interval_spin.value()))
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
