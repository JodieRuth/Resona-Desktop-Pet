import json
import os
import sys
import importlib.util
import random
import configparser
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("PackManager")

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
        self.override_config: Optional[configparser.ConfigParser] = None
        self.override_config_path: Optional[Path] = None
        self._previous_pack_override: Optional[configparser.ConfigParser] = None
        self._resolved_json_cache: Dict[str, Dict[str, Any]] = {}
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
        logger.info(f"set_active_pack requested={pack_id} resolved={folder_name} packs_dir={self.packs_dir}")

        self._previous_pack_override = self.override_config

        self.active_pack_id = folder_name
        self.pack_data = self._get_pack_data(folder_name)
        self._load_pack_manifest()
        self._unload_plugins()

        self._load_override_config()
        
        self._preload_resolved_jsons(folder_name)

    def _preload_resolved_jsons(self, pack_id: str):
        logger.info(f"Preloading resolved JSONs for pack: {pack_id}")
        
        self.clear_resolved_cache(pack_id)
        pack_root = self.packs_dir / pack_id
        
        pack_json_path = pack_root / "pack.json"
        if not pack_json_path.exists():
            logger.error(f"CRITICAL: pack.json not found in {pack_root}")
            return
        
        pack_data = self._get_pack_data(pack_id)
        if not pack_data:
            logger.error(f"CRITICAL: Failed to load pack.json for {pack_id}")
            return
        
        self._validate_pack_structure(pack_id, pack_data)
        
        emotions = self.load_and_resolve_json(pack_id, "logic", "emotions")
        if emotions:
            resolved_count = sum(1 for e in emotions.values() if "_resolved_abs_path" in e)
            failed_count = len(emotions) - resolved_count
            if failed_count > 0:
                logger.warning(f"Emotions: {len(emotions)} total, {resolved_count} resolved, {failed_count} FAILED")
                for emotion_key, config in emotions.items():
                    if "_resolved_abs_path" not in config and "ref_wav" in config:
                        logger.error(f"  Emotion '{emotion_key}': ref_wav '{config['ref_wav']}' not found")
            else:
                logger.info(f"Emotions: {len(emotions)} total, all resolved")
        else:
            emotions_path = self.get_path("logic", "emotions", pack_id)
            if emotions_path:
                logger.error(f"Emotions: FAILED to load from {emotions_path}")
        
        triggers = self.load_and_resolve_json(pack_id, "logic", "triggers")
        if triggers:
            resolved_count = 0
            failed_actions = []
            for trigger in triggers:
                for action in trigger.get("actions", []):
                    if "_resolved_abs_path" in action:
                        resolved_count += 1
                    elif "voice_file" in action:
                        failed_actions.append((trigger.get("id", "unknown"), action["voice_file"]))
            if failed_actions:
                logger.warning(f"Triggers: {len(triggers)} total, {resolved_count} voice files resolved, {len(failed_actions)} FAILED")
                for trigger_id, voice_file in failed_actions:
                    logger.error(f"  Trigger '{trigger_id}': voice_file '{voice_file}' not found")
            else:
                logger.info(f"Triggers: {len(triggers)} total, all voice files resolved")
        else:
            triggers_path = self.get_path("logic", "triggers", pack_id)
            if triggers_path:
                logger.error(f"Triggers: FAILED to load from {triggers_path}")
        
        error_config = self.load_and_resolve_json(pack_id, "logic", "error_config")
        if error_config:
            resolved_count = sum(1 for e in error_config.values() 
                               if isinstance(e, dict) and "audio" in e and "_resolved_abs_path" in e.get("audio", {}))
            failed_errors = []
            for error_type, config in error_config.items():
                if isinstance(config, dict) and "audio" in config:
                    audio_config = config["audio"]
                    if isinstance(audio_config, dict) and "file" in audio_config:
                        if "_resolved_abs_path" not in audio_config:
                            failed_errors.append((error_type, audio_config["file"]))
            if failed_errors:
                logger.warning(f"Error config: {len(error_config)} types, {resolved_count} audio files resolved, {len(failed_errors)} FAILED")
                for error_type, audio_file in failed_errors:
                    logger.error(f"  Error '{error_type}': audio file '{audio_file}' not found")
            else:
                logger.info(f"Error config: {len(error_config)} types, all audio files resolved")
        else:
            error_config_path = self.get_path("logic", "error_config", pack_id)
            if error_config_path:
                logger.error(f"Error config: FAILED to load from {error_config_path}")
        
        self._validate_critical_assets(pack_id, pack_data)

    def _validate_pack_structure(self, pack_id: str, pack_data: Dict[str, Any]):
        pack_root = self.packs_dir / pack_id
        
        pack_info = pack_data.get("pack_info", {})
        if not pack_info.get("id"):
            logger.warning(f"pack_info.id is missing in pack.json")
        if not pack_info.get("name"):
            logger.warning(f"pack_info.name is missing in pack.json")
        
        character = pack_data.get("character", {})
        if not character.get("name"):
            logger.warning(f"character.name is missing in pack.json")
        
        outfits = character.get("outfits", [])
        if not outfits:
            logger.warning(f"No outfits defined in pack.json")
        else:
            for outfit in outfits:
                outfit_id = outfit.get("id", "unknown")
                outfit_path = outfit.get("path")
                if outfit_path:
                    full_path = pack_root / outfit_path
                    if not full_path.exists():
                        logger.error(f"Outfit '{outfit_id}': path '{outfit_path}' not found")
                    elif not (full_path / "sum.json").exists():
                        logger.error(f"Outfit '{outfit_id}': sum.json not found in {outfit_path}")

    def _validate_critical_assets(self, pack_id: str, pack_data: Dict[str, Any]):
        pack_root = self.packs_dir / pack_id
        
        sovits_model = pack_data.get("character", {}).get("sovits_model", {})
        if sovits_model:
            gpt_weights = sovits_model.get("gpt_weights")
            vits_weights = sovits_model.get("vits_weights")
            
            if gpt_weights:
                gpt_path = self.resolve_model_path(pack_id, "gpt_weights")
                if not gpt_path:
                    logger.error(f"SoVITS GPT model not found: '{gpt_weights}'")
            
            if vits_weights:
                vits_path = self.resolve_model_path(pack_id, "vits_weights")
                if not vits_path:
                    logger.error(f"SoVITS VITS model not found: '{vits_weights}'")
        
        audio_cfg = pack_data.get("audio", {})
        for key, dir_name in [("event_audio_dir", "event"), ("emotion_audio_dir", "emotion"), ("error_audio_dir", "error")]:
            dir_path = self.get_path("audio", key.replace("_dir", ""), pack_id)
            if dir_path and not dir_path.exists():
                logger.warning(f"Audio directory for {dir_name} not found: {audio_cfg.get(key)}")
        
        prompts = pack_data.get("logic", {}).get("prompts", [])
        if not prompts:
            logger.warning(f"No prompts defined in pack.json")
        else:
            for prompt in prompts:
                prompt_id = prompt.get("id", "unknown")
                prompt_path = prompt.get("path")
                if prompt_path:
                    full_path = pack_root / prompt_path
                    if not full_path.exists():
                        logger.error(f"Prompt '{prompt_id}': file '{prompt_path}' not found")
        
        logic_configs = pack_data.get("logic", {}).get("interaction_configs", {})
        for config_name, config_path in logic_configs.items():
            if config_path:
                full_path = pack_root / config_path
                if not full_path.exists():
                    logger.error(f"Logic config '{config_name}': file '{config_path}' not found")
        
        plugin_dir_rel = pack_data.get("logic", {}).get("plugins")
        if plugin_dir_rel:
            plugin_dir = pack_root / plugin_dir_rel
            if not plugin_dir.exists():
                logger.warning(f"Plugin directory not found: '{plugin_dir_rel}'")
            elif not any(plugin_dir.glob("*.py")):
                logger.warning(f"No Python plugins found in: '{plugin_dir_rel}'")

    def _load_override_config(self):
        override_path = self.packs_dir / self.active_pack_id / "override_config.cfg"

        if override_path.exists():
            logger.info(f"Found override_config.cfg in pack '{self.active_pack_id}'")
            self.override_config = configparser.ConfigParser(interpolation=None)
            try:
                self.override_config.read(override_path, encoding="utf-8")
                self.override_config_path = override_path
                logger.info(f"Loaded override config with sections: {self.override_config.sections()}")
            except Exception as e:
                logger.error(f"Failed to load override_config.cfg: {e}")
                self.override_config = None
                self.override_config_path = None
        else:
            if self.override_config is not None:
                logger.info(f"Pack '{self.active_pack_id}' has no override_config.cfg, clearing previous override")
            self.override_config = None
            self.override_config_path = None

    def get_override_value(self, section: str, key: str, fallback: Any = None) -> Optional[str]:
        if self.override_config is None:
            return None
        try:
            return self.override_config.get(section, key, fallback=None)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return None

    def has_override(self) -> bool:
        return self.override_config is not None

    def get_override_sections(self) -> list:
        if self.override_config is None:
            return []
        return self.override_config.sections()

    def get_pack_json_id(self, folder_name: Optional[str] = None) -> str:
        target = folder_name if folder_name else self.active_pack_id
        data = self._get_pack_data(target)
        info = data.get("pack_info", {})
        return info.get("id") or data.get("id") or target

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
            logger.error(f"Plugin directory not found: {plugin_dir}")
            return

        py_files = list(plugin_dir.glob("*.py"))
        if not py_files:
            logger.warning(f"No Python plugins found in {plugin_dir}")
            return

        logger.info(f"Loading plugins from {plugin_dir} ({len(py_files)} files found)")
        loaded_count = 0
        failed_count = 0
        
        for f in py_files:
            try:
                module_name = f"resona_plugin_{self.active_pack_id}_{f.stem}"
                spec = importlib.util.spec_from_file_location(module_name, f)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    has_info = hasattr(module, "INFO")
                    if not has_info:
                        logger.error(f"Plugin {f.name}: missing INFO attribute")
                        failed_count += 1
                        continue
                    
                    plugin_id = module.INFO.get("id")
                    if not plugin_id:
                        logger.error(f"Plugin {f.name}: INFO.id is missing")
                        failed_count += 1
                        continue
                    
                    self.loaded_plugins[plugin_id] = module
                    triggers = module.INFO.get("triggers", [])
                    for t in triggers:
                        t_type = t.get("type")
                        if t_type:
                            self.plugin_trigger_map[t_type] = plugin_id
                    for a in module.INFO.get("actions", []):
                        a_type = a.get("type")
                        if a_type: 
                            self.plugin_action_map[a_type] = plugin_id
                    
                    logger.info(f"Loaded plugin: {plugin_id} from {f.name}")
                    loaded_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to load plugin {f.name}: {e}")
                failed_count += 1
                import traceback
                traceback.print_exc()
        
        logger.info(f"Plugin loading complete: {loaded_count} loaded, {failed_count} failed")
        if self.plugin_trigger_map:
            logger.info(f"Registered triggers: {list(self.plugin_trigger_map.keys())}")
        if self.plugin_action_map:
            logger.info(f"Registered actions: {list(self.plugin_action_map.keys())}")

    def _load_pack_manifest(self):
        self.pack_data = {}
        manifest_path = self.packs_dir / self.active_pack_id / "pack.json"
        
        if not manifest_path.exists():
            logger.error(f"CRITICAL: Manifest not found at {manifest_path}")
            logger.error(f"  Please ensure pack.json exists in the pack directory")
            return

        logger.info(f"Loading manifest from: {manifest_path}")
        
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.strip():
                    logger.error(f"CRITICAL: pack.json is empty")
                    return
                self.pack_data = json.loads(content)
        except UnicodeDecodeError:
            try:
                with open(manifest_path, "r", encoding="gbk") as f:
                    self.pack_data = json.load(f)
                logger.warning(f"pack.json was loaded with GBK encoding (consider using UTF-8)")
            except Exception as e:
                logger.error(f"CRITICAL: Failed to decode pack.json with UTF-8 or GBK: {e}")
                return
        except json.JSONDecodeError as e:
            logger.error(f"CRITICAL: pack.json syntax error: {e}")
            logger.error(f"  Location: {manifest_path}")
            logger.error(f"  Hint: Check for missing commas, brackets, or quotes")
            return
        except Exception as e:
            logger.error(f"CRITICAL: Unexpected error loading manifest: {e}")
            return

        info = self.pack_data.get("pack_info", {})
        character = self.pack_data.get("character", {})
        logic = self.pack_data.get("logic", {})
        prompts = logic.get("prompts", [])
        
        logger.info(f"Manifest loaded successfully")
        logger.info(f"Pack Information:")
        logger.info(f"  Folder: {self.active_pack_id}")
        logger.info(f"  Pack ID: {info.get('id', 'NOT SET')}")
        logger.info(f"  Name: {info.get('name', 'NOT SET')}")
        logger.info(f"  Version: {info.get('version', 'N/A')}")
        logger.info(f"  Author: {info.get('author', 'N/A')}")
        logger.info(f"Character Configuration:")
        logger.info(f"  Name: {character.get('name', 'NOT SET')}")
        logger.info(f"  TTS Language: {character.get('tts_language', 'default')}")
        logger.info(f"  Outfits: {len(character.get('outfits', []))}")
        logger.info(f"  Prompts: {len(prompts)}")
        
        missing_fields = []
        if not info.get('id'):
            missing_fields.append("pack_info.id")
        if not info.get('name'):
            missing_fields.append("pack_info.name")
        if not character.get('name'):
            missing_fields.append("character.name")
        if not prompts:
            missing_fields.append("logic.prompts")
        
        if missing_fields:
            logger.warning(f"Missing recommended fields: {', '.join(missing_fields)}")

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
                result = p if p.is_absolute() else pack_root / rel_path
                if not result.exists():
                    search_result = self._search_path_in_pack(target_pack_id, category, key, rel_path)
                    if search_result:
                        return search_result
                return result
        except Exception:
            pass
        return None

    def _search_path_in_pack(self, pack_id: str, category: str, key: str, original_rel_path: str) -> Optional[Path]:
        pack_root = self.packs_dir / pack_id
        if not pack_root.exists():
            return None
        
        original_name = Path(original_rel_path).name
        
        try:
            for file_path in pack_root.rglob(original_name):
                if file_path.is_file():
                    logger.debug(f"Found file via search: {file_path} (for {category}/{key})")
                    return file_path
            
            for dir_path in pack_root.rglob(original_name):
                if dir_path.is_dir():
                    logger.debug(f"Found directory via search: {dir_path} (for {category}/{key})")
                    return dir_path
        except Exception as e:
            logger.error(f"Search error: {e}")
        
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
            logger.error(f"Error resolving sprite: {e}")
        return None

    def get_available_packs(self) -> list:
        if not self.packs_dir.exists(): return []
        return [d.name for d in self.packs_dir.iterdir() if d.is_dir() and (d / "pack.json").exists()]

    def find_file_in_pack(self, pack_id: str, filename: str) -> Optional[Path]:
        pack_root = self.packs_dir / pack_id
        if not pack_root.exists():
            return None
        
        candidates = []
        try:
            for file_path in pack_root.rglob(filename):
                if file_path.is_file():
                    try:
                        mtime = file_path.stat().st_mtime
                        candidates.append((file_path, mtime))
                    except Exception:
                        candidates.append((file_path, 0))
        except Exception as e:
            logger.error(f"Search error in pack '{pack_id}': {e}")
            return None
        
        if not candidates:
            return None
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def resolve_model_path(self, pack_id: str, model_type: str) -> Optional[Path]:
        defined_path = self.get_path("model", model_type, pack_id)
        if defined_path and defined_path.exists():
            return defined_path
        
        pack_data = self._get_pack_data(pack_id)
        if pack_data:
            model_info = pack_data.get("character", {}).get("sovits_model", {})
            filename = model_info.get(model_type)
            if filename:
                found = self.find_file_in_pack(pack_id, Path(filename).name)
                if found:
                    logger.debug(f"Found {model_type} model via search: {found}")
                    return found
        
        return None

    def resolve_resource_path(self, pack_id: str, rel_path: str, search_extensions: list = None) -> Optional[Path]:
        pack_root = self.packs_dir / pack_id
        if not pack_root.exists():
            return None
        
        standard_path = pack_root / rel_path
        if standard_path.exists():
            return standard_path
        
        if search_extensions:
            for ext in search_extensions:
                path_with_ext = pack_root / (rel_path + ext)
                if path_with_ext.exists():
                    return path_with_ext
        
        filename = Path(rel_path).name
        found = self.find_file_in_pack(pack_id, filename)
        if found:
            logger.debug(f"Resolved resource via search: {found} (for {rel_path})")
            return found
        
        if search_extensions:
            for ext in search_extensions:
                found = self.find_file_in_pack(pack_id, filename + ext)
                if found:
                    logger.debug(f"Resolved resource via search: {found} (for {rel_path}{ext})")
                    return found
        
        return None

    def load_and_resolve_json(self, pack_id: str, category: str, key: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        cache_key = f"{pack_id}:{category}:{key}"
        
        if use_cache and cache_key in self._resolved_json_cache:
            return self._resolved_json_cache[cache_key]
        
        json_path = self.get_path(category, key, pack_id)
        if not json_path or not json_path.exists():
            logger.error(f"JSON file not found: {category}/{key} for pack {pack_id}")
            return None
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load JSON {json_path}: {e}")
            return None
        
        resolved_data = None
        if key == "emotions":
            resolved_data = self._resolve_emotions_json(pack_id, data)
        elif key == "triggers":
            resolved_data = self._resolve_triggers_json(pack_id, data)
        elif key == "error_config":
            resolved_data = self._resolve_error_config_json(pack_id, data)
        else:
            resolved_data = data
        
        if resolved_data is not None:
            self._resolved_json_cache[cache_key] = resolved_data
        
        return resolved_data

    def get_resolved_emotions(self, pack_id: str = None) -> Dict[str, Any]:
        target_pack = pack_id if pack_id else self.active_pack_id
        return self.load_and_resolve_json(target_pack, "logic", "emotions")

    def get_resolved_triggers(self, pack_id: str = None) -> list:
        target_pack = pack_id if pack_id else self.active_pack_id
        return self.load_and_resolve_json(target_pack, "logic", "triggers")

    def get_resolved_error_config(self, pack_id: str = None) -> Dict[str, Any]:
        target_pack = pack_id if pack_id else self.active_pack_id
        return self.load_and_resolve_json(target_pack, "logic", "error_config")

    def clear_resolved_cache(self, pack_id: str = None):
        if pack_id:
            keys_to_remove = [k for k in self._resolved_json_cache.keys() if k.startswith(f"{pack_id}:")]
            for key in keys_to_remove:
                del self._resolved_json_cache[key]
        else:
            self._resolved_json_cache.clear()

    def _resolve_emotions_json(self, pack_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        resolved_data = {}
        
        for emotion_key, config in data.items():
            resolved_config = config.copy()
            
            if "ref_wav" in config:
                original_path = config["ref_wav"]
                resolved_path = self.resolve_resource_path(
                    pack_id, 
                    original_path,
                    search_extensions=[".wav", ".mp3", ".ogg"]
                )
                if resolved_path:
                    pack_root = self.packs_dir / pack_id
                    try:
                        rel_resolved = resolved_path.relative_to(pack_root)
                        resolved_config["ref_wav"] = str(rel_resolved)
                        resolved_config["_resolved_abs_path"] = str(resolved_path)
                    except ValueError:
                        resolved_config["ref_wav"] = original_path
                        resolved_config["_resolved_abs_path"] = str(resolved_path)
                else:
                    logger.warning(f"Could not resolve ref_wav '{original_path}' for emotion {emotion_key}")
            
            resolved_data[emotion_key] = resolved_config
        
        return resolved_data

    def _resolve_triggers_json(self, pack_id: str, data: list) -> list:
        resolved_data = []
        
        for trigger in data:
            resolved_trigger = trigger.copy()
            
            if "actions" in trigger:
                resolved_actions = []
                for action in trigger["actions"]:
                    resolved_action = action.copy()
                    
                    if "voice_file" in action:
                        original_path = action["voice_file"]
                        resolved_path = self.resolve_resource_path(
                            pack_id,
                            original_path,
                            search_extensions=[".wav", ".mp3", ".ogg"]
                        )
                        if resolved_path:
                            pack_root = self.packs_dir / pack_id
                            try:
                                rel_resolved = resolved_path.relative_to(pack_root)
                                resolved_action["voice_file"] = str(rel_resolved)
                                resolved_action["_resolved_abs_path"] = str(resolved_path)
                            except ValueError:
                                resolved_action["voice_file"] = original_path
                                resolved_action["_resolved_abs_path"] = str(resolved_path)
                        else:
                            logger.warning(f"Could not resolve voice_file '{original_path}' in trigger {trigger.get('id', 'unknown')}")
                    
                    resolved_actions.append(resolved_action)
                resolved_trigger["actions"] = resolved_actions
            
            resolved_data.append(resolved_trigger)
        
        return resolved_data

    def _resolve_error_config_json(self, pack_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        resolved_data = data.copy()
        pack_root = self.packs_dir / pack_id
        
        for error_type, config in data.items():
            if isinstance(config, dict) and "audio" in config:
                audio_config = config["audio"]
                if isinstance(audio_config, dict) and "file" in audio_config:
                    original_path = audio_config["file"]
                    resolved_path = self.resolve_resource_path(
                        pack_id,
                        original_path,
                        search_extensions=[".wav", ".mp3", ".ogg"]
                    )
                    if resolved_path:
                        try:
                            rel_resolved = resolved_path.relative_to(pack_root)
                            resolved_data[error_type]["audio"]["file"] = str(rel_resolved)
                            resolved_data[error_type]["audio"]["_resolved_abs_path"] = str(resolved_path)
                        except ValueError:
                            resolved_data[error_type]["audio"]["file"] = original_path
                            resolved_data[error_type]["audio"]["_resolved_abs_path"] = str(resolved_path)
                    else:
                        logger.warning(f"Could not resolve error audio '{original_path}' for {error_type}")
        
        return resolved_data

