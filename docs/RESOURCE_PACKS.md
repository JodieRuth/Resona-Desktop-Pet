# 📦 资源包系统 (Resource Pack System)

资源包是 ResonaDesktopPet 的核心，它决定了宠物的形象、声音、性格与行为逻辑。

## 1. 目录结构
一个标准的资源包目录（如 `packs/Example_Pack/`）结构如下：
```text
Example_Pack/
├── pack.json               # 资源包核心配置文件
├── README.md               # 资源包说明
├── icon.ico                # 托盘图标（可选）
├── assets/
│   ├── sprites/            # 立绘素材目录
│   │   └── example_outfit/ # 特定服装目录
│   │       ├── sum.json    # 表情索引文件
│   │       └── *.png       # 图片素材
│   └── audio/              # 音频素材目录
├── logic/
│   ├── emotions.json       # TTS 情感参考配置
│   ├── triggers.json       # 交互触发逻辑
│   ├── thinking.json       # 思考中显示的随机文本
│   ├── listening.json      # 录音中显示的随机文本
│   └── error_config.json   # 错误处理配置（可选）
├── models/
│   └── sovits/             # GPT-SoVITS 模型权重 (.pth / .ckpt)
├── prompts/
│   ├── character_prompt.txt # LLM 人格提示词
│   └── other_prompt.txt    # 其他性格提示词（可选）
└── plugins/
    └── system_extension.py # 插件扩展（可选）
```

## 2. 核心配置文件 (`pack.json`)
这是资源包的入口，定义了：
- **pack_info**: 包含 `id`（唯一标识符）、`name`（显示名称）、`version`（版本）、`author`（作者）。
- **character**: 包含角色名、`username_default`（默认用户名）、服装配置、`tts_language`（TTS 语言）、以及 SoVITS 模型路径。
- **logic**: 映射各种逻辑 JSON 文件和提示词文件的路径。
- **audio**: 定义事件、情感参考音频的根目录。
- **plugins**: 插件目录路径（可选）。

## 3. 表情索引 (`sum.json`)
位于每个服装目录下，格式如下：
```json
{
    "<E:smile>": ["outfit_smile_01", "outfit_smile_02"],
    "<E:angry>": ["outfit_angry_01"]
}
```
它将情感标签映射到对应的文件名（不含扩展名）。程序会从中随机选择一张图片显示。

## 4. 插件系统 (`plugins/`)
资源包可以包含 Python 插件来扩展功能：
- **自定义触发条件**：通过 `INFO["triggers"]` 注册新的触发条件。
- **自定义动作**：通过 `INFO["actions"]` 注册新的动作类型。
- **后台逻辑**：通过 `check_status()` 函数执行自定义检测逻辑。
- **示例文件**：`system_extension.py`

## 5. 如何自定义资源包
1. **参考示例**：最快的方法是复制 `packs/Example_Pack` 并重命名文件夹。
2. **修改 pack.json**：更改 `id` 为唯一值，并更新角色名称。
3. **准备立绘**：
   - 使用 `tools/image_processor.py` 处理你的图片。
   - 使用 `tools/sprite_organizer.py` 整理并生成 `sum.json`。
4. **配置声音**：
   - 将训练好的 SoVITS 模型放入 `models/sovits/`。
   - 在 `logic/emotions.json` 中配置情感对应的参考音频。
5. **编写逻辑**：
   - 在 `prompts/character_prompt.txt` 中定义角色的语气和背景。
   - 使用 `tools/trigger_editor.py` 制作有趣的交互触发器。
6. **（可选）编写插件**：
   - 在 `plugins/` 目录下创建 Python 文件扩展功能。

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。
