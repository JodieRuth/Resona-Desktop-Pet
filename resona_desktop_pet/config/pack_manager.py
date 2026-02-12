import json
import os
import sys
import importlib.util
from pathlib import Path
from typing import Optional, Dict, Any

class PackManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.packs_dir = project_root / "packs"
        self.active_pack_id = "Resona_Default"
        self.pack_data: Dict[str, Any] = {}
        self.id_map: Dict[str, str] = {}
        self.loaded_plugins: Dict[str, Any] = {}
        self.plugin_trigger_map: Dict[str, str] = {}
        self.plugin_action_map: Dict[str, str] = {}
        self._scan_packs()

    def _scan_packs(self):
        self.id_map = {}
        if not self.packs_dir.exists(): return
        for p_dir in self.packs_dir.iterdir():
            if p_dir.is_dir():
                manifest = p_dir / "pack.json"
                if manifest.exists():
                    try:
                        with open(manifest, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            info = data.get("pack_info", {})
                            pid = info.get("id") or data.get("id")
                            if pid:
                                self.id_map[pid] = p_dir.name
                    except: pass

    def set_active_pack(self, pack_id: str):
        self._scan_packs()
        folder_name = self.id_map.get(pack_id, pack_id)
        print(f"[PackManager] set_active_pack requested={pack_id} resolved={folder_name} packs_dir={self.packs_dir}")
        self.active_pack_id = folder_name
        self._load_pack_manifest()
        self._unload_plugins()

    def _unload_plugins(self):
        self.loaded_plugins.clear()
        self.plugin_trigger_map.clear()
        self.plugin_action_map.clear()

    def load_plugins(self, enabled: bool):
        if not enabled:
            self._unload_plugins()
            return

        plugin_dir_rel = self.pack_data.get("logic", {}).get("plugins")
        if not plugin_dir_rel:
            return

        plugin_dir = self.packs_dir / self.active_pack_id / plugin_dir_rel
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            return

        print(f"[PackManager] Loading plugins from {plugin_dir}")
        for f in plugin_dir.glob("*.py"):
            try:
                module_name = f"resona_plugin_{self.active_pack_id}_{f.stem}"
                spec = importlib.util.spec_from_file_location(module_name, f)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    has_info = hasattr(module, "INFO")
                    print(f"[PackManager] Checking plugin {f.name}: hasattr(INFO)={has_info}")
                    if has_info:
                        print(f"[PackManager] INFO content: {module.INFO}")

                    if has_info:
                        plugin_id = module.INFO.get("id")
                        print(f"[PackManager] plugin_id: {plugin_id}")
                        if plugin_id:
                            self.loaded_plugins[plugin_id] = module
                            triggers = module.INFO.get("triggers", [])
                            print(f"[PackManager] triggers: {triggers}")
                            for t in triggers:
                                t_type = t.get("type")
                                print(f"[PackManager] Processing trigger: type={t_type}")
                                if t_type:
                                    self.plugin_trigger_map[t_type] = plugin_id
                                    print(f"[PackManager] Registered trigger: {t_type} -> {plugin_id}")
                            for a in module.INFO.get("actions", []):
                                a_type = a.get("type")
                                if a_type: self.plugin_action_map[a_type] = plugin_id
                            print(f"[PackManager] Loaded plugin: {plugin_id}")
                            print(f"[PackManager] Current plugin_trigger_map: {self.plugin_trigger_map}")
            except Exception as e:
                print(f"[PackManager] Failed to load plugin {f.name}: {e}")
                import traceback
                traceback.print_exc()

    def _load_pack_manifest(self):
        self.pack_data = {}
        manifest_path = self.packs_dir / self.active_pack_id / "pack.json"
        print(f"[PackManager] Loading manifest: {manifest_path}")
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    self.pack_data = json.load(f)
                info = self.pack_data.get("pack_info", {})
                character = self.pack_data.get("character", {})
                outfits = character.get("outfits", [])
                prompts = self.pack_data.get("logic", {}).get("prompts", [])
                print(f"[PackManager] Manifest loaded: pack_id={info.get('id')} name={info.get('name')} character={character.get('name')} outfits={len(outfits)} prompts={len(prompts)}")
            except Exception as e:
                print(f"[PackManager] Error loading manifest: {e}")
        else:
            print(f"[PackManager] Manifest not found: {manifest_path}")

    def get_info(self, key: str, default: Any = None) -> Any:
        self._load_pack_manifest()

        if key in self.pack_data:
            return self.pack_data[key]

        if "character" in self.pack_data:
            return self.pack_data["character"].get(key, default)

        return default

    def get_path(self, category: str, key: str = None) -> Optional[Path]:
        if not self.pack_data:
            self._load_pack_manifest()
        pack_root = self.packs_dir / self.active_pack_id
        try:
            rel_path = None
            if category == "logic":
                configs = self.pack_data.get("logic", {}).get("interaction_configs", {})
                if key == "triggers": rel_path = configs.get("triggers")
                elif key == "prompts":
                    prompts = self.pack_data.get("logic", {}).get("prompts", [])
                    if prompts: rel_path = prompts[0].get("path")
                elif key == "error_config": rel_path = configs.get("error_config")
                elif key == "emotions": rel_path = configs.get("emotions")
                elif key == "thinking": rel_path = configs.get("thinking")
                elif key == "listening": rel_path = configs.get("listening")
            elif category == "audio":
                audio_cfg = self.pack_data.get("audio", {})
                if key == "event_dir": rel_path = audio_cfg.get("event_audio_dir")
                elif key == "emotion_dir": rel_path = audio_cfg.get("emotion_audio_dir")
                elif key == "error_dir": rel_path = audio_cfg.get("error_audio_dir")
            elif category == "model":
                rel_path = self.pack_data.get("character", {}).get("sovits_model", {}).get(key)

            if rel_path:
                p = Path(rel_path)
                return p if p.is_absolute() else pack_root / rel_path
        except: pass
        return None

    def get_available_emotions(self) -> list:
        emotions_path = self.get_path("logic", "emotions")
        if emotions_path and emotions_path.exists():
            try:
                with open(emotions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return list(data.keys())
            except: pass
        return []

    def get_available_emotions(self) -> list:
        emotions_path = self.get_path("logic", "emotions")
        if emotions_path and emotions_path.exists():
            try:
                with open(emotions_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return list(data.keys())
            except: pass
        return []

    def get_character_name(self) -> str:
        return self.pack_data.get("character", {}).get("name", "Unknown")

    def get_available_packs(self) -> list:
        if not self.packs_dir.exists(): return []
        return [d.name for d in self.packs_dir.iterdir() if d.is_dir() and (d / "pack.json").exists()]
