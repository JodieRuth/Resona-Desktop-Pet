# 🖼️ User Interface Components

UI modules are located in `resona_desktop_pet/ui/` and built using PySide6.

## 1. MainWindow (`luna/main_window.py`)
The central UI controller of the application.
- **Frameless Transparent Window**: Achieves the transparent floating effect for the desktop pet, supporting frameless, shadowless, and tool window styles.
- **State Management**: Orchestrates states like "Idle", "Thinking", "Speaking", and "Recording".
- **Interaction Handling**: Manages dragging, scaling (Alt+Scroll), and context menu interactions.
- **Auto Hide/Fade**: Supports automatic hiding in full-screen mode and idle fading after periods of inactivity.
- **Physics Engine Integration**: Bridges with the physics engine to support drag-to-throw, collision bounce, and other physics effects.
- **File Drop Support**: Supports detecting file drop events (in development).
- **Topmost Control**: Periodically reinforces window topmost status to ensure the pet remains visible.

## 2. CharacterView (`luna/character_view.py`)
Responsible for rendering character sprites.
- **Outfit Support**: Indexes different outfit directories based on `sum.json`, supporting runtime switching.
- **Emotion Switching**: Maps emotion tags to specific image files via random or deterministic selection.
- **High-Performance Rendering**: Optimized scaling for smooth display on transparent backgrounds.
- **Mouse Interaction**: Supports detection of mouse hover, click, and drag states.
- **Dynamic Scaling**: Automatically calculates initial scale ratio based on configuration, supports manual scaling with Alt+Scroll.

## 3. IOOverlay (`luna/io_overlay.py`)
The dialogue box component.
- **Unified Input/Output**: Supports both user text input and LLM response display.
- **Auto Positioning**: Automatically adjusts the dialogue box position relative to the character sprite (top-left or top-right).
- **Animations**: Features smooth fading effects for a better visual experience.
- **Character Name Display**: Displays the current character name and username.
- **Regenerate Button**: Supports clicking to regenerate LLM responses.

## 4. Tray Icon (`tray_icon.py`)
- Enables background operation.
- Provides a quick-access menu for settings, pack switching, and exiting.
- **Outfit Switching Menu**: Supports quick switching between different outfits for the current character.
- **Pack Switching Menu**: Supports quick switching between different character resource packs.

## 5. Settings Dialog (`settings_dialog.py`)
- **Advanced Settings**: Provides detailed configuration for API keys, TTS parameters, UI behavior, physics engine, and more.
- **Multi-Tab**: Organizes settings by functional categories (General, LLM, STT, SoVITS, Physics, Behavior, etc.).
- **Real-time Save**: Configuration changes can be saved and applied immediately.
- **Model Selection**: Supports selecting different LLM providers and models.

## 6. Debug Panel (`debug_panel.py`)
Developer tool for testing and debugging.
- **Manual Response Trigger**: Allows manually specifying emotion tags, display text, and TTS text to simulate LLM responses.
- **Emotion Selection**: Dropdown selection of available emotion tags.
- **TTS Language Switching**: Supports switching text-to-speech languages.
- **Quick Operations**: Facilitates developers in testing pet behavior under specific scenarios.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
