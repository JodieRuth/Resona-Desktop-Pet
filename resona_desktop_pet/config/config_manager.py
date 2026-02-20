import configparser
import os
from pathlib import Path
from typing import Any, Optional


from .pack_manager import PackManager

class ConfigManager:
    def __init__(self, config_path: str = "config.cfg"):
        self.config_path = Path(config_path).absolute()
        self.config = configparser.ConfigParser(interpolation=None)
        self.load()


        self.pack_manager = PackManager(self.config_path.parent)
        self.pack_manager.set_active_pack(self.get_required("General", "active_pack"))

    def load(self):
        if self.config_path.exists():
            self.config.read(self.config_path, encoding="utf-8")
            if hasattr(self, 'pack_manager'):
                active_pack = self.config.get("General", "active_pack", fallback="Resona_Default")
                if active_pack:
                    print(f"[Config] load active_pack={active_pack} config_path={self.config_path}")
                    self.pack_manager.set_active_pack(active_pack)

    def save(self) -> None:
        active_pack = self.config.get("General", "active_pack", fallback="")
        if active_pack:
            print(f"[Config] save active_pack={active_pack} config_path={self.config_path}")

        if not self.config_path.exists():
            with open(self.config_path, "w", encoding="utf-8") as f:
                self.config.write(f)
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        current_section = None
        processed_items = set() 

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1]
                new_lines.append(line)
                continue
            
            if current_section and "=" in line and not stripped.startswith(("#", ";")):
                key = line.split("=", 1)[0].strip()
                found = False
                for mem_key in self.config.options(current_section):
                    if mem_key.lower() == key.lower():
                        val = self.config.get(current_section, mem_key)
                        comment = ""
                        if "#" in line: comment = " #" + line.split("#", 1)[1].strip()
                        elif ";" in line: comment = " ;" + line.split(";", 1)[1].strip()
                        new_lines.append(f"{key} = {val}{comment}\n")
                        processed_items.add((current_section.lower(), key.lower()))
                        found = True
                        break
                if not found:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        with open(self.config_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    def get(self, section: str, key: str, fallback: Any = None) -> str:
        val = self.config.get(section, key, fallback=None)
        if val is None:
            return str(fallback)
        return val

    def get_bool(self, section: str, key: str, fallback: bool = False) -> bool:

        return self.getboolean(section, key, fallback)

    def get_required(self, section: str, key: str) -> str:

        try:
            val = self.config.get(section, key)
            if not val or val.strip() == "":
                raise RuntimeError(f"CRITICAL CONFIG ERROR: [{section}] -> '{key}' is empty in config.cfg.")
            return val
        except (configparser.NoSectionError, configparser.NoOptionError):
            raise RuntimeError(f"CRITICAL CONFIG ERROR: [{section}] -> '{key}' is missing in config.cfg. This value is mandatory.")

    def getint(self, section: str, key: str, fallback: int = 0) -> int:
        return self.config.getint(section, key, fallback=fallback)

    def getfloat(self, section: str, key: str, fallback: float = 0.0) -> float:
        return self.config.getfloat(section, key, fallback=fallback)

    def getboolean(self, section: str, key: str, fallback: bool = False) -> bool:
        try:
            value = self.config.get(section, key, fallback=str(fallback))
            return value.lower() in ("true", "1", "yes", "on")
        except:
            return fallback

    def set(self, section: str, key: str, value: Any) -> None:
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))


    @property
    def model_select(self) -> int:
        return self.getint("General", "model_select", 2)

    @property
    def llm_mode(self) -> str:
        return self.get("General", "llm_mode", "cloud")

    @property
    def character_name(self) -> str:
        if self.use_pack_settings:
            val = self.pack_manager.get_info("character", {}).get("name")
            if val: return val
        return self.get_required("General", "CharacterName")
        
    @property
    def default_outfit(self) -> str:
        if self.use_pack_settings:
            outfits = self.pack_manager.get_info("character", {}).get("outfits", [])
            target = next((o for o in outfits if o.get("is_default")), None)
            if not target and outfits:
                target = outfits[0]
            if target:
                return target.get("id")
        return self.get_required("General", "default_outfit")

    @property
    def username(self) -> str:
        if self.use_pack_settings:
            val = self.pack_manager.get_info("character", {}).get("username_default")
            if val: return val
        return self.get("Custom", "Username", "User")

    @property
    def use_pack_settings(self) -> bool:
        return self.getboolean("General", "use_pack_settings", True)

    @property
    def plugins_enabled(self) -> bool:
        return self.getboolean("General", "plugins_enabled", False)

    @property
    def disable_actions(self) -> bool:
        return self.getboolean("General", "disable_actions", False)

    @property
    def tts_language(self) -> str:
        if self.use_pack_settings:
            return self.pack_manager.get_info("character", {}).get("tts_language", "ja")
        return self.get("SoVITS", "tts_language", "ja")

    @property
    def max_rounds(self) -> int:
        return self.getint("History", "max_rounds", 4)

    @property
    def enable_time_context(self) -> bool:
        return self.getint("Time", "enable_time_context", 1) == 1

    @property
    def thinking_text_enabled(self) -> bool:
        return self.getboolean("General", "ThinkingText", True)

    @property
    def thinking_text_switch(self) -> bool:
        return self.getboolean("General", "ThinkingTextSwitch", True)

    @property
    def thinking_text_time(self) -> float:
        return self.getfloat("General", "ThinkingTextTime", 1.0)

    @property
    def thinking_text_switch_time(self) -> float:
        return self.getfloat("General", "ThinkingTextSwitchTime", 5.0)

    @property
    def listening_text_enabled(self) -> bool:
        return self.getboolean("General", "ListeningText", True)

    @property
    def debug_panel(self) -> bool:
        return self.getboolean("General", "debug_panel", False)

    @property
    def debug_trigger(self) -> bool:
        return self.getboolean("General", "debugtrigger", False)

    @property
    def always_show_ui(self) -> bool:
        return self.getboolean("General", "always_show_ui", False)

    @property
    def idle_fade_delay(self) -> float:
        return self.getfloat("General", "idle_fade_delay", 3.0)

    @property
    def text_read_speed(self) -> float:
        return self.getfloat("General", "text_read_speed", 0.2)

    @property
    def base_display_time(self) -> float:
        return self.getfloat("General", "base_display_time", 2.0)

    @property
    def sprite_width(self) -> int:
        return self.getint("General", "width", 650)

    @property
    def sprite_height(self) -> int:
        return self.getint("General", "height", 780)

    @property
    def dialogue_width(self) -> int:
        return self.getint("General", "dialogue_width", 380)

    @property
    def dialogue_height(self) -> int:
        return self.getint("General", "dialogue_height", 135)

    @property
    def font_scale(self) -> float:
        return self.getfloat("General", "font_scale", 1.0)

    @property
    def dialogue_clear_timeout(self) -> float:
        return self.getfloat("General", "dialogue_clear_timeout", 5.0)

    @property
    def dialog_color(self) -> str:
        return self.get("General", "dialog_color", "0,0,0")

    @property
    def dialog_opacity(self) -> int:
        val = self.getint("General", "dialog_opacity", 35)
        return max(0, min(100, val))

    @property
    def dialog_font(self) -> str:
        return self.get("General", "dialog_font", "")

    @property
    def dialog_text_color(self) -> str:
        return self.get("General", "dialog_text_color", "255,255,255")
        
    @property
    def monitor_clipboard(self) -> bool:
        return self.get_bool("Advanced", "monitor_clipboard", True)

    @property
    def monitor_music(self) -> bool:
        return self.get_bool("General", "monitor_music", True)

    @property
    def use_ui_automation(self) -> bool:
        return self.get_bool("Advanced", "use_ui_automation", True)

    @property
    def check_last_input(self) -> bool:
        return self.get_bool("Advanced", "check_last_input", True)

    @property
    def behavior_enabled(self) -> bool:
        return self.getboolean("Behavior", "enabled", True)

    @property
    def behavior_interval(self) -> float:
        return self.getfloat("Behavior", "interval", 1.0)

    @property
    def always_on_top(self) -> bool:
        return self.getboolean("General", "always_on_top", False)

    @property
    def action_bring_to_front(self) -> bool:
        return self.getboolean("Behavior", "action_bring_to_front", True)

    @property
    def behavior_text_read_multiplier(self) -> float:
        return self.getfloat("Behavior", "behavior_text_read_multiplier", 1.5)

    @property
    def trigger_cooldown(self) -> float:
        return self.getfloat("Behavior", "trigger_cooldown", 30.0)

    @property
    def post_busy_delay(self) -> float:
        return self.getfloat("Behavior", "post_busy_delay", 5.0)

    @property
    def idle_opacity(self) -> float:
        return self.getfloat("General", "idle_opacity", 0.8)

    @property
    def show_in_taskbar(self) -> bool:
        return self.getboolean("General", "show_in_taskbar", True)

    @property
    def global_show_hotkey(self) -> str:
        return self.get("General", "global_show_hotkey", "ctrl+alt+0")

    @property
    def tray_icon_path(self) -> str:

        filename = self.get("General", "tray_icon_path", "icon.ico")
        

        pack_path = self.pack_manager.packs_dir / self.pack_manager.active_pack_id
        if pack_path.exists():

            path = pack_path / filename
            if path.exists(): return str(path.absolute())

            path = pack_path / "assets" / filename
            if path.exists(): return str(path.absolute())
            

        default_path = Path(self.config_path.parent) / "icon.ico"
        return str(default_path.absolute())

    def print_all_configs(self):

        print("\n" + "="*20 + " [RESONA CONFIG AUDIT] " + "="*20)
        for section in self.config.sections():
            print(f"[{section}]")
            for key, val in self.config.items(section):

                key_lower = key.lower()
                masked = any(token in key_lower for token in ["api_key", "secret", "token", "password"])
                display_val = "********" if masked else val
                print(f"  {key} = {display_val}")
        print("="*63 + "\n")


    @property
    def stt_enabled(self) -> bool:
        return self.getboolean("STT", "enabled", True)

    @property
    def stt_hotkey(self) -> str:
        return self.get("STT", "hotkey", "ctrl+shift+i")

    @property
    def stt_silence_threshold(self) -> float:
        return self.getfloat("STT", "silence_threshold", 1.0)

    @property
    def stt_max_duration(self) -> float:
        return self.getfloat("STT", "max_duration", 6.5)

    @property
    def stt_model_dir(self) -> str:
        return self.get("STT", "model_dir", "./models/stt/sensevoice")

    @property
    def stt_download_url(self) -> str:
        return self.get("STT", "download_url", "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2")

    @property
    def stt_language(self) -> str:
        return self.get("STT", "language", "auto")

    @property
    def ocr_enabled(self) -> bool:
        return self.getboolean("OCR", "enabled", False)

    @property
    def ocr_vlm_enabled(self) -> bool:
        return self.getboolean("OCR", "vlm_enabled", False)

    @property
    def ocr_provider(self) -> str:
        return self.get("OCR", "provider", "tencent").lower()

    @property
    def ocr_include_process_list(self) -> bool:
        return self.getboolean("OCR", "include_process_list", False)

    @property
    def ocr_sentence_limit(self) -> int:
        return self.getint("OCR", "sentence_limit", 4)

    @property
    def ocr_baidu_api_key(self) -> str:
        return self.get("OCR", "baidu_api_key", "")

    @property
    def ocr_baidu_secret_key(self) -> str:
        return self.get("OCR", "baidu_secret_key", "")

    @property
    def ocr_tencent_secret_id(self) -> str:
        return self.get("OCR", "tencent_secret_id", "")

    @property
    def ocr_tencent_secret_key(self) -> str:
        return self.get("OCR", "tencent_secret_key", "")

    def get_ocr_config(self) -> dict:
        enabled = self.ocr_enabled
        vlm_enabled = self.ocr_vlm_enabled
        provider = self.ocr_provider
        include_process_list = self.ocr_include_process_list
        sentence_limit = self.ocr_sentence_limit
        config = {
            "enabled": enabled,
            "vlm_enabled": vlm_enabled,
            "provider": provider,
            "include_process_list": include_process_list,
            "sentence_limit": sentence_limit
        }

        if not enabled:
            return config

        if provider == "baidu":
            config["api_key"] = self.get_required("OCR", "baidu_api_key")
            config["secret_key"] = self.get_required("OCR", "baidu_secret_key")
        elif provider == "tencent":
            config["secret_id"] = self.get_required("OCR", "tencent_secret_id")
            config["secret_key"] = self.get_required("OCR", "tencent_secret_key")
        else:
            raise RuntimeError(f"CRITICAL CONFIG ERROR: Unsupported OCR provider '{provider}'.")

        return config


    @property
    def physics_enabled(self) -> bool:
        return self.getboolean("Physics", "enabled", False)

    @property
    def physics_gravity(self) -> float:
        return self.getfloat("Physics", "gravity", 300.0)

    @property
    def physics_gravity_enabled(self) -> bool:
        return self.getboolean("Physics", "gravity_enabled", True)

    @property
    def physics_accel_x(self) -> float:
        return self.getfloat("Physics", "accel_x", 0.0)

    @property
    def physics_accel_y(self) -> float:
        return self.getfloat("Physics", "accel_y", 0.0)

    @property
    def physics_accel_enabled(self) -> bool:
        return self.getboolean("Physics", "accel_enabled", False)

    @property
    def physics_invert_forces(self) -> bool:
        return self.getboolean("Physics", "invert_forces", False)

    @property
    def physics_friction(self) -> float:
        return self.getfloat("Physics", "friction", 0.98)

    @property
    def physics_friction_enabled(self) -> bool:
        return self.getboolean("Physics", "friction_enabled", True)

    @property
    def physics_elasticity(self) -> float:
        return self.getfloat("Physics", "elasticity", 0.6)

    @property
    def physics_bounce_enabled(self) -> bool:
        return self.getboolean("Physics", "bounce_enabled", True)

    @property
    def physics_max_speed(self) -> float:
        return self.getfloat("Physics", "max_speed", 2000.0)

    @property
    def physics_drag_velocity_multiplier(self) -> float:
        return self.getfloat("Physics", "drag_velocity_multiplier", 1.2)

    @property
    def physics_drag_velocity_max(self) -> float:
        return self.getfloat("Physics", "drag_velocity_max", 2500.0)

    @property
    def physics_sleep_still_frames(self) -> int:
        return self.getint("Physics", "sleep_still_frames", 10)

    @property
    def physics_sleep_speed_threshold(self) -> float:
        return self.getfloat("Physics", "sleep_speed_threshold", 30)

    @property
    def physics_collide_windows(self) -> bool:
        return self.getboolean("Physics", "collide_windows", True)

    @property
    def physics_ignore_maximized_windows(self) -> bool:
        return self.getboolean("Physics", "ignore_maximized_windows", True)

    @property
    def physics_ignore_fullscreen_windows(self) -> bool:
        return self.getboolean("Physics", "ignore_fullscreen_windows", True)

    @property
    def physics_ignore_borderless_fullscreen(self) -> bool:
        return self.getboolean("Physics", "ignore_borderless_fullscreen", True)

    @property
    def physics_screen_padding(self) -> int:
        return self.getint("Physics", "screen_padding", 0)

    @property
    def physics_refresh_rate(self) -> float:
        return self.getfloat("Physics", "refresh_rate", 0.0)

    @property
    def sovits_enabled(self) -> bool:
        return self.getboolean("SoVITS", "enabled", True)

    @property
    def sovits_device(self) -> str:
        return self.get("SoVITS", "device", "cuda")

    @property
    def sovits_model_version(self) -> str:
        return self.get("SoVITS", "model_version", "v2Pro")

    @property
    def sovits_model_dir(self) -> str:
        return self.get("SoVITS", "model_dir", "./models/sovits")

    @property
    def sovits_temperature(self) -> float:
        return self.getfloat("SoVITS", "temperature", 1.0)

    @property
    def sovits_top_p(self) -> float:
        return self.getfloat("SoVITS", "top_p", 1.0)

    @property
    def sovits_speed(self) -> float:
        return self.getfloat("SoVITS", "speed", 1.0)

    @property
    def sovits_top_k(self) -> int:
        return self.getint("SoVITS", "top_k", 15)

    @property
    def sovits_text_split_method(self) -> str:
        return self.get("SoVITS", "text_split_method", "cut5")

    @property
    def sovits_fragment_interval(self) -> float:
        return self.getfloat("SoVITS", "fragment_interval", 0.25)

    @property
    def sovits_api_port(self) -> int:
        return self.getint("SoVITS", "api_port", 9880)

    @property
    def sovits_timeout(self) -> int:
        return self.getint("SoVITS", "api_timeout", 120)

    @property
    def sovits_kill_existing(self) -> bool:
        return self.getboolean("SoVITS", "kill_existing", True)


    @property
    def mcp_enabled(self) -> bool:
        return self.getboolean("MCP", "enabled", False)

    @property
    def mcp_server_dir(self) -> str:
        return self.get("MCP", "server_dir", "mcpserver")

    @property
    def mcp_startup_timeout(self) -> int:
        return self.getint("MCP", "startup_timeout", 20)

    @property
    def mcp_max_tool_rounds(self) -> int:
        return self.getint("MCP", "max_tool_rounds", 30)


    @property
    def monitor_clipboard(self) -> bool:
        return self.get_bool("General", "monitor_clipboard", True)

    @property
    def monitor_music(self) -> bool:
        return self.get_bool("General", "monitor_music", True)

    @property
    def use_ui_automation(self) -> bool:
        return self.get_bool("Advanced", "use_ui_automation", True)

    @property
    def special_dates_mode(self) -> str:
        return self.get("Advanced", "special_dates_mode", "once")


    @property
    def weather_enabled(self) -> bool:
        return self.getboolean("Weather", "enabled", True)

    @property
    def weather_api_key(self) -> str:
        return self.get("Weather", "api_key", "24760f76c64e469ca1f125800262401")


    @property
    def prompt_source(self) -> str:
        return self.get("Prompt", "source", "file")

    @property
    def prompt_content(self) -> str:
        return self.get("Prompt", "content", "哎呀这里写什么都可以吧。")

    @property
    def prompt_file_path(self) -> str:
        if self.use_pack_settings:
             return self.get("Prompt", "file_path", "")
        return self.get_required("Prompt", "file_path")

    @property
    def enable_ip_context(self) -> bool:
        return self.getboolean("Prompt", "enable_ip_context", True)

    def get_prompt(self) -> str:
        
        target_val = self.prompt_file_path 
        
        if self.use_pack_settings:
            logic_info = self.pack_manager.get_info("logic", {})
            prompts = logic_info.get("prompts", [])
            
            if not prompts:
                pack_id = self.pack_manager.active_pack_id
                print(f"[Config] Error: No 'prompts' found in 'logic' section of pack.json for pack '{pack_id}'")
                print(f"[Config] logic_info content: {logic_info}")
                raise RuntimeError(f"CRITICAL: Active pack '{pack_id}' has no prompts defined in its pack.json.")
            
            target_prompt = next((p for p in prompts if p.get("id") == target_val), None)
            
            if not target_prompt:
                 target_prompt = next((p for p in prompts if p.get("id") == "default"), None)
            
            if not target_prompt:
                target_prompt = prompts[0]
            
            rel_path = target_prompt.get("path")
            pack_root = self.pack_manager.packs_dir / self.pack_manager.active_pack_id
            full_path = pack_root / rel_path
            
            if full_path.exists():
                return full_path.read_text(encoding="utf-8")
            
            default_prompt_path = self.pack_manager.get_path("logic", "prompts")
            if default_prompt_path:
                prompt_dir = default_prompt_path.parent
                legacy_path = prompt_dir / target_val
                if legacy_path.exists():
                     return legacy_path.read_text(encoding="utf-8")

            raise RuntimeError(f"CRITICAL: Prompt file for ID '{target_val}' or path '{rel_path}' not found.")

        if self.prompt_source == "string":
            return self.prompt_content
            
        filename = self.prompt_file_path
        default_prompt_path = self.pack_manager.get_path("logic", "prompts")
        
        if default_prompt_path:
            prompt_dir = default_prompt_path.parent
            target_path = prompt_dir / filename
            
            if target_path.exists() and target_path.is_file():
                try:
                    return target_path.read_text(encoding="utf-8")
                except Exception as e:
                    print(f"[Config] Error reading prompt file: {e}")
            
            if default_prompt_path.exists():
                return default_prompt_path.read_text(encoding="utf-8")
        
        raise RuntimeError(f"CRITICAL: Required prompt file '{filename}' not found in active pack and no default available.")

    def get_llm_config(self) -> dict:
        mode = self.get("General", "llm_mode", "cloud").lower()
        

        if mode == "local":
            return {
                "model_type": "local",
                "api_key": self.get_required("Model_Local", "api_key"),
                "base_url": self.get_required("Model_Local", "base_url"),
                "model_name": self.get("Model_Local", "model_name", "qwen2.5:7b"),
                "temperature": self.getfloat("Model_Local", "temperature", 0.95),
                "top_p": self.getfloat("Model_Local", "top_p", 1.0),
                "max_tokens": self.getint("Model_Local", "max_tokens", 768)
            }
            

        model_id = self.model_select
        target_section = f"Model_{model_id}"
        for s in self.config.sections():
            if s.startswith(f"Model_{model_id}"):
                target_section = s
                break
                
        return {
            "model_type": model_id,
            "api_key": self.get_required(target_section, "api_key"),
            "base_url": self.get(target_section, "base_url", ""),
            "model_name": self.get(target_section, "model_name", ""),
            "temperature": self.getfloat(target_section, "temperature", 0.95),
            "top_p": self.getfloat(target_section, "top_p", 1.0),
            "max_tokens": self.getint(target_section, "max_tokens", 768)
        }
