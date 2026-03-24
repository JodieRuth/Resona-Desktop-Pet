# 🎨 桌面宠物：小白保姆级资源包创作/修改指南

这份指南专为**完全没有编程经验**的小白用户设计。我们将手把手教你如何修改现有的角色，或者从零开始创造一个属于你自己的桌面伴侣。

---

## 📂 第一步：认识资源包的"家"

在本项目的文件夹里，所有的角色都住在 `packs` 文件夹中。
- `packs/Example_Pack`：这是一个完美的模板，建议你**永远不要直接删除它**，而是通过"复制 -> 修改"它来创建新角色。

### 一个完整的资源包长这样：
```text
我的资源包/
├── assets/                # 【肉体】放立绘图片和音效
│   ├── sprites/           # 立绘图片（支持 PNG/WebP）
│   │   └── 服装目录/       # 每一套衣服一个文件夹
│   │       └── sum.json   # 这一套衣服的表情索引
│   └── audio/             # 预设音效（一般给 triggers.json 用）
├── logic/                 # 【灵魂】宠物的思考逻辑
│   ├── emotions.json      # 表情与声音和立绘的对应关系
│   ├── triggers.json      # 什么时候该干什么（触发器）
│   ├── thinking.json      # 思考时使用的随机文本
│   ├── listening.json     # 录音时使用的随机文本
│   └── error_config.json  # 错误处理配置（可选）
├── models/                # 【声音核心】语音合成模型
│   └── sovits/            # 放置 GPT-SoVITS 的 .pth 和 .ckpt 文件
├── prompts/               # 【性格】给 AI 的人设剧本
│   ├── character_prompt.txt # 默认人设
│   └── other_prompt.txt     # 可选的其他性格（如"黑化"、"幼年"）
├── plugins/               # 【超能力】Python 脚本扩展功能
│   └── system_extension.py  # 示例插件
├── pack.json              # 【身份证】资源包的名字、作者、模型路径等
├── icon.ico               # 【图标】资源包的专属托盘图标（可选）
└── README.md              # 你的资源包介绍
```

---

## 🆔 第二步：修改"身份证" (`pack.json`)

这是最关键的一步，决定了程序如何读取你的资源。用记事本（推荐使用 VS Code 或 Notepad++）打开 `pack.json`。

### 基础信息 (`pack_info`):
- **`id`**: 资源包的唯一标识符（英文，无空格）。
- **`name`**: 你的角色叫什么名字？（显示在设置菜单里）。
- **`author`**: 写上你的大名。
- **`version`**: 版本号（如 "1.0.0"）。

### 角色设定 (`character`):
- **`name`**: 宠物在对话时自称的名字。
- **`username_default`**: 默认用户名（显示在对话框中）。
- **`tts_language`**: 语音语言（`ja` 为日语，`zh` 为中文，`en` 为英语，`ko` 为韩语）。
- **`outfits`**: 这里可以配置**多套服装**！
    - `id`: 服装标识符（英文）。
    - `name`: 服装显示名称。
    - `path`: 对应 `assets/sprites/` 下的文件夹路径。
    - `is_default`: 是否为默认服装（`true` 或 `false`，只能存在一个）。

### 语音模型 (`sovits_model`):
- **`vits_weights`: `.pth` 文件的路径（相对于资源包根目录）。
- **`gpt_weights`: `.ckpt` 文件的路径（相对于资源包根目录）。

### 逻辑配置 (`logic`):
- **`prompts`**: 这里可以配置**多种性格**！
    - 每一项都有一个 `id` 和对应的 `path`（指向 `prompts/` 文件夹下的文件）。
- **`emotions`**: `emotions.json` 的路径。
- **`triggers`**: `triggers.json` 的路径。
- **`thinking`**: `thinking.json` 的路径。
- **`listening`**: `listening.json` 的路径。
- **`plugins`**: 插件目录路径（可选）。

### 音频配置 (`audio`):
- **`emotion_audio_dir`**: 情感参考音频的根目录。

### 其他属性:
- **`icon.ico`**: 如果你在资源包根目录放一个 `icon.ico`，程序切换到这个包时，托盘图标也会跟着变！

---

## 🎭 第三步：配置立绘（让宠物"动"起来）

本项目的立绘不是动画文件，而是多张静态图的切换。

1.  **准备图片**：将你的立绘图片放入 `assets/sprites/你的服装名/` 文件夹。
2.  **图片要求**：
    - 图片最好是透明底的 PNG。
    - 建议分辨率为 1280×720（16:9 比例）。
    - 立绘主体应该位于图片下方，程序会自动对齐到底部中央。
    - *小贴士*：如果你的立绘大小不一，可以使用项目自带的工具 `tools/image_processor.py`，它会自动帮你把图片对齐并填充到 1280×720。
3.  **编写索引 (`sum.json`)**：在图片文件夹里创建 `sum.json`。
    - 格式：`"<E:表情名>": ["图片文件名1", "图片文件名2"]`
    - 例如：`"<E:smile>": ["happy_01", "happy_02"]`。当宠物开心时，它会从这两个文件里随机选一个显示。
    - 常用表情标签：`<E:smile>`、`<E:angry>`、`<E:sad>`、`<E:serious>`、`<E:thinking>`、`<E:surprised>`、`<E:dislike>`、`<E:smirk>`、`<E:embarrassed>`
    - 使用 `tools/sprite_organizer.py` 可以图形化整理图片并自动生成 `sum.json`。

---

## 🧠 第四步：塑造性格 (`prompts/character_prompt.txt`)

这是最神奇的一步，你在这里写下的文字将决定宠物的"灵魂"。

- **背景设定**：它是谁？来自哪里？
- **性格特征**：是温柔的邻家妹妹，还是毒舌的傲娇大小姐？
- **说话风格**：用什么语气说话？有什么口头禅？
- **禁忌事项**：
    - 不要说长篇大论（建议限制在 4 句以内）。
    - 不要承认自己是 AI。
    - 不要跳出角色设定。
- **格式要求**：**千万不要改动文件底部的 JSON 格式说明**，否则宠物的表情和语音会失效！

### 提示词示例结构：
```
你是[角色名]，一个[性格特征]的[身份]。
你说话[说话风格]，喜欢[爱好]。
你对用户的态度是[态度]。

[其他设定...]

--- 以下部分不要修改 ---
你需要以JSON格式回复...
```

---

## 🗣️ 第五步：声音与情感 (`logic/emotions.json`)

本项目使用 SoVITS 技术。要让宠物说话有感情，你需要给每个表情配一个"参考音频"。

1.  **放置模型**：将训练好的 `.pth` 和 `.ckpt` 文件放入资源包的 `models/sovits/` 目录下，并在 `pack.json` 中配置好路径（见第二步）。
2.  **准备参考音频**：录制或截取每个情感对应的参考音频（建议 3-10 秒），放入 `assets/audio/` 目录。
3.  **编写 `emotions.json`**：
```json
{
  "<E:smile>": {
    "ref_wav": "audio/smile_ref.wav",
    "ref_text": "参考音频的文本内容",
    "ref_lang": "ja"
  },
  "<E:angry>": {
    "ref_wav": "audio/angry_ref.wav",
    "ref_text": "参考音频的文本内容",
    "ref_lang": "ja"
  }
}
```
- **`ref_wav`**: 参考音频路径（相对于资源包根目录）。
- **`ref_text`**: 这段音频里说了什么（需要准确）。
- **`ref_lang`**: 这段音频是什么语言（`zh` 为中文，`ja` 为日文，`en` 为英文，`ko` 为韩文）。

*如果没有模型？请自行训练一个对应的 GPT-SoVITS 模型。教程现在网上有很多。*

---

## ⚡ 第六步：设置触发器（让宠物变聪明）

这是让宠物感觉"活着"的关键。比如：你打开了游戏，它为你加油；你很久没理它，它开始抱怨。

### 小白神器：`tools/trigger_editor.py`
1.  双击运行 `tools/trigger_editor.py`。
2.  在左上角下拉框选择你的资源包。
3.  点击"新增触发器"创建新规则。
4.  **添加条件**：
    - `cpu_temp` / `gpu_temp`：CPU/GPU 温度超过阈值。
    - `process_active`：监控某个软件（如 `notepad.exe`）是否在前台运行。
    - `idle_duration`：如果你 N 分钟没动鼠标，触发特定反应。
    - `battery_level`：电脑电量低时提醒你（笔记本）。
    - `hover_duration`：鼠标悬停在宠物身上超过 N 秒。
    - `time_range`：在特定时间段内（如晚上 11 点到早上 5 点）。
    - `physics_bounce_count`：物理反弹次数（需要开启物理引擎）。
5.  **添加动作**：
    - `speak`：让它说一段话，可以指定情感标签。
    - `move_to`：让它在屏幕上移动到指定位置。
    - `fade_out`：改变透明度（模拟"隐身"或"生气"）。
    - `delay`：等待一段时间。
    - `random_group`：从多个动作中随机选择一个执行。
    - `physics_add_directional_acceleration`：给宠物一个物理方向的推力。

### 触发器示例 (`triggers.json`)：
```json
[
  {
    "id": "game_cheer",
    "enabled": true,
    "description": "打开游戏时加油",
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
        "text": "要加油哦！我会一直陪着你的！",
        "emotion": "<E:smile>"
      }
    ]
  }
]
```

---

## 🔌 第七步：插件扩展（进阶）

如果你懂一点点 Python，可以通过插件扩展宠物的功能。

### 插件文件 (`plugins/system_extension.py`)：
```python
INFO = {
    "name": "系统监控插件",
    "triggers": {
        "is_machine_explosion": "检测机器是否爆炸（示例）"
    },
    "actions": {
        "custom_action": "执行自定义动作"
    }
}

def check_status():
    """返回 (bool, str, float) 元组"""
    # 在这里编写检测逻辑
    return (False, "状态正常", 0.0)

def execute_action(action_type, params):
    """执行自定义动作"""
    if action_type == "custom_action":
        print(f"执行自定义动作，参数：{params}")
```

### 插件可以做什么：
- 注册自定义触发条件（通过 `INFO["triggers"]`）。
- 注册自定义动作（通过 `INFO["actions"]`）。
- 在后台执行自定义逻辑（通过 `check_status()`）。
- 调用外部 API（如查天气、股价等）。

---

## 🚀 第八步：测试与运行

1.  确保你的资源包文件夹放在 `packs/` 目录下。
2.  运行 `run.bat` 启动程序。
3.  右键程序立绘 -> 资源包管理 -> 选择你的资源包。
    - 或者在 `config.cfg` 中设置 `active_pack = 你的资源包文件夹名`。
4.  **调试触发器**：
    - 在 `config.cfg` 中设置 `debugtrigger = true`。
    - 运行 `tools/sensor_mocker.py`。
    - 在模拟器中调整各种参数（CPU 温度、闲置时间等），观察宠物是否按预期触发。

---

## 💡 进阶小技巧

- **多套服装**：在 `pack.json` 的 `outfits` 列表里添加多个服装配置，你就可以在右键菜单里给宠物换装了。
- **多性格切换**：在 `prompts/` 文件夹中放置多个性格文件，虽然目前程序默认读取第一个，但你可以预留多个供以后使用。
- **托盘图标**：在资源包根目录放置 `icon.ico`，切换资源包时托盘图标会跟着变化。
- **求助社区**：遇到问题不要怕，参考 [Example_Pack](file:///d:/GitHub/Resona-Desktop-Pet/packs/Example_Pack) 里的写法，那是最好的老师。
- **让 AI 帮你写**：如果你不会写代码，可以把需求描述给大语言模型，让它帮你写插件代码或触发器配置。或者把本项目在任何一个AI IDE中打开之后直接要求模型读取本文件。

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。