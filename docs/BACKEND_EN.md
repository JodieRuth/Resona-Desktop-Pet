# ⚙️ Backend Service Modules

Located in `resona_desktop_pet/backend/`, these modules handle AI logic and audio processing.

## 1. LLM Module (`llm_backend.py`)
Handles communication with various LLM APIs.
- **History Management**: The `ConversationHistory` class automatically maintains the last N rounds of dialogue.
- **Multi-Model Adapters**:
  - `query_openai_compatible`: Supports DeepSeek, GPT-4, LocalLLM, etc.
  - `query_gemini`: Specifically adapted for Google Gemini's history format.
  - `query_claude`: Supports Anthropic Claude.
- **Thinking Process Support**: Extracts and logs `<think>` tag content from models like R1 and Claude.
- **Automatic Parsing**: Robustly parses LLM JSON responses into `LLMResponse` objects (emotion, display text, TTS text).
- **OCR Context (Optional)**: Provides screen text recognition and prompt injection for environmental awareness. Enabling this feature will send screen content to third-party OCR services, potentially including sensitive information. Users assume all risks associated with this feature.

## 2. TTS Module (`tts_backend.py`)
Converts text to speech.
- **GPT-SoVITS Integration**: Communicates with the local inference server via HTTP API.
- **Emotion Mapping**: Maps LLM emotion tags (e.g., `<E:smile>`) to specific reference audio (`ref_wav`) and annotation text (`ref_text`) defined in the active pack's `emotions.json`.
- **Dynamic Loading**: Automatically updates reference assets when switching resource packs without restarting.

## 3. STT Module (`stt_backend.py`)
Handles speech recognition.
- **SenseVoice Engine**: Uses the offline SenseVoice model for high-speed and accurate recognition. The `setup.ps1` installation script in this project downloads and uses the SenseVoiceSmall speech recognition model developed and open-sourced by Alibaba Group (FunASR), following the FunASR Model License 1.1. This script uses the ONNX converted version provided by the k2-fsa / sherpa-onnx project.
- **Voice Activity Detection (VAD)**: Automatically stops recording and starts recognition after a period of silence.
- **Hotkey Binding**: Supports global hotkeys (default `Ctrl+Shift+I`) to trigger voice interaction.

## 4. SoVITS Manager (`sovits_manager.py`)
Manages the SoVITS background process.
- **Lifecycle Management**: Automatically locates the `GPT-SoVITS` path, starts the API server on launch, and cleans up processes on exit.
- **Runtime Support**: Supports starting via the project's built-in streamlined runtime environment.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
