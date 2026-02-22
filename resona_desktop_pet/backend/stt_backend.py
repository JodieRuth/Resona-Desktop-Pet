import asyncio
import os
import tarfile
import threading
import wave
import requests
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
from ..config import ConfigManager
from ..cleanup_manager import register_cleanup
@dataclass
class STTResult:
    text: str = ""
    error: Optional[str] = None
    duration: float = 0.0
def log(message):
    from datetime import datetime
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{timestamp}] [STT] {message}")
class STTBackend:
    def __init__(self, config: ConfigManager):
        self.config = config
        self.project_root = Path(config.config_path).parent
        self._recognizer = None
        self._stream = None
        self._is_recording = False
        self._audio_data = []
        self._sample_rate = 16000
        self._model_loaded = False
        self._record_thread: Optional[threading.Thread] = None
        self._silence_counter = 0
        self._hotkey_registered = False
        self._loaded_language = None
        register_cleanup(self.cleanup)
        log("STTBackend initialized (Model not loaded yet)")

    def _get_model_path(self) -> Path:
        model_dir = self.project_root / self.config.stt_model_dir
        if model_dir.exists():
            has_onnx = any(f.name.endswith(".onnx") for f in model_dir.iterdir())
            if has_onnx:
                return model_dir
        for item in model_dir.iterdir() if model_dir.exists() else []:
            if item.is_dir() and "sense" in item.name.lower():
                return item
        return model_dir

    def _download_model(self, url: str, target_dir: Path) -> Optional[Path]:
        if not url: return None
        log(f"Downloading STT model from {url}")
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = url.split("/")[-1]
        target_path = target_dir / filename
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            with open(target_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
            log(f"Download complete: {target_path}")
            return target_path
        except Exception as e:
            log(f"Download failed: {e}")
            if target_path.exists(): target_path.unlink()
            return None

    async def load_model(self) -> bool:
        current_lang = self.config.stt_language
        if current_lang.lower() == "auto":
            current_lang = ""

        if self._model_loaded and self._loaded_language == current_lang:
            return True

        if not self.config.stt_enabled: 
            log("STT is disabled in config")
            return False
        model_dir = self._get_model_path()
        log(f"Checking model in: {model_dir}")
        base_dir = self.project_root / self.config.stt_model_dir
        has_model = False
        if model_dir.exists():
            for f in model_dir.rglob("*.onnx"):
                has_model = True
                break
        if not has_model:
            log("Model files not found, checking for archives...")
            archive_found = False
            for archive in base_dir.iterdir() if base_dir.exists() else []:
                if archive.suffix in [".bz2", ".tar.gz", ".zip"]:
                    log(f"Found archive: {archive.name}, extracting...")
                    await self._extract_model(archive, base_dir)
                    archive_found = True
                    break
            if not archive_found and self.config.stt_download_url:
                log("No model or archive found, attempting download...")
                archive_path = await asyncio.to_thread(self._download_model, self.config.stt_download_url, base_dir)
                if archive_path: await self._extract_model(archive_path, base_dir)
            model_dir = self._get_model_path()
            log(f"Final model search path: {model_dir}")
        if not model_dir.exists(): 
            log(f"CRITICAL: Model directory {model_dir} does not exist.")
            return False
        try:
            import sherpa_onnx
            model_file, tokens_file = None, None
            for f in model_dir.iterdir():
                if f.name.endswith(".onnx"): model_file = f
                elif f.name == "tokens.txt": tokens_file = f
            if not model_file or not tokens_file: 
                log(f"CRITICAL: Missing files in {model_dir}. Need .onnx and tokens.txt")
                return False
            log(f"Loading SenseVoice model: {model_file.name} (Lang: {current_lang or 'auto'})")
            self._recognizer = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(model_file.absolute()), 
                tokens=str(tokens_file.absolute()), 
                num_threads=4, 
                use_itn=True, 
                debug=False,
                language=current_lang
            )
            self._model_loaded = True
            self._loaded_language = current_lang
            log("SenseVoice model loaded successfully.")
            return True
        except Exception as e: 
            log(f"Failed to initialize sherpa-onnx: {e}")
            return False

    async def _extract_model(self, archive_path: Path, target_dir: Path) -> None:
        await asyncio.get_event_loop().run_in_executor(None, self._extract_sync, archive_path, target_dir)

    def _extract_sync(self, archive_path: Path, target_dir: Path) -> None:
        try:
            log(f"Extracting {archive_path} to {target_dir}...")
            with tarfile.open(archive_path, "r:bz2") as tar: tar.extractall(target_dir)
            log("Extraction complete.")
        except Exception as e:
            log(f"Extraction failed: {e}")

    def register_hotkey(self, callback: Callable[[], None]) -> bool:
        if self._hotkey_registered: return True
        try:
            import keyboard
            log(f"Registering STT hotkey: {self.config.stt_hotkey}")
            keyboard.add_hotkey(self.config.stt_hotkey, callback)
            self._hotkey_registered = True
            log("STT hotkey registered successfully.")
            return True
        except Exception as e:
            log(f"Failed to register STT hotkey: {e}")
            return False

    def unregister_hotkey(self) -> None:
        if not self._hotkey_registered: return
        try:
            import keyboard
            keyboard.unhook_all()
            self._hotkey_registered = False
        except Exception: pass

    async def start_recording(self, on_complete: Optional[Callable[[STTResult], None]] = None) -> None:
        if self._is_recording: return
        
        current_lang = self.config.stt_language
        if current_lang.lower() == "auto":
            current_lang = ""
            
        if not self._model_loaded or self._loaded_language != current_lang:
            if not await self.load_model():
                if on_complete: on_complete(STTResult(error="Model not loaded"))
                return
        self._is_recording = True
        self._audio_data, self._silence_counter = [], 0
        self._record_thread = threading.Thread(target=self._record_audio, args=(on_complete,), daemon=True)
        self._record_thread.start()

    def _record_audio(self, on_complete: Optional[Callable[[STTResult], None]]) -> None:
        try:
            import pyaudio
            import numpy as np
            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=self._sample_rate, input=True, frames_per_buffer=1024)
            max_duration = self.config.stt_max_duration
            silence_timeout = self.config.stt_silence_threshold
            max_frames = int(max_duration * self._sample_rate / 1024)
            silence_threshold_frames = int(silence_timeout * self._sample_rate / 1024)
            log(f"Recording started (Max: {max_duration}s, Silence Timeout: {silence_timeout}s)")
            frames_recorded, silence_frames = 0, 0
            VOL_THRESHOLD = 20
            MIN_DURATION = 2.0
            while self._is_recording and frames_recorded < max_frames:
                data = stream.read(1024, exception_on_overflow=False)
                self._audio_data.append(data)
                frames_recorded += 1
                volume = np.abs(np.frombuffer(data, dtype=np.int16)).mean()
                if volume < VOL_THRESHOLD:
                    silence_frames += 1
                    if silence_frames >= silence_threshold_frames:
                        if frames_recorded * 1024 / self._sample_rate > MIN_DURATION:
                            log("Silence detected, stopping recording.")
                            break
                else:
                    silence_frames = 0
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            self._is_recording = False
            log("Recording finished. Recognizing...")
            result = self._recognize_audio()
            if on_complete: on_complete(result)
        except Exception as e:
            self._is_recording = False
            log(f"Recording error: {e}")
            if on_complete: on_complete(STTResult(error=str(e)))

    def recognize_file(self, file_path: str) -> STTResult:
        import numpy as np
        import wave
        log(f"recognize_file start path={file_path}")
        
        if not self._model_loaded:
             try:
                 loop = asyncio.get_event_loop()
                 if loop.is_running():
                     new_loop = asyncio.new_event_loop()
                     try:
                         if not new_loop.run_until_complete(self.load_model()):
                             return STTResult(error="Model load failed")
                     finally:
                         new_loop.close()
                 else:
                     if not loop.run_until_complete(self.load_model()):
                         return STTResult(error="Model load failed")
             except Exception:
                 if not asyncio.run(self.load_model()):
                     return STTResult(error="Model load failed")

        try:
            if not os.path.exists(file_path):
                return STTResult(error="File not found")
            
            with wave.open(file_path, "rb") as wf:
                if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
                    pass
                
                frames = wf.readframes(wf.getnframes())
                samples = np.frombuffer(frames, dtype=np.int16)
                samples = samples.astype(np.float32) / 32768.0

            stream = self._recognizer.create_stream()
            stream.accept_waveform(16000, samples)
            self._recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            log(f"recognize_file done text_len={len(text)}")
            return STTResult(text=text)

        except Exception as e:
            log(f"File recognition error: {e}")
            return STTResult(error=str(e))

    def _recognize_audio(self) -> STTResult:
        if not self._recognizer or not self._audio_data: return STTResult(error="No audio")
        try:
            import numpy as np
            audio_data_bytes = b"".join(self._audio_data)
            audio_float = np.frombuffer(audio_data_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            if len(audio_float) == 0:
                return STTResult(error="Audio buffer empty")

            max_vol = np.max(np.abs(audio_float))
            log(f"Recognizing audio: {len(audio_float)/self._sample_rate:.2f}s, Max Vol: {max_vol:.4f}")

            stream = self._recognizer.create_stream()
            stream.accept_waveform(self._sample_rate, audio_float)
            self._recognizer.decode_stream(stream)
            
            text = stream.result.text.strip()
            return STTResult(text=text, duration=len(audio_float) / self._sample_rate)
        except Exception as e:
            log(f"Recognition error: {e}")
            return STTResult(error=str(e))

    def stop_recording(self) -> None: self._is_recording = False
    def is_recording(self) -> bool: return self._is_recording
    def cleanup(self) -> None: self.stop_recording(); self.unregister_hotkey()
