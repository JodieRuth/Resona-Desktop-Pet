[English](README_EN.md) | [中文](README.md)

# ResonaDesktopPet

ResonaDesktopPet is a versatile desktop pet project that integrates Large Language Models (LLM), Text-to-Speech (SoVITS), and Speech-to-Text (STT) technologies to provide a vivid and natural interactive experience.
Through customized resource packs and a wide variety of events, it offers an experience far beyond that of a typical desktop pet.
Please obtain resource packs compatible with this program on your own.

## 💡 Usage Tips

- **Sprite Aspect Ratio**: The UI does not strictly limit resolution, but please ensure your sprite files are **16:9**.
- **Performance**: TTS speed depends on your inference hardware, while LLM response speed depends on your network quality.
- **Voice Tuning**: If you are unsatisfied with the default voice quality, you can replace the reference audio and annotation text pointed to in `emotion.json` within your resource pack.
- **Language Matching**: It is recommended to keep the model training language, reference audio language, and the `text_tts` output from the LLM consistent. Currently only tested for **Chinese (zh)** and **Japanese (ja)**.

## 🙏 Acknowledgements & Notes

- **Inspiration**: Parts of the code in this project are referenced from [luna-sama](https://github.com/annali07/luna-sama).
- **Core Technology**: Designed specifically for interaction with [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS). Compatibility is only guaranteed for version `v2pro-20250604` and v2Pro models. If you need to train custom model weights, please use the corresponding version.
- **Environment**: The installation script includes a streamlined SoVITS runtime environment (distributed under the MIT license) to lower the barrier to entry.
- **Speech Recognition Component**: The `setup.ps1` installation script in this project downloads and uses the SenseVoiceSmall speech recognition model developed and open-sourced by Alibaba Group (FunASR), following the FunASR Model License 1.1. This script uses the ONNX converted version provided by the k2-fsa / sherpa-onnx project.
- **Project Focus**: Focused on a high-efficiency, lightweight dialogue experience. There are currently no plans to add Live2D support, real-time screen recognition, or complex favorability systems.

## 📚 Detailed Documentation

To help you better understand and use this project, we have prepared detailed documentation:

- **[Core Features](docs/FEATURES_EN.md)**: Explore what this project can do.
- **[Quick Start](docs/QUICK_START_EN.md)**: A step-by-step guide from installation to launch.
- **[Technical Architecture](docs/ARCHITECTURE_EN.md)**: Learn about the internal workings of the project.
- **[Backend Services](docs/BACKEND_EN.md)**: Detailed explanation of LLM, TTS, and STT modules.
- **[UI Components](docs/UI_COMPONENTS_EN.md)**: Breakdown of the UI and interaction logic.
- **[Resource Pack System](docs/RESOURCE_PACKS_EN.md)**: How to create and customize your own characters.
- **[Developer Tools Guide](docs/TOOLS_GUIDE_EN.md)**: Comprehensive guide for the four built-in tools.
- **[Interaction Trigger Guide](docs/TRIGGER_EDITOR_GUIDE_EN.md)**: Learn how to use the editor to make your pet smarter.

## 🌟 Key Features

- **Deep Interaction**: Connects to cloud or local LLMs to give your pet a unique personality and dialogue capabilities.
- **Full Voice Support**: High-quality voice output via SoVITS and semi-real-time voice dialogue via STT.
- **Low-End Friendly**: Can run theoretically without a GPU by using cloud LLMs and setting SoVITS to CPU mode.
- **Automated Deployment**: Provides a comprehensive installation script that supports one-click configuration of virtual environments. A Runtime environment option is available for beginners.

## 🛠️ Technical Architecture

- **UI Framework**: PySide6 (Qt for Python, LGPL license)
- **Language Models**: Supports OpenAI-compatible APIs and various mainstream cloud/local models.
- **Speech Recognition**: Fast offline recognition based on SenseVoice. Uses the default recording device; please ensure clear articulation without background noise.
- **Speech Synthesis**: GPT-SoVITS inference engine.

## 🚀 Quick Start

1. **Download the Project**: Clone this repository.
2. **Run the Installation Script**:
   - Right-click `setup.ps1` and select **"Run with PowerShell"**.
   - Follow the prompts to select an installation mode (Options 2 or 3 recommended) and download the default resource pack.
3. **Configure API Key**:
   - Open `config.cfg` and enter your LLM API Key. You can also use locally deployed LLMs.
4. **Configure SoVITS**:
   - Obtain the SoVITS integrated package from [here](https://github.com/RVC-Boss/GPT-SoVITS/releases/tag/20250606v2pro). Extract it to the `GPT-SoVITS` directory so your path looks like: `ResonaDesktopPet\GPT-SoVITS\GPT-SoVITS-v2pro-20250604\api_v2.py`. Any method works as long as `api_v2.py` exists and can be called by the program.
   - If SoVITS is enabled, the program will start a SoVITS server for real-time speech synthesis upon startup.
5. **Start the Program**:
   - Double-click `run.bat` to begin interacting with your desktop pet.

## 🛠️ Extended Developer Tools (tools/)

This project includes several built-in tools for developers and resource pack creators:

- **Interaction Logic Editor** (`trigger_editor.py`): A GUI for editing `triggers.json` within resource packs. Supports complex conditions (system temperature, process status, time of day, etc.) and sequential actions.
- **Sensor Mocker** (`sensor_mocker.py`): Simulates system parameters (CPU/GPU temp, usage, clipboard content, etc.) for real-time testing of custom triggers. Enable by setting `debugtrigger = true` in `config.cfg`.
- **Image Preprocessor** (`image_processor.py`): Automatically centers and bottom-aligns PNG images, padding them with transparent pixels to 1280*720.
- **Sprite Organizer** (`sprite_organizer.py`): Batch renames and manages sprite assets and generates `sum.json`.
- Refer to the format in the default resource pack to create your own.

## 🔌 Plugin System

This program has a plugin system that allows you to load external .py files from resource packs to customize trigger and action interactions for this program. Note: Only load plugins you trust.

## ⚙️ Trigger System Explained

Using `trigger_editor.py`, you can configure highly personalized reaction logic. Current capabilities include:

### 1. Conditions
- **System Monitoring**: CPU/GPU temperature and usage, battery level (laptop).
- **Software Detection**: Specific process in focus, specific process running in background, process uptime, specific URL visited (Chrome/Edge only), window title keyword matching.
- **User Interaction**: Hover duration, pointer leave duration, long press duration, double-click/combo count, **file drop detection**.
- **Environment Awareness**: Full-screen mode detection, weather matching, currently playing music (Netease Cloud Music only).
- **Time & Date**: Specific dates or time periods.
- **Others**: Idle time detection, resume from idle, clipboard keyword matching.
- **Logic Combinations**: Supports `AND`, `OR`, `CUMULATIVE`, and complex nested logic.

### 2. Actions
- **Speak** (`speak`): Plays specific voice lines with text and emotion tags.
- **Delay** (`delay`): Inserts wait time between actions.
- **Move To** (`move_to`): Moves the pet across the screen.
- **Fade Out** (`fade_out`): Changes pet brightness or transparency.
- **Random Group** (`random_group`): Randomly selects an action from a preset group (experimental).
- **Lock Interaction** (`lock_intermation`): Temporarily disables all interactions (experimental).
- **Exit App** (`exit_app`): Closes the program.

## ⚠️ Copyright & Licensing

- **Code License**: This project's source code is licensed under [CC BY-NC-SA 4.0](LICENSE) (Attribution-NonCommercial-ShareAlike).
- **Non-Commercial Use**: Commercial use of this code, models, or related assets is strictly prohibited.
- **Legal Terms**: For detailed information on disclaimers, asset attribution, and usage risks, please refer to [LEGAL.md](docs/LEGAL_EN.md).

By downloading, installing, debugging, or running any content from this project/repository, you are deemed to have read and agreed to all terms in [LEGAL.md](docs/LEGAL_EN.md). If you do not agree, please stop using and delete the resources immediately.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.