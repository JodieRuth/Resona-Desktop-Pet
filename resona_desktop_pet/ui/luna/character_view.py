import json
import random
import re
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, QSize, QRect, Signal, QPoint
from PySide6.QtGui import QPainter, QPaintEvent, QMouseEvent, QPixmap, QColor
from PySide6.QtWidgets import QWidget

class CharacterView(QWidget):
    leftClicked = Signal()
    rightClicked = Signal()
    
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setSizePolicy(self.sizePolicy().Policy.Fixed, self.sizePolicy().Policy.Fixed)
        self._pixmap: QPixmap = QPixmap()
        self._scale: float = 1.0
        self.project_root: Optional[Path] = None
        self.current_outfit = "risona_outfit_00"
        self.current_emotion = "<E:smile>"
        self.emotion_map: Dict[str, List[str]] = {}
        
    def setup(self, project_root: Path, default_outfit: str = "risona_outfit_00"):
        self.project_root = project_root
        self.emotion_map = {}
        self.current_outfit = default_outfit
        print(f"[CharacterView] Setup with outfit: {default_outfit}")
        self._load_outfit(self.current_outfit)

    def _resolve_pack_outfit(self, requested: str) -> str:
        try:
            config = getattr(self.parent(), "config", None)
            if config and hasattr(config, "pack_manager"):
                pack_manager = config.pack_manager
                outfits = pack_manager.get_info("character", {}).get("outfits", [])
                if outfits:
                    if any(o.get("id") == requested for o in outfits):
                        return requested
                    fallback = next((o for o in outfits if o.get("is_default")), outfits[0])
                    fallback_id = fallback.get("id")
                    if fallback_id:
                        print(f"[CharacterView] Outfit not in pack: {requested}, fallback: {fallback_id}")
                        return fallback_id
        except Exception as e:
            print(f"[CharacterView] Error resolving outfit id: {e}")
        return requested
        
    def _get_outfit_path(self, outfit: str, verbose: bool = False) -> Path:
        if not self.project_root: return Path(".")
        try:
            config = getattr(self.parent(), "config", None)
            if config and hasattr(config, "pack_manager"):
                pack_manager = config.pack_manager
                pack_id = pack_manager.active_pack_id
                pack_root = pack_manager.packs_dir / pack_id
                outfits = pack_manager.get_info("character", {}).get("outfits", [])
                target = next((o for o in outfits if o.get("id") == outfit), None)
                if target:
                    rel_path = target.get("path", "")
                    if rel_path:
                        candidate = Path(rel_path)
                        outfit_path = candidate if candidate.is_absolute() else pack_root / rel_path
                        if verbose: print(f"[CharacterView] Checking pack outfit path: {outfit_path}")
                        if outfit_path.exists() and (outfit_path / "sum.json").exists():
                            if verbose: print(f"[CharacterView] Using pack outfit path: {outfit_path}")
                            return outfit_path
                pack_outfit_path = pack_root / "assets" / "sprites" / outfit
                if verbose: print(f"[CharacterView] Checking pack outfit path: {pack_outfit_path}")
                if pack_outfit_path.exists() and (pack_outfit_path / "sum.json").exists():
                    if verbose: print(f"[CharacterView] Using pack outfit path: {pack_outfit_path}")
                    return pack_outfit_path
        except Exception as e:
            print(f"[CharacterView] Error resolving outfit path: {e}")
            pass
        return self.project_root / "resona_desktop_pet" / "ui" / "assets" / "modes" / outfit

    def get_available_outfits(self) -> List[str]:
        if not self.project_root: return []
        outfits = set()
        try:
            config = getattr(self.parent(), "config", None)
            if config and hasattr(config, "pack_manager"):
                pack_manager = config.pack_manager
                pack_id = pack_manager.active_pack_id
                pack_root = pack_manager.packs_dir / pack_id
                outfit_defs = pack_manager.get_info("character", {}).get("outfits", [])
                for outfit in outfit_defs:
                    outfit_id = outfit.get("id")
                    rel_path = outfit.get("path")
                    if outfit_id and rel_path:
                        candidate = Path(rel_path)
                        outfit_path = candidate if candidate.is_absolute() else pack_root / rel_path
                        if outfit_path.exists() and (outfit_path / "sum.json").exists():
                            outfits.add(outfit_id)
                if not outfits:
                    pack_sprites_path = pack_root / "assets" / "sprites"
                    if pack_sprites_path.exists():
                        for item in pack_sprites_path.iterdir():
                            if item.is_dir() and (item / "sum.json").exists(): outfits.add(item.name)
        except: pass
        modes_path = self.project_root / "resona_desktop_pet" / "ui" / "assets" / "modes"
        if modes_path.exists():
            for item in modes_path.iterdir():
                if item.is_dir() and (item / "sum.json").exists(): outfits.add(item.name)
        return sorted(list(outfits))

    def _load_outfit(self, outfit: str) -> bool:
        resolved = self._resolve_pack_outfit(outfit)
        outfit_path = self._get_outfit_path(resolved, verbose=True)
        print(f"[CharacterView] Loading outfit from: {outfit_path}")
        sum_json = outfit_path / "sum.json"
        if not sum_json.exists(): return False
        try:
            with open(sum_json, "r", encoding="utf-8") as f: self.emotion_map = json.load(f)
            self.current_outfit = resolved
            return True
        except: return False

    def set_outfit(self, outfit: str) -> bool:
        if self._load_outfit(outfit):
            self.set_emotion(self.current_emotion)
            return True
        return False

    def set_emotion(self, emotion: str, deterministic: bool = False) -> bool:
        self.current_emotion = emotion
        if emotion == "<E:smile>": deterministic = True
        if not self.emotion_map or self._resolve_pack_outfit(self.current_outfit) != self.current_outfit:
            self._load_outfit(self.current_outfit)
        if not self.emotion_map: return False
        sprites = self.emotion_map.get(emotion, [])
        if not sprites:
            base_emotion = emotion.split("|")[0] if "|" in emotion else emotion
            sprites = self.emotion_map.get(base_emotion, [])
        if not sprites:
            if emotion != "<E:smile>": return self.set_emotion("<E:smile>", deterministic=True)
            return False
        if deterministic:
            sprite_name = min(sprites, key=lambda s: sum(int(d) for d in s if d.isdigit()))
        else:
            sprite_name = random.choice(sprites)
        return self._load_sprite(sprite_name)

    def _load_sprite(self, sprite_name: str) -> bool:
        outfit_path = self._get_outfit_path(self.current_outfit)
        for ext in [".png", ".jpg", ".webp"]:
            sprite_path = outfit_path / f"{sprite_name}{ext}"
            if sprite_path.exists():
                pixmap = QPixmap(str(sprite_path))
                if not pixmap.isNull():
                    self._pixmap = pixmap
                    self.updateGeometry(); self.update()
                    return True
        return False

    def set_scale(self, scale: float):
        self._scale = max(0.5, min(scale, 1.0))
        self.updateGeometry(); self.update()
        
    def get_scale(self) -> float: return self._scale
        
    def sizeHint(self) -> QSize:
        if not self._pixmap.isNull():
            return QSize(int(self._pixmap.width() * self._scale), int(self._pixmap.height() * self._scale))
        return QSize(int(320 * self._scale), int(360 * self._scale))
        
    def image_rect(self) -> QRect:
        tgt = self.sizeHint()
        return QRect((self.width() - tgt.width()) // 2, (self.height() - tgt.height()) // 2, tgt.width(), tgt.height())
                     
    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform, True)
        rect = self.image_rect()
        if not self._pixmap.isNull(): painter.drawPixmap(rect, self._pixmap)
            
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton: self.leftClicked.emit()
        elif event.button() == Qt.MouseButton.RightButton: self.rightClicked.emit()
        event.ignore()

    def dragEnterEvent(self, event):
        print(f"[CharacterView] dragEnterEvent")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        print(f"[CharacterView] dropEvent")
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            parent = self.parent()
            if parent and hasattr(parent, 'on_file_dropped'):
                for url in event.mimeData().urls():
                    if url.isLocalFile():
                        file_path = url.toLocalFile()
                        if os.path.isfile(file_path):
                            import os
                            from pathlib import Path
                            path = Path(file_path)
                            file_info = {
                                "path": str(path),
                                "name": path.name,
                                "stem": path.stem,
                                "ext": path.suffix.lower() if path.suffix else ""
                            }
                            parent.on_file_dropped(file_info)
