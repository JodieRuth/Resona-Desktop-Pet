# 🛠️ Technical Architecture

This project adopts a modular design, divided into the UI Layer, Logic Control Layer, and Backend Service Layer.

## 1. Core Technology Stack
- **UI Framework**: PySide6 (Python + Qt)
- **LLM**: OpenAI API compatible / Gemini API / Claude API (unified via litellm library)
- **TTS**: GPT-SoVITS (Local inference server)
- **STT**: SenseVoice (Offline engine based on sherpa-onnx)
- **Image Processing**: Pillow (PIL)
- **Web Services**: FastAPI + WebSocket
- **Physics Engine**: Custom Verlet integration physics engine (experimental)

## 2. Directory Structure
```text
D:\GitHub\Resona-Desktop-Pet\
├── main.py                     # Entry point
├── config.cfg                  # Main configuration file
├── resona_desktop_pet/         # Core source code
│   ├── backend/                # Backend services (LLM/TTS/STT/MCP)
│   │   ├── llm_backend.py      # LLM calls and conversation history management
│   │   ├── tts_backend.py      # Text-to-speech interface
│   │   ├── stt_backend.py      # Speech-to-text interface
│   │   ├── sovits_manager.py   # SoVITS process management
│   │   └── mcp_manager.py      # MCP tools management
│   ├── config/                 # Configuration and pack management
│   │   ├── config_manager.py   # Configuration manager
│   │   └── pack_manager.py     # Resource pack manager (includes plugin loading)
│   ├── ui/                     # User interface components
│   │   ├── luna/               # Main UI module
│   │   │   ├── main_window.py  # Main window
│   │   │   ├── character_view.py # Character sprite display
│   │   │   └── io_overlay.py   # Dialogue box component
│   │   ├── tray_icon.py        # System tray icon
│   │   ├── settings_dialog.py  # Settings dialog
│   │   └── debug_panel.py      # Debug panel
│   ├── physics/                # Physics engine (experimental)
│   │   ├── engine.py           # Physics calculation core
│   │   ├── bridge.py           # Physics engine to UI bridge
│   │   └── env_scanner.py      # Environment scanner (window detection)
│   ├── web_server/             # Web services and remote control
│   │   ├── server.py           # FastAPI server
│   │   └── session_manager.py  # WebSocket session management
│   ├── utils/                  # Utility functions
│   │   └── audio_utils.py      # Audio processing utilities
│   ├── behavior_monitor.py     # System monitoring and trigger logic core
│   └── cleanup_manager.py      # Process cleanup manager
├── packs/                      # Resource pack storage
├── tools/                      # Development and debugging tools
├── mcpserver/                  # MCP tool scripts directory
└── docs/                       # Project documentation
```

## 3. Workflow
1. **Initialization**:
   - Loads `config.cfg` and the selected `pack.json`.
   - Initializes UI (MainWindow) and Backend Services (LLM/TTS/STT/MCP).
   - Starts `BehaviorMonitor` to listen for system events and user interactions.
   - If enabled, starts the Web server and physics engine.
2. **Active Interaction**:
   - User clicks the sprite or uses a hotkey to start STT.
   - STT converts voice to text and sends it to the LLM.
   - LLM generates a JSON response with emotion tags based on the prompt.
   - TTS Backend synthesizes voice based on emotion tags; UI displays text and updates sprite emotions.
3. **Passive Interaction (Triggers)**:
   - `BehaviorMonitor` polls sensor data (CPU/GPU, etc.) or listens to system hooks (window switching).
   - Matches conditions defined in the pack's `triggers.json`.
   - Executes feedback sequences as defined in `actions` (speak, move, fade, etc.).
4. **Web Remote Control** (Optional):
   - Supports remote device control via WebSocket connections.
   - Provides HTTP API for status retrieval and command sending.

## 4. Decoupled Backend Services
- **LLMBackend**: Wraps API calls from different providers into a unified `LLMResponse` object. Supports thought process extraction, OCR context injection, and IP geolocation context.
- **TTSBackend**: Communicates with GPT-SoVITS via HTTP API, dynamically fetching reference audio from the active pack.
- **STTBackend**: Runs in a separate thread, capturing audio via `pyaudio` and performing local recognition using `sherpa-onnx`. Supports VAD automatic silence detection.
- **MCPManager**: Manages Model Context Protocol tools, automatically scans the `mcpserver/` directory to load tool scripts, and injects tool descriptions into the LLM's System Prompt.
- **SoVITSManager**: Manages the startup and shutdown of the SoVITS inference server, automatically finds and starts `api_v2.py`.

## 5. Physics Engine (Experimental)
- **Verlet Integration**: Uses Verlet algorithm to simulate particle motion trajectories.
- **Collision Detection**: Detects screen boundaries and window rectangles to implement bounce effects.
- **State Tracking**: Records bounce count, window collision count, fall distance, etc., which can be used as trigger conditions.
- **Flexible Configuration**: Configure gravity, friction, elasticity, and other parameters via the `[Physics]` section in `config.cfg`.

## 6. Resource Pack and Plugin System
- **PackManager**: Manages resource pack loading, supports multiple character switching.
- **Plugin Loading**: Supports dynamic loading of Python scripts from the `plugins/` directory in resource packs to extend triggers and actions.
- **Multi-Outfit Support**: A character can be configured with multiple outfits and switch between them at runtime.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
