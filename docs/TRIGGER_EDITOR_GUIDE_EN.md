# 🎮 Trigger Editor Quick Start Guide

`trigger_editor.py` is the core logic configuration tool for ResonaDesktopPet. It allows you to bring your pet to "life" without writing a single line of code.

## 1. Basic Concepts

A trigger consists of three parts:
- **Base Info**: ID, description, cooldown, probability, max triggers, etc.
- **Conditions**: What must happen for the trigger to fire.
- **Actions**: What the pet does once triggered.

## 2. Detailed Conditions

You can combine multiple conditions. Supported types include:

### System State
| Condition | Description | Parameters |
|-----------|-------------|------------|
| `cpu_temp` | CPU temperature exceeds threshold | `gt`: greater than (°C), `lt`: less than (°C) |
| `gpu_temp` | GPU temperature exceeds threshold | `gt`: greater than (°C), `lt`: less than (°C) |
| `cpu_usage` | CPU usage exceeds threshold | `gt`: greater than (%), `lt`: less than (%) |
| `gpu_usage` | GPU usage exceeds threshold | `gt`: greater than (%), `lt`: less than (%) |
| `battery_level` | Battery level check (laptop only) | `gt`/`lt`: threshold, `charging`: true/false |

### Software Environment
| Condition | Description | Parameters |
|-----------|-------------|------------|
| `process_active` | Specific process is in focus | `pnames`: process name list, `only_new`: trigger only on new process |
| `process_background` | Process running in background | `pnames`: process name list |
| `process_uptime` | Process running time check | `pnames`: process names, `gt`/`lt`: time threshold (seconds) |
| `url_match` | Browser visits specific URL | `urls`: URL list, `browsers`: browser list (chrome/edge) |
| `title_match` | Window title keyword match | `titles`: keyword list |

### User Interaction
| Condition | Description | Parameters |
|-----------|-------------|------------|
| `hover_duration` | Mouse hover duration | `gt`: time threshold (seconds) |
| `leave_duration` | Pointer left pet area duration | `gt`: time threshold (seconds) |
| `long_press` | Long press duration | `gt`: time threshold (seconds) |
| `click_count` | Click combo count | `count`: required clicks, `time_window`: time window (seconds) |
| `idle_duration` | User idle time | `gt`: time threshold (seconds) |
| `resume_from_idle` | Trigger when returning from idle | `min_idle`: minimum idle time (seconds) |
| `clipboard_match` | Clipboard content keyword match | `keywords`: keyword list |
| `file_drop` | ~~File dropped onto pet area~~ | `Temporarily Unavailable` |

### Contextual Info
| Condition | Description | Parameters |
|-----------|-------------|------------|
| `weather_match` | Weather condition match | `weathers`: weather list (sunny/rainy/cloudy/etc.) |
| `time_range` | Specific time period | `start`: start time (HH:MM), `end`: end time (HH:MM) |
| `date_match` | Specific date | `dates`: date list (MM-DD) |
| `music_match` | Music match (NetEase Cloud Music only) | `songs`: song name list, `artists`: artist list |
| `fullscreen_active` | Full-screen mode detection | `active`: true/false |

### Physics Engine (Experimental)
| Condition | Description | Parameters |
|-----------|-------------|------------|
| `physics_acceleration_threshold` | Physics acceleration exceeds threshold | `threshold`: acceleration value |
| `physics_bounce_count` | Bounce count check | `gt`: greater than count |
| `physics_fall_distance` | Fall distance check | `gt`: distance threshold (pixels) |
| `physics_window_collision_count` | Window collision count | `gt`: greater than count |

### Logic Nesting
| Condition | Description | Parameters |
|-----------|-------------|------------|
| `AND` | All sub-conditions must be met | `conditions`: sub-condition list |
| `OR` | Any one sub-condition is enough | `conditions`: sub-condition list |
| `CUMULATIVE` | Accumulate condition triggers | `conditions`: sub-condition list, `threshold`: required count |

### Plugin Extension
- Custom conditions registered by plugins through `INFO["triggers"]`

## 3. Detailed Actions

You can execute a sequence of actions upon triggering:

### Basic Actions
| Action | Description | Parameters |
|--------|-------------|------------|
| `speak` | Play a specific line | `text`: dialogue text, `emotion`: emotion tag (e.g., `<E:angry>`) |
| `delay` | Wait for set duration | `duration`: wait time (seconds) |
| `move_to` | Move pet to position | `x`: X coordinate (0-1 or pixels), `y`: Y coordinate (0-1 or pixels), `duration`: animation time |
| `fade_out` | Change transparency | `opacity`: target opacity (0-1), `duration`: transition time |

### Random Actions
| Action | Description | Parameters |
|--------|-------------|------------|
| `random_group` | Randomly select from action groups | `groups`: list of action lists |

### Physics Engine Actions (Experimental)
| Action | Description | Parameters |
|--------|-------------|------------|
| `physics_add_directional_acceleration` | Apply directional force | `angle`: direction angle (degrees), `force`: force magnitude |
| `physics_disable_temporarily` | Temporarily disable physics | `duration`: disable time (seconds) |
| `physics_multiply_forces` | Multiply current forces | `multiplier`: multiplication factor |

### Interaction Control
| Action | Description | Parameters |
|--------|-------------|------------|
| `lock_interaction` | Lock/unlock interactions | `lock`: true/false, `duration`: lock duration (seconds, 0=permanent) |

### Plugin Actions
- Custom actions registered by plugins through `INFO["actions"]`

## 4. Complex Logic Example

```json
{
  "id": "complex_example",
  "enabled": true,
  "description": "Complex logic example",
  "logic": "OR",
  "probability": 1.0,
  "cooldown": 60,
  "max_triggers": 999,
  "conditions": [
    {
      "logic": "AND",
      "conditions": [
        {"type": "cpu_temp", "gt": 80},
        {"type": "process_active", "pnames": ["game.exe"]}
      ]
    },
    {
      "type": "battery_level",
      "lt": 20,
      "charging": false
    }
  ],
  "actions": [
    {
      "type": "speak",
      "text": "Master, please pay attention!",
      "emotion": "<E:serious>"
    },
    {
      "type": "move_to",
      "x": 0.5,
      "y": 0.8,
      "duration": 0.5
    }
  ]
}
```

## 5. Random Action Example

```json
{
  "type": "random_group",
  "groups": [
    [
      {"type": "speak", "text": "Response A", "emotion": "<E:smile>"}
    ],
    [
      {"type": "speak", "text": "Response B", "emotion": "<E:thinking>"}
    ],
    [
      {"type": "speak", "text": "Response C", "emotion": "<E:surprised>"}
    ]
  ]
}
```

## 6. Quick Start Steps

1. **Open the Editor**: Run `python tools/trigger_editor.py`.
2. **Select Pack**: Choose `Resona_Default` or your custom pack from the dropdown.
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
