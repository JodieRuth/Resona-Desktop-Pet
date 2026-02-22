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

## 5. MCP Manager (`mcp_manager.py`)
Responsible for Model Context Protocol service management and tool scheduling.
- **Auto-Discovery**: Scans `mcpserver/` directory for `.mcp.json/py/js` files on startup, loading and starting corresponding MCP Servers.
- **Tool Injection**: Converts all discovered tools into LLM-understandable Schemas and injects them into the System Prompt.
- **Security Sandbox**: Communicates with subprocesses via `stdio` pipes, isolating the tool execution environment (though tools themselves may have high privileges, beware of risks with `command_proxy`).
- **Built-in Tools**:
  - `filesystem_tools`: File reading, writing, searching, editing.
  - `command_proxy`: Executes system Shell commands.
  - `timer_inbox`: Writes scheduled tasks to a JSON inbox, polled by the main loop.
  - `ocr_tools`: Calls OCR interfaces to recognize screen content (as a tool call, not passive injection).

## 6. Web Server (`web_server/`)
Local Web service built on FastAPI.
- **API Service**: Provides HTTP interfaces and static file serving.
- **WebSocket (`server.py`)**: Core communication channel supporting persistent connections between clients (e.g., Web UI) and the backend.
  - **State Synchronization**: Pushes pet expression, action, and voice status in real-time.
  - **Remote Control**: Receives commands from clients to control pet behavior.
- **Session Management (`session_manager.py`)**: Supports multi-client connection management.

## 7. Physics Engine (`physics/`)
Located in `resona_desktop_pet/physics/`, providing experimental physics simulation.
- **Verlet Integration**: Uses Verlet algorithm to simulate particle motion trajectories.
- **Collision Detection**: Detects screen edges (`ScreenBoundary`) and window rectangles for bounce effects.
- **State Machine Integration**: Physics states (e.g., "Dragging", "Flying", "Landing") are decoupled but interoperable with the pet's main logic state machine.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
