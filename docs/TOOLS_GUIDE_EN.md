# 🛠️ Developer Tools Guide

The `tools/` directory contains a suite of utilities to help you create and debug resource packs efficiently.

## 1. Trigger Editor (`trigger_editor.py`)
**The most essential tool** for graphically editing `triggers.json`.
- **How to Use**:
  1. Run `trigger_editor.py`.
  2. Select your resource pack from the top-left menu.
  3. Click "Add Trigger" and set an ID.
  4. **Add Conditions**: E.g., CPU Temp > 80 or Mouse Hover > 5s.
  5. **Add Actions**: E.g., `speak` (voice response) or `move_to` (move character).
  6. Click "Save & Sync".
- **Advanced**: Supports nested logic (AND/OR) for intelligent reactions.

## 2. Sensor Mocker (`sensor_mocker.py`)
A powerful tool for debugging triggers.
- **Purpose**: Test logic like "High CPU Warning" or "Full Screen Feedback" without actually stressing your hardware.
- **How to Use**:
  1. Set `debugtrigger = true` in `config.cfg`.
  2. Run `sensor_mocker.py`.
  3. Adjust sliders (e.g., drag CPU temp to 90).
  4. The pet will receive this mocked data in real-time and trigger corresponding reactions.

## 3. Image Preprocessor (`image_processor.py`)
- **Purpose**: Resona's UI uses a 1280x720 canvas. This tool resizes and aligns raw sprites to the **bottom-center** of the canvas automatically.
- **How to Use**: Drag and drop images or folders onto the script.

## 4. Sprite Organizer (`sprite_organizer.py`)
- **Purpose**: Batch renames loose sprite files into a standard format and generates the required `sum.json` based on assigned emotions.
- **How to Use**:
  1. Open the folder containing your sprites.
  2. Assign an emotion tag to each image.
  3. Enter an Outfit ID.
  4. Click generate; it will copy files to the correct pack directory and create the index.

## 5. MCP Toolset (`mcpserver/`)
These scripts are not run directly but are loaded by the main program as MCP Servers for LLM invocation.
- **`filesystem_tools.mcp.py`**: Provides file system read/write capabilities.
- **`command_proxy.mcp.py`**: Provides command line execution capabilities.
- **`timer_inbox.mcp.py`**: Provides scheduled task management capabilities.
- **Developer Guide**: If you want to extend AI capabilities (e.g., controlling smart home devices), refer to the format of these files to write new `.mcp.py` scripts and place them in the `mcpserver/` directory for automatic loading.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
