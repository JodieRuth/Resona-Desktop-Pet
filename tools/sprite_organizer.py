import sys
import os
import json
import shutil
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QListWidget, QPushButton, QLineEdit, 
                             QLabel, QFileDialog, QMessageBox, QScrollArea, QGridLayout, QComboBox)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

class SpriteOrganizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Resona Sprite Organizer")
        self.resize(1000, 700)
        
        self.source_dir = None
        self.outfit_name = ""
        self.items = [] 
        self.EMOTIONS = [
            "<E:smile>", "<E:serious>", "<E:angry>", "<E:sad>", 
            "<E:thinking>", "<E:surprised>", "<E:dislike>", 
            "<E:smirk>", "<E:embarrassed>"
        ]
        
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.open_btn = QPushButton("1. Open Folder")
        self.open_btn.clicked.connect(self.open_folder)
        self.outfit_edit = QLineEdit()
        self.outfit_edit.setPlaceholderText("Enter Outfit Name (e.g. risona_outfit_01)")
        top.addWidget(self.open_btn)
        top.addWidget(QLabel("Outfit Name:"))
        top.addWidget(self.outfit_edit)
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
            
            img_label = QLabel()
            pix = QPixmap(str(f)).scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio)
            img_label.setPixmap(pix)
            img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            emo_combo = QComboBox()
            emo_combo.addItems(self.EMOTIONS)
            emo_combo.currentTextChanged.connect(lambda t, idx=i: self.update_emo(idx, t))
            
            vbox.addWidget(img_label)
            vbox.addWidget(emo_combo)
            vbox.addWidget(QLabel(f.name))
            
            self.grid.addWidget(container, i // 4, i % 4)

    def update_emo(self, idx, text):
        self.items[idx]['emotion'] = text

    def process_sprites(self):
        if not self.source_dir: return
        self.outfit_name = self.outfit_edit.text().strip()
        if not self.outfit_name:
            QMessageBox.warning(self, "Error", "Please enter outfit name")
            return

        target_root = Path("resona_desktop_pet/ui/assets/modes") / self.outfit_name
        target_root.mkdir(parents=True, exist_ok=True)

        sum_data = {}
        
        emo_groups = {}
        for item in self.items:
            emo = item['emotion']
            if emo not in emo_groups: emo_groups[emo] = []
            emo_groups[emo].append(item)

        for emo, group in emo_groups.items():
            sum_data[emo] = []
            for i, item in enumerate(group):
                clean_emo = emo.replace("<E:", "").replace(">", "").replace(":", "_")
                new_name = f"{self.outfit_name}_{clean_emo}_{i:02d}"
                dest_path = target_root / (new_name + item['path'].suffix)
                
                shutil.copy2(item['path'], dest_path)
                sum_data[emo].append(new_name)

        with open(target_root / "sum.json", "w", encoding="utf-8") as f:
            json.dump(sum_data, f, indent=4, ensure_ascii=False)

        QMessageBox.information(self, "Success", f"Outfit saved to {target_root}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SpriteOrganizer()
    window.show()
    sys.exit(app.exec())
