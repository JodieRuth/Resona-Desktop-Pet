# 🎨 Desktop Pet: Beginner's Resource Pack Creation & Modification Guide

This guide is designed for **absolute beginners** with no programming experience. We will walk you through how to modify existing characters or create your very own desktop companion from scratch.

---

## 📂 Step 1: Meet the Resource Pack "Home"

In the project folder, all characters live in the `packs` directory.
- `packs/Example_Pack`: This is a perfect template. We recommend **never deleting it directly**; instead, "Copy -> Modify" it to create a new character.

### A complete resource pack looks like this:
```text
My_Resource_Pack/
├── assets/                # 【Body】Stores sprites and sound effects
│   ├── sprites/           # Sprite images (Supports PNG/WebP)
│   │   └── Outfit_Folder/ # One folder per outfit
│   │       └── sum.json   # Index for expressions in this outfit
│   └── audio/             # Preset sound effects (usually for triggers.json)
├── logic/                 # 【Soul】The pet's thinking logic
│   ├── emotions.json      # Mapping between emotions, voice, and sprites
│   ├── triggers.json      # When to do what (Triggers)
│   ├── thinking.json      # Random text used while thinking
│   ├── listening.json     # Random text used while recording
│   └── error_config.json  # Error handling config (optional)
├── models/                # 【Voice Core】Voice synthesis models
│   └── sovits/            # Place GPT-SoVITS .pth and .ckpt files here
├── prompts/               # 【Personality】AI personality scripts
│   ├── character_prompt.txt # Default personality
│   └── other_prompt.txt     # Optional personalities (e.g., "Dark", "Young")
├── plugins/               # 【Superpowers】Python scripts for extended features
│   └── system_extension.py  # Example plugin
├── pack.json              # 【ID Card】Name, author, model paths, etc.
├── icon.ico               # 【Icon】Exclusive tray icon (optional)
└── README.md              # Introduction to your resource pack
```

---

## 🆔 Step 2: Modify the "ID Card" (`pack.json`)

This is the most critical step, as it determines how the program reads your resources. Open `pack.json` with a text editor (VS Code or Notepad++ recommended).

### Basic Info (`pack_info`):
- **`id`**: Unique identifier for the resource pack (English, no spaces).
- **`name`**: What is your character's name? (Shows up in settings).
- **`author`**: Write your name here.
- **`version`**: Version number (e.g., "1.0.0").

### Character Settings (`character`):
- **`name`**: The name the pet calls itself in conversation.
- **`username_default`**: Default username (displayed in the dialog box).
- **`tts_language`**: Voice language (`ja` for Japanese, `zh` for Chinese, `en` for English, `ko` for Korean).
- **`outfits`**: You can configure **multiple outfits** here!
    - `id`: Outfit identifier (English).
    - `name`: Outfit display name.
    - `path`: Path to the folder under `assets/sprites/`.
    - `is_default`: Whether this is the default outfit (`true` or `false`, only one allowed).

### Voice Model (`sovits_model`):
- **`vits_weights`**: Path to the `.pth` file (relative to the pack root).
- **`gpt_weights`**: Path to the `.ckpt` file (relative to the pack root).

### Logic Config (`logic`):
- **`prompts`**: You can configure **multiple personalities**!
    - Each item has an `id` and a `path` (pointing to files in the `prompts/` folder).
- **`emotions`**: Path to `emotions.json`.
- **`triggers`**: Path to `triggers.json`.
- **`thinking`**: Path to `thinking.json`.
- **`listening`**: Path to `listening.json`.
- **`plugins`**: Plugin directory path (optional).

### Audio Config (`audio`):
- **`emotion_audio_dir`**: Root directory for emotion reference audio.

### Other Attributes:
- **`icon.ico`**: If you place an `icon.ico` in the root of the resource pack, the tray icon will change when you switch to this pack!

---

## 🎭 Step 3: Configure Sprites (Make it "Move")

The sprites in this project are not animation files but a switch between multiple static images.

1.  **Prepare Images**: Put your sprite images into the `assets/sprites/Your_Outfit_Name/` folder.
2.  **Image Requirements**:
    - Images should ideally be transparent PNGs.
    - Recommended resolution is 1280×720 (16:9 aspect ratio).
    - The sprite subject should be at the bottom of the image; the program will automatically align it to the bottom center.
    - *Tip*: If your sprites are different sizes, use the built-in tool `tools/image_processor.py`. It will automatically align and pad images to 1280×720.
3.  **Write the Index (`sum.json`)**: Create `sum.json` in the image folder.
    - Format: `"<E:expression_name>": ["image_file1", "image_file2"]`
    - Example: `"<E:smile>": ["happy_01", "happy_02"]`. When the pet is happy, it will randomly pick one of these files to display.
    - Common expression tags: `<E:smile>`, `<E:angry>`, `<E:sad>`, `<E:serious>`, `<E:thinking>`, `<E:surprised>`, `<E:dislike>`, `<E:smirk>`, `<E:embarrassed>`
    - Use `tools/sprite_organizer.py` to graphically organize images and automatically generate `sum.json`.

---

## 🧠 Step 4: Shape the Personality (`prompts/character_prompt.txt`)

This is the most magical step. The text you write here determines the pet's "soul."

- **Background**: Who is it? Where is it from?
- **Traits**: Is it a gentle girl next door or a sharp-tongued tsundere?
- **Speaking Style**: What tone does it use? Any catchphrases?
- **Constraints**:
    - Don't be too wordy (suggested limit: 4 sentences).
    - Don't admit to being an AI.
    - Don't break character.
- **Format Requirement**: **Never change the JSON format instructions at the bottom of the file**, or the pet's expressions and voice will break!

### Prompt Example Structure:
```
You are [character name], a [trait] [identity].
You speak [speaking style] and like [hobbies].
Your attitude toward the user is [attitude].

[Other settings...]

--- Do not modify below this line ---
You need to reply in JSON format...
```

---

## 🗣️ Step 5: Voice & Emotion (`logic/emotions.json`)

This project uses SoVITS technology. To make the pet speak with emotion, you need to provide a "reference audio" for each expression.

1.  **Place Models**: Put your trained `.pth` and `.ckpt` files in `models/sovits/` and configure the paths in `pack.json` (see Step 2).
2.  **Prepare Reference Audio**: Record or clip reference audio for each emotion (suggested 3-10 seconds) and place them in the `assets/audio/` directory.
3.  **Write `emotions.json`**:
```json
{
  "<E:smile>": {
    "ref_wav": "audio/smile_ref.wav",
    "ref_text": "Reference audio text content",
    "ref_lang": "ja"
  },
  "<E:angry>": {
    "ref_wav": "audio/angry_ref.wav",
    "ref_text": "Reference audio text content",
    "ref_lang": "ja"
  }
}
```
- **`ref_wav`**: Path to reference audio (relative to the pack root).
- **`ref_text`**: What is being said in that audio (needs to be accurate).
- **`ref_lang`**: The language of the audio (`zh` for Chinese, `ja` for Japanese, `en` for English, `ko` for Korean).

*Don't have a model? You'll need to train a GPT-SoVITS model yourself. There are many tutorials available online.*

---

## ⚡ Step 6: Set Triggers (Make it Smart)

This is key to making the pet feel "alive." For example: it cheers for you when you open a game, or complains if you haven't interacted with it for a long time.

### Beginner's Tool: `tools/trigger_editor.py`
1.  Double-click to run `tools/trigger_editor.py`.
2.  Select your resource pack from the dropdown in the top-left corner.
3.  Click "Add Trigger" to create a new rule.
4.  **Add Conditions**:
    - `cpu_temp` / `gpu_temp`: CPU/GPU temperature exceeds threshold.
    - `process_active`: Monitor if a specific software (like `notepad.exe`) is in focus.
    - `idle_duration`: Trigger a reaction if you haven't moved the mouse for N minutes.
    - `battery_level`: Remind you when the laptop battery is low.
    - `hover_duration`: Mouse hovers over the pet for more than N seconds.
    - `time_range`: Within a specific time period (e.g., 11 PM to 5 AM).
    - `physics_bounce_count`: Physics bounce count (requires physics engine enabled).
5.  **Add Actions**:
    - `speak`: Make it say something, with optional emotion tags.
    - `move_to`: Move it to a specific position on the screen.
    - `fade_out`: Change transparency (simulate "hiding" or "angry").
    - `delay`: Wait for a period of time.
    - `random_group`: Randomly select one action from multiple options to execute.
    - `physics_add_directional_acceleration`: Give the pet a directional physical push.

### Trigger Example (`triggers.json`):
```json
[
  {
    "id": "game_cheer",
    "enabled": true,
    "description": "Cheer when opening a game",
    "logic": "AND",
    "probability": 1.0,
    "cooldown": 300,
    "max_triggers": 999,
    "conditions": [
      {
        "type": "process_active",
        "pnames": ["game.exe"],
        "only_new": true
      }
    ],
    "actions": [
      {
        "type": "speak",
        "text": "Good luck! I'll always be here with you!",
        "emotion": "<E:smile>"
      }
    ]
  }
]
```

---

## 🔌 Step 7: Plugin Extension (Advanced)

If you know a bit of Python, you can extend the pet's functionality through plugins.

### Plugin File (`plugins/system_extension.py`):
```python
INFO = {
    "name": "System Monitor Plugin",
    "triggers": {
        "is_machine_explosion": "Detect if machine explodes (example)"
    },
    "actions": {
        "custom_action": "Execute custom action"
    }
}

def check_status():
    """Returns (bool, str, float) tuple"""
    # Write detection logic here
    return (False, "Status normal", 0.0)

def execute_action(action_type, params):
    """Execute custom action"""
    if action_type == "custom_action":
        print(f"Executing custom action, params: {params}")
```

### What Plugins Can Do:
- Register custom trigger conditions (via `INFO["triggers"]`).
- Register custom actions (via `INFO["actions"]`).
- Execute custom logic in the background (via `check_status()`).
- Call external APIs (such as weather, stock prices, etc.).

---

## 🚀 Step 8: Test & Run

1.  Ensure your resource pack folder is in the `packs/` directory.
2.  Run `run.bat` to start the program.
3.  Right-click the pet sprite -> Resource Pack Management -> Select your pack.
    - Or set `active_pack = your_pack_folder_name` in `config.cfg`.
4.  **Debug Triggers**:
    - Set `debugtrigger = true` in `config.cfg`.
    - Run `tools/sensor_mocker.py`.
    - Adjust various parameters (CPU temperature, idle time, etc.) in the simulator and observe if the pet triggers as expected.

---

## 💡 Pro Tips

- **Multiple Outfits**: Add multiple outfit configurations to the `outfits` list in `pack.json`, and you can change clothes via the right-click menu.
- **Multiple Personalities**: Place multiple personality files in the `prompts/` folder. Although the program currently reads the first one by default, you can reserve multiple for future use.
- **Tray Icon**: Place `icon.ico` in the resource pack root directory, and the tray icon will change when switching resource packs.
- **Community Support**: If you get stuck, check the [Example_Pack](file:///d:/GitHub/Resona-Desktop-Pet/packs/Example_Pack). It's the best teacher.
- **Let AI Help You Write**: If you don't know how to write code, you can describe your needs to a large language model and let it help you write plugin code or trigger configurations. Or open this project in any AI IDE and directly ask the model to read this file.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
