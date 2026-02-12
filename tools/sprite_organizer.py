import sys
import os
import json
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel, QFileDialog, 
                             QMessageBox, QScrollArea, QGridLayout, QComboBox)
from PySide6.QtGui import QPixmap, QMouseEvent
from PySide6.QtCore import Qt, Signal, QEvent

class ImagePreviewer(QLabel):
    def __init__(self, pixmap, parent=None):
        super().__init__(None) 
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        
        screen_size = QApplication.primaryScreen().size()
        max_w, max_h = screen_size.width() * 0.8, screen_size.height() * 0.8
        
        scaled_pix = pixmap
        if pixmap.width() > max_w or pixmap.height() > max_h:
            scaled_pix = pixmap.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
        self.setPixmap(scaled_pix)
        self.adjustSize()
        self.move((screen_size.width() - self.width()) // 2, (screen_size.height() - self.height()) // 2)

    def mousePressEvent(self, event: QMouseEvent):
        self.close()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow():
                self.close()
        super().changeEvent(event)

class ClickableLabel(QLabel):
    clicked = Signal(str)
    
    def __init__(self, path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = path
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.path)

class SpriteOrganizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Resona Sprite Organizer")
        self.resize(1000, 700)
        
        self.source_dir = None
        self.items = [] 
        self.EMOTIONS = [
            "<E:smile>", "<E:serious>", "<E:angry>", "<E:sad>", 
            "<E:thinking>", "<E:surprised>", "<E:dislike>", 
            "<E:smirk>", "<E:embarrassed>"
        ]
        self.preview_window = None
        
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.open_btn = QPushButton("1. Open Folder")
        self.open_btn.clicked.connect(self.open_folder)
        top.addWidget(self.open_btn)
        layout.addLayout(top)

        self.scroll = QScrollArea()
        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.grid_widget)
        layout.addWidget(self.scroll)

        self.save_btn = QPushButton("2. Rename & Generate sum.json")
        self.save_btn.clicked.connect(self.process_sprites)
        layout.addWidget(self.save_btn)

    def open_folder(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Sprite Folder")
        if not dir_path: return
        self.source_dir = Path(dir_path)
        
        self.items = []
        valid_exts = ['.png', '.jpg', '.webp']
        files = [f for f in self.source_dir.iterdir() if f.suffix.lower() in valid_exts]
        
        for i in reversed(range(self.grid.count())): 
            self.grid.itemAt(i).widget().setParent(None)

        for i, f in enumerate(files):
            item = {'path': f, 'emotion': self.EMOTIONS[0]}
            self.items.append(item)
            
            container = QWidget()
            vbox = QVBoxLayout(container)
            
            img_label = ClickableLabel(str(f))
            pix = QPixmap(str(f)).scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio)
            img_label.setPixmap(pix)
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            img_label.clicked.connect(self.show_preview)
            
            emo_combo = QComboBox()
            emo_combo.addItems(self.EMOTIONS)
            emo_combo.currentTextChanged.connect(lambda t, idx=i: self.update_emo(idx, t))
            
            vbox.addWidget(img_label)
            vbox.addWidget(emo_combo)
            vbox.addWidget(QLabel(f.name))
            
            self.grid.addWidget(container, i // 4, i % 4)

    def update_emo(self, idx, text):
        self.items[idx]['emotion'] = text

    def show_preview(self, path):
        pix = QPixmap(path)
        if not pix.isNull():
            self.preview_window = ImagePreviewer(pix)
            self.preview_window.show()
            self.preview_window.activateWindow()

    def process_sprites(self):
        if not self.source_dir: return
        
        target_root = self.source_dir
        sum_data = {}
        
        emo_groups = {}
        for item in self.items:
            emo = item['emotion']
            if emo not in emo_groups: emo_groups[emo] = []
            emo_groups[emo].append(item)

        for emo, group in emo_groups.items():
            sum_data[emo] = []
            for item in group:
                name_in_json = item['path'].stem
                sum_data[emo].append(name_in_json)

        with open(target_root / "sum.json", "w", encoding="utf-8") as f:
            json.dump(sum_data, f, indent=4, ensure_ascii=False)

        QMessageBox.information(self, "Success", f"sum.json saved to {target_root}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpriteOrganizer()
    window.show()
    sys.exit(app.exec())
