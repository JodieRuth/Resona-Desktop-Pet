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
   - `model_type`: Select 1 (DeepSeek/OpenAI), 5 (Gemini), or 3 (Claude).
   - `api_key`: Enter your API Key.
   - `base_url`: Enter the API endpoint if using DeepSeek or a proxy (e.g., `https://api.deepseek.com`).
3. **OCR Config (Optional)**:
   - `enabled`: Set to `true` to enable screen recognition context.
   - `provider`: Select `tencent` or `baidu`.
   - **Warning**: Enabling OCR will send screen captures to third-party services. This may lead to privacy leaks. Use at your own risk.
4. **SoVITS Config**:
   - Ensure you have extracted the SoVITS integrated package to the correct path as per the README.
   - Set `sovits_enabled = true`.

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

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
