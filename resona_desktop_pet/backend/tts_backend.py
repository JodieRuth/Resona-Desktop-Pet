import json
import os
import asyncio
import aiohttp
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
from ..config import ConfigManager
@dataclass
class TTSResult:
    audio_path: Optional[str] = None
    error: Optional[str] = None
    duration: float = 0.0
def log(message):
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] {message}")
class TTSBackend:
    def __init__(self, config: ConfigManager, sovits_log_path: Optional[Path] = None):
        self.config = config
        self.project_root = Path(config.config_path).parent
        self.emotions_config = self._load_emotions_config()
        self.sovits_log_path = sovits_log_path
        self._temp_dir = self.project_root / "TEMP"
        self._temp_dir.mkdir(exist_ok=True)
        self.api_url = f"http://127.0.0.1:{config.sovits_api_port}"
        self.timeout = aiohttp.ClientTimeout(total=config.sovits_timeout)
    def _load_emotions_config(self) -> dict:
        json_path = self.config.pack_manager.get_path("logic", "emotions")
        active_pack = getattr(self.config.pack_manager, "active_pack_id", "")
        print(f"[TTS] Loading emotions config: pack={active_pack} path={json_path}")
        if json_path and json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    log(f"[TTS] Loaded {len(data)} emotions from pack.")
                    return data
            except Exception as e:
                log(f"[TTS] CRITICAL: Error loading pack emotions.json: {e}")
        else:
            log(f"[TTS] Emotions config missing: {json_path}")
        return {}

    def reload_config(self):
        self.emotions_config = self._load_emotions_config()
        active_pack = getattr(self.config.pack_manager, "active_pack_id", "")
        log(f"[TTS] Emotions config reloaded. pack={active_pack} count={len(self.emotions_config)}")
    def _get_emotion_config(self, emotion: str) -> dict:
        target = emotion.split("|")[0] if "|" in emotion else emotion
        if target not in self.emotions_config:
            log(f"[TTS] Warning: Emotion {target} not defined. Falling back.")
            target = "<E:smile>"
        return self.emotions_config.get(target, {})
    def _resolve_ref_audio_path(self, ref_wav: str) -> Path:
        pack_emotion_dir = self.config.pack_manager.get_path("audio", "emotion_dir")
        if pack_emotion_dir:
            path = pack_emotion_dir / ref_wav
            if path.exists():
                return path
        raise FileNotFoundError(f"Reference audio {ref_wav} not found.")
    def _log_sovits_params(self, payload: dict):
        log_file_path = self.sovits_log_path if self.sovits_log_path else self.project_root / "sovits_log.txt"
        models_info = "Unknown models"
        override_config = self.project_root / "models" / "sovits" / "tts_infer_override.yaml"
        if override_config.exists():
            try:
                import yaml
                with open(override_config, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f)
                    ver_key = self.config.sovits_model_version
                    section = config_data.get(ver_key, config_data.get("default", {}))
                    t2s = section.get("t2s_weights_path", "N/A")
                    vits = section.get("vits_weights_path", "N/A")
                    ver = section.get("version", ver_key)
                    models_info = f"GPT: {t2s}, SoVITS: {vits}, Version: {ver}"
            except: pass
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = f"""---
{timestamp} ---
Models: {models_info}
Parameters: {json.dumps(payload, ensure_ascii=False, indent=2)}
"""
        try:
            with open(log_file_path, "a", encoding="utf-8") as f: f.write(log_entry)
        except: pass
    async def load_model(self) -> bool:
        if not self.config.sovits_enabled: return False
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(self.api_url) as response:
                    return response.status in [200, 404, 405]
        except: return False
    async def synthesize(self, text: str, emotion: str = "<E:smile>", language: Optional[str] = None) -> TTSResult:
        if not self.config.sovits_enabled: return TTSResult(error="TTS is disabled")
        log(f"[TTS] Synthesizing: {text[:30]}... ({emotion})")
        if not await self.load_model():
            log("[TTS] SoVITS API not available")
            return TTSResult(error="SoVITS API offline")
        try:
            emotion_config = self._get_emotion_config(emotion)
            if not emotion_config: return TTSResult(error="Emotion config missing")
            ref_wav_path = self._resolve_ref_audio_path(emotion_config["ref_wav"])
            ref_lang = language if language else self.config.tts_language
            prompt_lang = emotion_config.get("ref_lang", "ja")
            
            pack_model_dir = self.config.pack_manager.get_path("models", "sovits")
            gpt_path = None
            sovits_path = None
            if pack_model_dir and pack_model_dir.exists():
                ckpt_files = list(pack_model_dir.glob("*.ckpt"))
                pth_files = list(pack_model_dir.glob("*.pth"))
                if ckpt_files and pth_files:
                    gpt_path = str(sorted(ckpt_files)[0].absolute().as_posix())
                    sovits_path = str(sorted(pth_files)[0].absolute().as_posix())
                    log(f"[TTS] Dynamic model switch detected: {pack_model_dir.name}")

            log(f"[TTS] Using reference audio: {ref_wav_path} with language: {ref_lang} (Prompt: {prompt_lang})")
            output_path = os.path.join(self._temp_dir, f"output_{hash(text) & 0xffffffff}.wav")
            payload = {
                "text": text, "text_lang": ref_lang,
                "ref_audio_path": str(ref_wav_path.absolute()),
                "prompt_text": emotion_config.get("ref_text", ""),
                "prompt_lang": prompt_lang,
                "top_k": int(self.config.sovits_top_k), "top_p": float(self.config.sovits_top_p),
                "temperature": float(self.config.sovits_temperature), "speed_factor": float(self.config.sovits_speed),
                "media_type": "wav", "streaming_mode": False,
                "text_split_method": self.config.sovits_text_split_method,
                "fragment_interval": float(self.config.sovits_fragment_interval),
                "repetition_penalty": 1.35
            }
            
            if gpt_path and sovits_path:
                payload["gpt_method"] = "set_gpt_weights"
                payload["gpt_path"] = gpt_path
                payload["sovits_method"] = "set_sovits_weights"
                payload["sovits_path"] = sovits_path

            self._log_sovits_params(payload)
            log(f"[TTS] Sending request to {self.api_url}/tts")
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(f"{self.api_url}/tts", json=payload) as response:
                    log(f"[TTS] API response status: {response.status}")
                    if response.status == 200:
                        audio_data = await response.read()
                        log(f"[TTS] Received {len(audio_data)} bytes of audio data")
                        with open(output_path, "wb") as f: f.write(audio_data)
                        log(f"[TTS] Audio saved to: {output_path}")
                        if os.path.getsize(output_path) == 0: return TTSResult(error="Generated audio is empty")
                        import soundfile as sf
                        try:
                            data, sr = sf.read(output_path)
                            duration = len(data) / sr
                            log(f"[TTS] Audio duration: {duration:.2f}s")
                            return TTSResult(audio_path=output_path, duration=duration)
                        except Exception as e:
                            log(f"[TTS] Failed to read audio duration: {e}")
                            return TTSResult(audio_path=output_path, duration=0.0)
                    else:
                        error_text = await response.text()
                        log(f"[TTS] API error: {response.status} - {error_text}")
                        return TTSResult(error=f"API error {response.status}")
        except Exception as e:
            log(f"[TTS] Synthesis failed: {e}")
            traceback.print_exc()
            return TTSResult(error=str(e))
    async def synthesize_fallback(self, text: str, emotion: str = "<E:smile>") -> TTSResult:
        emotion_config = self._get_emotion_config(emotion)
        ref_wav_path = self.project_root / "gsv" / emotion_config["ref_wav"]
        if ref_wav_path.exists():
            return TTSResult(audio_path=str(ref_wav_path))
        return TTSResult(error="No fallback")
    def cleanup(self) -> None:
        import shutil
        if os.path.exists(self._temp_dir): shutil.rmtree(self._temp_dir, ignore_errors=True)
    def __del__(self):
        self.cleanup()
