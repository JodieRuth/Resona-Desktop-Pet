import json
import os
import sys
import importlib.util
import random
from pathlib import Path
from typing import Optional, Dict, Any

class PackManager:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.packs_dir = project_root / "packs"
        self.active_pack_id = "Resona_Default"
        self.pack_data: Dict[str, Any] = {}
        self.pack_cache: Dict[str, Any] = {}
        self.id_map: Dict[str, str] = {}
        self.loaded_plugins: Dict[str, Any] = {}
        self.plugin_trigger_map: Dict[str, str] = {}
        self.plugin_action_map: Dict[str, str] = {}
        self._scan_packs()

    def _get_pack_data(self, pack_id: str) -> Dict[str, Any]:
        if pack_id in self.pack_cache:
            return self.pack_cache[pack_id]
        
        manifest_path = self.packs_dir / pack_id / "pack.json"
        if not manifest_path.exists():
            return {}
            
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.pack_cache[pack_id] = data
                return data
        except UnicodeDecodeError:
            try:
                with open(manifest_path, "r", encoding="gbk") as f:
                    data = json.load(f)
                    self.pack_cache[pack_id] = data
                    return data
            except: pass
        except: pass
        return {}

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
        self.pack_data = self._get_pack_data(folder_name)
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
        
        if not manifest_path.exists():
            print(f"[PackManager] CRITICAL: Manifest not found at {manifest_path}")
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                self.pack_data = json.load(f)
        except UnicodeDecodeError:
            try:
                with open(manifest_path, "r", encoding="gbk") as f:
                    self.pack_data = json.load(f)
            except Exception as e:
                print(f"[PackManager] CRITICAL: Failed to decode pack.json with UTF-8 or GBK: {e}")
                return
        except json.JSONDecodeError as e:
            print(f"[PackManager] CRITICAL: pack.json syntax error at {manifest_path}: {e}")
            return
        except Exception as e:
            print(f"[PackManager] CRITICAL: Unexpected error loading manifest: {e}")
            return

        info = self.pack_data.get("pack_info", {})
        character = self.pack_data.get("character", {})
        logic = self.pack_data.get("logic", {})
        prompts = logic.get("prompts", [])
        
        print(f"[PackManager] Manifest loaded successfully from {self.active_pack_id}")
        print(f"  - Pack ID: {info.get('id')}")
        print(f"  - Character: {character.get('name')}")
        print(f"  - Prompts defined: {len(prompts)}")

    def get_info(self, key: str, default: Any = None) -> Any:
        if not self.pack_data:
            self._load_pack_manifest()

        if key in self.pack_data:
            return self.pack_data[key]

        if "character" in self.pack_data:
            return self.pack_data["character"].get(key, default)

        return default

    def get_path(self, category: str, key: str = None, pack_id: Optional[str] = None) -> Optional[Path]:
        target_pack_id = pack_id if pack_id else self.active_pack_id
        current_data = self._get_pack_data(target_pack_id) if pack_id else self.pack_data
        
        if not current_data and not pack_id:
            self._load_pack_manifest()
            current_data = self.pack_data

        pack_root = self.packs_dir / target_pack_id
        try:
            rel_path = None
            if category == "logic":
                configs = current_data.get("logic", {}).get("interaction_configs", {})
                if key == "triggers": rel_path = configs.get("triggers")
                elif key == "prompts":
                    prompts = current_data.get("logic", {}).get("prompts", [])
                    if prompts: rel_path = prompts[0].get("path")
                elif key == "error_config": rel_path = configs.get("error_config")
                elif key == "emotions": rel_path = configs.get("emotions")
                elif key == "thinking": rel_path = configs.get("thinking")
                elif key == "listening": rel_path = configs.get("listening")
            elif category == "audio":
                audio_cfg = current_data.get("audio", {})
                if key == "event_dir": rel_path = audio_cfg.get("event_audio_dir")
                elif key == "emotion_dir": rel_path = audio_cfg.get("emotion_audio_dir")
                elif key == "error_dir": rel_path = audio_cfg.get("error_audio_dir")
            elif category == "model":
                rel_path = current_data.get("character", {}).get("sovits_model", {}).get(key)

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

    def get_character_name(self) -> str:
        return self.pack_data.get("character", {}).get("name", "Unknown")

    def resolve_sprite_path(self, pack_id: str, outfit_id: str, emotion: str) -> Optional[str]:
        try:
            pack_data = self._get_pack_data(pack_id)
            if not pack_data: return None
            
            outfits = pack_data.get("character", {}).get("outfits", [])
            target_outfit = next((o for o in outfits if o.get("id") == outfit_id), None)
            if not target_outfit:
                target_outfit = next((o for o in outfits if o.get("is_default")), None)
            
            if not target_outfit: return None
            
            outfit_rel_path = target_outfit.get("path")
            full_outfit_path = self.packs_dir / pack_id / outfit_rel_path
            sum_path = full_outfit_path / "sum.json"
            
            if not sum_path.exists(): return None
            
            with open(sum_path, "r", encoding="utf-8") as f:
                sum_data = json.load(f)
            
            candidates = sum_data.get(emotion, [])
            if not candidates:
                for k in ["<E:normal>", "<E:default>"]:
                    if k in sum_data and sum_data[k]:
                        candidates = sum_data[k]
                        break
                if not candidates and sum_data:
                    first_key = list(sum_data.keys())[0]
                    candidates = sum_data[first_key]
            
            if candidates:
                valid_images = []
                for image_name in candidates:
                    for ext in [".png", ".jpg", ".jpeg"]:
                        if (full_outfit_path / (image_name + ext)).exists():
                            valid_images.append((image_name, ext))
                            break
                if valid_images:
                    image_name, ext = random.choice(valid_images)
                    rel_path = f"{pack_id}/{outfit_rel_path}/{image_name}{ext}"
                    return rel_path.replace("\\", "/")
                        
        except Exception as e:
            print(f"[PackManager] Error resolving sprite: {e}")
        return None

    def get_available_packs(self) -> list:
        if not self.packs_dir.exists(): return []
        return [d.name for d in self.packs_dir.iterdir() if d.is_dir() and (d / "pack.json").exists()]
