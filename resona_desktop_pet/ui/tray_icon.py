from pathlib import Path
from typing import Optional, Callable
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap, QAction
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from ..config import ConfigManager

class TrayIcon(QSystemTrayIcon):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.config = parent.config
        self.project_root = Path(self.config.config_path).parent
        self._setup_icon()
        self._setup_menu()
        self.activated.connect(self._on_activated)

    def _setup_icon(self):
        icon_name = self.config.get("General", "tray_icon_path", fallback="icon.ico")
        icon_path = self.project_root / icon_name
        if not icon_path.exists():
            pack_icon = self.config.pack_manager.packs_dir / self.config.pack_manager.active_pack_id / "icon.ico"
            if pack_icon.exists(): icon_path = pack_icon
        
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.GlobalColor.transparent)
            self.setIcon(QIcon(pixmap))
        self.setToolTip(f"Resona Desktop Pet - {self.config.character_name}")

    def _setup_menu(self):
        menu = QMenu()
        menu.setStyleSheet("QMenu { background-color: #2d2d2d; border: 1px solid #555; border-radius: 5px; padding: 5px; } QMenu::item { color: white; padding: 8px 25px; border-radius: 3px; } QMenu::item:selected { background-color: #404040; } QMenu::separator { height: 1px; background: #555; margin: 5px 10px; }")
        
        show_action = QAction("Show/Hide", self)
        show_action.triggered.connect(self._on_show)
        menu.addAction(show_action)
        menu.addSeparator()
        
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._on_settings)
        menu.addAction(settings_action)
        menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self._on_exit)
        menu.addAction(exit_action)
        self.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick: self._on_show()

    def _on_show(self):
        if self.main_window:
            if self.main_window.isVisible() and self.main_window.windowOpacity() > 0:
                self.main_window.manual_hide()
            else:
                self.main_window.manual_show()

    def _on_settings(self):
        if self.main_window: self.main_window.settings_requested.emit()

    def _on_exit(self):
        if self.main_window and self.main_window.controller and hasattr(self.main_window.controller, "force_exit"):
            self.main_window.controller.force_exit()
            return
        if self.main_window and self.main_window.controller:
            self.main_window.controller.cleanup()
        QApplication.quit()

    def add_menu_action(self, text: str, callback: Callable):
        action = QAction(text, self)
        action.triggered.connect(callback)
        self.contextMenu().insertAction(self.contextMenu().actions()[0], action)
        self.contextMenu().insertSeparator(self.contextMenu().actions()[1])

    def show_message(self, title: str, message: str, icon_type=None):
        if icon_type is None: icon_type = QSystemTrayIcon.MessageIcon.Information
        self.showMessage(title, message, icon_type, 3000)
