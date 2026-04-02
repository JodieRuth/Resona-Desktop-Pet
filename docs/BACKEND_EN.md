# ⚙️ Backend Service Modules

Located in `resona_desktop_pet/backend/`, these modules handle AI logic and audio processing.

## 1. LLM Module (`llm_backend.py`)
Handles communication with various LLM APIs.
- **Unified Calling**: Based on the `litellm` library for unified LLM API calls, supporting 100+ models.
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

### 2.1 Remote TTS Mode (`tts_remote_handler.py`)
Supports connecting to a remote SoVITS server for distributed speech synthesis.
- **Server Discovery**: Automatically discovers SoVITS servers on the local network via UDP broadcast.
- **WebSocket Communication**: Uses WebSocket to establish persistent connections with remote servers, transmitting text in real-time and receiving audio data.
- **Multi-Pack Support**: Remote servers can load voice models for multiple resource packs simultaneously, with clients able to switch dynamically.
- **Configuration**: Set `mode = server` in `config.cfg` and configure `server_host` and `server_port`.

```ini
[SoVITS]
mode = server              # local=local mode, server=remote mode
server_auto_discover = true # Whether to auto-discover servers
server_host = 127.0.0.1    # Remote server address
server_port = 9876         # Remote server WebSocket port
```

## 3. STT Module (`stt_backend.py`)
Handles speech recognition.
- **SenseVoice Engine**: Uses the offline SenseVoice model for high-speed and accurate recognition. The `setup.ps1` installation script in this project downloads and uses the SenseVoiceSmall speech recognition model developed and open-sourced by Alibaba Group (FunASR), following the FunASR Model License 1.1. This script uses the ONNX converted version provided by the k2-fsa / sherpa-onnx project.
- **Voice Activity Detection (VAD)**: Automatically stops recording and starts recognition after a period of silence.
- **Hotkey Binding**: Supports global hotkeys (default `Ctrl+Shift+I`) to trigger voice interaction.

## 4. SoVITS Manager (`sovits_manager.py`)
Manages the SoVITS background process.
- **Lifecycle Management**: Automatically locates the `GPT-SoVITS` path, starts the API server on launch, and cleans up processes on exit.
- **Runtime Support**: Supports starting via the project's built-in streamlined runtime environment.

### 4.1 SoVITS Server Mode (`sovits_server.py`)
Allows SoVITS to run as a standalone server, providing speech synthesis services to multiple clients.
- **Standalone Operation**: Launched independently via `run_sovits_server.py`, without depending on the main program.
- **WebSocket Interface**: Provides WebSocket interfaces for remote client connections.
- **Service Discovery**: Automatically announces service via UDP broadcast (port 19876) for easy client discovery.
- **Multi-Client Support**: Supports simultaneous connections from multiple clients, each with independent pack switching.
- **Multi-Pack Management**: Servers can load model weights for multiple resource packs simultaneously, supporting runtime switching.

**Launch Method**:
```bash
python run_sovits_server.py
```

**Configuration** (`config.cfg`):
```ini
[SoVITS]
device = cuda              # Server compute device (cuda/cpu)
sovits_api_port = 9880     # SoVITS API port
```

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

## 8. Timer Module (`timer_backend.py`)
Responsible for scheduled task scheduling and management.
- **Inbox Mechanism**: MCP tools write scheduled tasks to a JSON inbox, which the main program polls and reads.
- **Task Queue**: Internally maintains a task queue, supporting persistence of unfinished tasks.
- **Pre-synthesis Voice**: Can pre-synthesize voice before task trigger for zero-latency reminders.
- **Configuration**: Configured through the `[Timer]` section in `config.cfg`.

## 9. Long-Term Memory System (`memory/`)
Located in `memory/`, providing long-term memory capabilities beyond conversation history.

### 9.1 Memory Manager (`memory_manager.py`)
Core memory management module responsible for memory storage and retrieval.
- **SQLite Database Storage**: Uses SQLite for persistent storage of memories and conversation history.
- **Per-Pack Isolation**: Supports memory isolation by resource pack (`per_pack_memory = true`), giving each character independent memory space.
- **Conversation History Logging**: Automatically records all conversations, supporting time-range queries.
- **Memory Injection**: Automatically injects relevant memories into the System Prompt before LLM calls.

### 9.2 Vector Store (`vector_store.py`)
Vector embedding-based semantic memory system supporting similarity search.
- **ONNX Model Support**: Uses ONNX format sentence embedding models (e.g., sentence-transformers).
- **Semantic Retrieval**: Encodes memory content as vectors, supporting semantic similarity search.
- **Optional Enablement**: Enable via `vector_enabled = true`, requires downloading ONNX models to the specified directory.
- **Model Path Configuration**:
```ini
[Memory]
vector_enabled = true
vector_model_path = memory/sentence-transformers
vector_model_file = onnx/model_quint8_avx2.onnx
```

### 9.3 Startup Processor (`startup_processor.py`)
Processes previous session memories on program startup.
- **Session Summarization**: Uses independently configured LLM to analyze previous session content and extract important information.
- **Memory Conversion**: Converts temporary sessions into long-term memory storage.
- **Independent Configuration**: Supports using different LLM configurations from the main program for memory processing.

**Memory System Configuration** (`config.cfg`):
```ini
[Memory]
enabled = true                    # Enable long-term memory
per_pack_memory = true            # Isolate memory by resource pack
force_operation = true            # Force LLM to use memory tools
startup_processing = true         # Process previous session on startup
startup_base_url =                # LLM address for memory processing (empty uses main config)
startup_api_key =                 # API Key for memory processing
startup_model_name = deepseek-chat # Model for memory processing
conversation_retention_days = 30  # Conversation history retention days (0=permanent)
```

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
