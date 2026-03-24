# 🚀 Quick Start

Follow these steps to get your ResonaDesktopPet up and running in minutes.

## 0. Prerequisites
**Required Environment**:
- **Microsoft Visual C++ Redistributable (2015-2022)**:
  - Many core libraries (PySide6, NumPy, SoVITS) depend on this.
  - **[Download x64 version from Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe)** and install it.
- **Python 3.12** (if not using the Full Runtime mode in `setup.ps1`).

## 1. Installation
1. **Clone the Repo**: `git clone https://github.com/JodieRuth/Resona-Desktop-Pet.git`
2. **Setup Environment**:
   - Right-click `setup.ps1` and select **"Run with PowerShell"**.
   - **Option 2 (Recommended)**: Creates a dedicated Runtime environment, keeping your system Python clean.
   - **Option 3**: Creates a `.venv` virtual environment in the current directory.
   - The script will automatically download necessary libraries, the default resource pack, and STT models.

## 2. Configure AI Backend
1. Open `config.cfg` in the root directory.
2. **LLM Config**:
   - `model_select`: Select model (1-10 or Local). Supported models:
     - `1`: OpenAI (GPT-4/GPT-3.5)
     - `2`: DeepSeek (default, recommended)
     - `3`: Claude (Anthropic)
     - `4`: Kimi (Moonshot)
     - `5`: Gemini (Google)
     - `6`: Grok (xAI)
     - `7`: Qwen (Alibaba)
     - `8`: GitHub Models
     - `9`: OpenAI Compatible (any OpenAI API-compatible model)
     - `10`: Zhipu (智谱 AI)
     - `Local`: Local models (Ollama, etc.)
   - `api_key`: Enter your API Key.
   - `base_url`: Enter the API endpoint if using third-party services or proxies.
3. **OCR Config (Optional)**:
   - `enabled`: Set to `true` to enable screen recognition context.
   - **Multimodal Models**: Set `vlm_enabled = true` to use multimodal models (like GPT-4V) for direct screen screenshot recognition. OCR will be automatically disabled when VLM is enabled.
   - `provider`: Select `tencent` or `baidu`.
   - **Warning**: Enabling OCR/VLM will send screen captures to third-party services. This may lead to privacy leaks. Use at your own risk.
4. **SoVITS Config**:
   - Ensure you have extracted the SoVITS integrated package to the correct path as per the README.
   - Set `enabled = true` (in `[SoVITS]` section).
5. **Enable MCP (Advanced/Optional)**:
   - Find the `[MCP]` section in `config.cfg`.
   - Set `enabled = true`.
   - **Optional Configurations**:
     - `server_dir`: MCP server working directory (default `mcpserver`)
     - `startup_timeout`: MCP server startup timeout in seconds (default 20)
     - `max_tool_rounds`: Maximum tool call rounds per conversation (default 30)
   - **Note**: Enabling this grants the LLM file read/write and command execution permissions, and will significantly increase Token consumption. Ensure you understand the risks.
6. **Enable HTML Server**:
   - Find the `[HTML]` section in `config.cfg`.
   - Set `enabled = true`.
   - When enabled, runs on port 8000 by default, accessible from other devices on the LAN. Some features are adjusted in HTML mode.
7. **Enable Timer (Optional)**:
   - Find the `[Timer]` section in `config.cfg`.
   - Set `enabled = true` to enable the timer task scheduler.
   - MCP tools can write timer tasks, which the main program will poll and trigger.

## 3. Launch
- Double-click `run.bat`.
- Once the pet appears:
  - **Click it**: Open the dialogue box for text chat.
  - **Press Ctrl+Shift+I**: Start/Stop recording.
  - **Right-click**: Change outfits, switch packs, or open settings.

## 4. Advanced
- To change personality: Edit `packs/Resona_Default/prompts/character_prompt.txt`.
- To add custom behaviors: Run `tools/trigger_editor.py`.
- To replace sprites: Use `tools/sprite_organizer.py`.
- To debug triggers: Set `debugtrigger = true` in `config.cfg`, then run `tools/sensor_mocker.py`.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
