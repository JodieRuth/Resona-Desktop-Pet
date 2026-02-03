# 🎨 Desktop Pet: Beginner's Resource Pack Creation & Modification Guide

This guide is designed for **absolute beginners** with no programming experience. We will walk you through how to modify existing characters or create your very own desktop companion from scratch.

---

## 📂 Step 1: Meet the Resource Pack "Home"

In the project folder, all characters live in the `packs` directory.
- `packs/Example_Pack`: This is a perfect template. We recommend **never deleting it directly**; instead, "Copy -> Paste" it to create a new character.

### A complete resource pack looks like this:
```text
My_Resource_Pack/
├── assets/                # 【Body】Stores sprites and sound effects
├── sprites/           # Sprite images (Supports PNG/WebP)
│   │       └── Outfit_Folder/ # One folder per outfit
│   │           └── sum.json   # Index for expressions in this outfit
│   └── audio/             # Preset sound effects (usually for triggers.json)
├── logic/                 # 【Soul】The pet's thinking logic
│   ├── emotions.json      # Mapping between emotions, voice, and sprites
│   ├── triggers.json      # When to do what (Triggers)
│   ├── thinking.json      # Random text used while thinking
│   └── listening.json     # Random text used while recording
├── models/                # 【Voice Core】Voice synthesis models
│   └── sovits/            # Place GPT-SoVITS .pth and .ckpt files here
├── prompts/               # 【Personality】AI personality scripts
│   ├── character_prompt.txt # Default personality
│   └── other_prompt.txt     # Optional personalities (e.g., "Dark", "Young")
├── plugins/               # 【Superpowers】Python scripts for extended features
├── pack.json              # 【ID Card】Name, author, model paths, etc.
├── icon.ico               # 【Icon】Exclusive tray icon (optional)
└── README.md              # Introduction to your resource pack
```

---

## 🆔 Step 2: Modify the "ID Card" (`pack.json`)

This is the most critical step, as it determines how the program reads your resources. Open `pack.json` with a text editor (VS Code or Notepad++ recommended).

- **Basic Info (`pack_info`)**:
    - **`name`**: What is your character's name? (Shows up in settings).
    - **`author`**: Write your name here.
- **Character Settings (`character`)**:
    - **`name`**: The name the pet calls itself in conversation.
    - **`tts_language`**: Voice language (`ja` for Japanese, `zh` for Chinese).
    - **`outfits`**: You can configure **multiple outfits** here!
        - `id`: Outfit name (shows in the change outfit menu).
        - `path`: Path to the folder under `assets/sprites/`.
    - **`sovits_model`**: Paths to voice models.
        - `vits_weights`: Path to the `.pth` file (relative to the pack root).
        - `gpt_weights`: Path to the `.ckpt` file (relative to the pack root).
- **Logic Config (`logic`)**:
    - **`prompts`**: You can configure **multiple personalities**!
        - Each item has an `id` and a `path` (pointing to files in the `prompts/` folder).
- **Other Attributes**:
    - **`icon.ico`**: If you place an `icon.ico` in the root of the resource pack, the tray icon will change when you switch to this pack!

---

## 🎭 Step 3: Configure Sprites (Make it "Move")

The sprites in this project are not animation files but a switch between multiple static images.

1.  **Prepare Images**: Put your sprite images into the `assets/sprites/Your_Outfit_Name/` folder.
2.  **Image Requirements**: Images should ideally be transparent PNGs.
    - *Tip*: If your sprites are different sizes, use the built-in tool `tools/image_processor.py`. It will automatically align and pad images to 1280*720.
3.  **Write the Index (`sum.json`)**: Inside the image folder, you'll see a `sum.json`.
    - Format: `"<E:expression_name>": ["image_file1", "image_file2"]`
    - Example: `"<E:smile>": ["happy_01", "happy_02"]`. When the pet is happy, it will randomly pick one of these files to display.
    - If you use `tools/image_processor.py`, the filenames will be automatically updated in `sum.json`.

---

## 🧠 Step 4: Shape the Personality (`prompts/character_prompt.txt`)

This is the most magical step. The text you write here determines the pet's "soul."

- **Background**: Who is it? Where is it from?
- **Traits**: Is it a gentle girl next door or a sharp-tongued tsundere?
- **Constraints**: Don't be too wordy (suggested limit: 4 sentences). Don't admit to being an AI.
- **Format Requirement**: **Never change the JSON format instructions at the bottom of the file**, or the pet's expressions and voice will break!

---

## 🗣️ Step 5: Voice & Emotion (`logic/emotions.json`)

This project uses SoVITS technology. To make the pet speak with emotion, you need to provide a "reference audio" for each expression.

1.  **Place Models**: Put your trained `.pth` and `.ckpt` files in `models/sovits/` and configure the paths in `pack.json` (see Step 2).
2.  **Set Reference Audio**: In `emotions.json`, you will see tags like `<E:smile>`.
3.  **`ref_wav`**: Path to the reference audio (relative to `audio/emotion_audio_dir` or the pack root, depending on config).
4.  **`ref_text`**: What is being said in that audio.
5.  **`ref_lang`**: The language of the audio (`zh` for Chinese, `ja` for Japanese).

*Don't have a model? You'll need to train a SoVITS model yourself. There are many tutorials available online.*

---

## ⚡ Step 6: Set Triggers (Make it Smart)

This is key to making the pet feel "alive." For example: it cheers for you when you open a game, or complains if you haven't interacted with it for a long time.

**Beginner's Tool: `tools/trigger_editor.py`**
1.  Double-click to run `tools/trigger_editor.py`.
2.  Click "Open File" and select your resource pack.
3.  **Add Conditions**:
    - `process_active`: Monitor if a specific software (like `notepad.exe`) is running.
    - `idle_time`: Trigger a reaction if you haven't moved the mouse for 5 minutes.
    - `battery_low`: Remind you when the battery is low.
4.  **Add Actions**:
    - `speak`: Make it say something.
    - `move_to`: Make it jump around the screen.

---

## 🚀 Step 7: Test & Run

1.  Ensure your resource pack folder is in the `packs/` directory.
2.  Run `run.bat` to start.
3.  Right-click the pet sprite -> Resource Pack Management -> Select your pack. Or set `pack = your_pack_name` in `config.cfg`.
4.  **Debugging**: If triggers aren't working, set `debugtrigger = true` in `config.cfg` and run `tools/sensor_mocker.py` to manually simulate conditions.

---

## 💡 Pro Tips

- **Multiple Outfits**: Add multiple paths to the `outfits` list in `pack.json` to change clothes via the right-click menu.
- **Plugins**: If you know a bit of Python, you can write scripts in the `plugins` folder for features like weather updates or stock prices. Even if you don't, you can ask an AI to write it for you!
- **Community Support**: If you get stuck, check the [Example_Pack](file:///d:/GitHub/Resona-Desktop-Pet/packs/Example_Pack). It's the best teacher.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.