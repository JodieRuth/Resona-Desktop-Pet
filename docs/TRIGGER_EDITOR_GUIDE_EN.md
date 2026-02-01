# 🎮 Trigger Editor Quick Start Guide

`trigger_editor.py` is the core logic configuration tool for ResonaDesktopPet. it allows you to bring your pet to "life" without writing a single line of code.

## 1. Basic Concepts
A trigger consists of three parts:
- **Base Info**: ID, description, cooldown, probability, etc.
- **Conditions**: What must happen for the trigger to fire.
- **Actions**: What the pet does once triggered.

## 2. Detailed Conditions
You can combine multiple conditions. Supported types include:
- **System State**:
  - `cpu_temp` / `gpu_temp`: Checks if temperature exceeds a threshold.
  - `cpu_usage` / `gpu_usage`: Checks if usage is too high.
  - `battery_level`: Checks battery level (laptop only, supports charging state detection).
- **Software Environment**:
  - `process_active`: Fires when a specific app (e.g., `League of Legends.exe`) is in focus.
  - `process_background`: Detects if specific process is running in background.
  - `process_uptime`: Checks how long a process has been running.
  - `url_match`: Fires when a browser visits a specific URL (e.g., `github.com`).
  - `title_match`: Matches window title keywords.
- **User Interaction**:
  - `hover_duration`: How long the mouse hovers over the pet.
  - `click_count`: Detects rapid click combos.
  - `long_press`: Long press detection.
  - `file_drop`: ~~Detects files dropped onto the pet area (supports extension and filename keyword matching)~~ `Temporarily Unavailable`
- **Contextual Info**:
  - `weather_match`: Matches current weather conditions.
  - `time_range`: Fires during specific time periods (e.g., `23:00-05:00`).
  - `music_match`: Matches currently playing music in NetEase Cloud Music.
- **Logic Nesting**:
  - `AND`: All sub-conditions must be met.
  - `OR`: Any one sub-condition is enough.

## 3. Detailed Actions
You can execute a sequence of actions upon triggering:
1. `speak`: Play a specific line. You can specify emotion tags (e.g., `<E:angry>`).
2. `delay`: Wait for a set duration before the next action.
3. `move_to`: Move the pet to a specific screen position.
4. `fade_out`: Decrease transparency (e.g., to simulate "hiding").
5. `random_group`: Randomly select one group of actions from several presets.

## 4. Quick Start Steps
1. **Open the Editor**: Run `python tools/trigger_editor.py`.
2. **Select Pack**: Choose `Resona_Default` or your custom pack.
3. **Create a Rule**:
   - Click "Add Trigger".
   - Set ID to `high_cpu_warning`.
   - Set Description to "High CPU warning".
4. **Set Conditions**:
   - Select `cpu_temp` and click "Add Condition".
   - In the property panel on the right, set `gt` (greater than) to `85`.
5. **Set Actions**:
   - Select `speak` and click "Insert Action".
   - In the property panel, set:
     - `text`: "Master, the computer is so hot, should we take a break?"
     - `emotion`: `<E:serious>`
6. **Save**: Click "Save & Sync".
7. **Test**: Run `python tools/sensor_mocker.py`, drag the CPU temp slider to 90, and watch your pet react.

---
Parts of this document were generated with the assistance of large language models, and translations were also completed by large language models. Any deviations do not represent the author's true intent.
