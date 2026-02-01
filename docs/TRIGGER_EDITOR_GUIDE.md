# 🎮 Trigger Editor 快速上手指南

`trigger_editor.py` 是 ResonaDesktopPet 的核心逻辑配置工具。它让您不需要编写任何代码，就能让宠物拥有“生命力”。

## 1. 基础概念
一个触发器由三部分组成：
- **基础信息**：ID、描述、冷却时间、触发概率等。
- **判定条件 (Conditions)**：满足什么条件时触发。
- **响应动作 (Actions)**：触发后宠物做什么。

## 2. 判定条件 (Conditions) 详解
您可以组合多个条件。支持的条件包括：
- **系统状态**：
  - `cpu_temp` / `gpu_temp`: 检测温度是否超过设定值。
  - `cpu_usage` / `gpu_usage`: 检测占用率是否过高。
  - `battery_level`: 检测电池电量（需笔记本，支持充电状态检测）。
- **软件环境**：
  - `process_active`: 当特定软件（如 `League of Legends.exe`）在前台时触发。
  - `process_background`: 检测特定进程在后台运行。
  - `process_uptime`: 检测进程已存活的时间。
  - `url_match`: 当浏览器访问特定网页（如 `github.com`）时触发。
  - `title_match`: 窗口标题匹配关键词。
- **用户交互**：
  - `hover_duration`: 鼠标放在宠物身上多久。
  - `click_count`: 快速点击几次。
  - `long_press`: 长按立绘。
  - `file_drop`: 检测拖入到立绘区域的文件（支持按后缀名和文件名关键词匹配）。
- **环境信息**：
  - `weather_match`: 匹配当前天气。
  - `time_range`: 在特定时间段内（如 `23:00-05:00`）。
  - `music_match`: 网易云音乐正在播放的歌曲匹配。
- **逻辑嵌套**：
  - `AND`: 所有子条件必须全部满足。
  - `OR`: 满足其中一个即可。

## 3. 响应动作 (Actions) 详解
触发后，您可以按顺序执行一系列动作：
1. `speak`: 播放一段特定的台词。您可以指定情感标签（如 `<E:angry>`）。
2. `delay`: 等待几秒再执行下一个动作。
3. `move_to`: 将宠物移动到屏幕的特定位置。
4. `fade_out`: 降低透明度（模拟宠物“隐身”或“生气”）。
5. `random_group`: 从几个预设的动作组中随机选一个执行。

## 4. 快速上手步骤
1. **打开编辑器**：运行 `python tools/trigger_editor.py`。
2. **选择资源包**：在下拉框选择 `Resona_Default` 或您的自定义包。
3. **创建新规则**：
   - 点击“新增触发器”。
   - ID 设为 `high_cpu_warning`。
   - 规则描述写“CPU 温度过高警告”。
4. **设置条件**：
   - 条件类型选 `cpu_temp`，点击“添加条件”。
   - 在右侧面板，将 `gt` (大于) 设为 `85`。
5. **设置动作**：
   - 动作类型选 `speak`，点击“插入动作”。
   - 在右侧面板设置：
     - `text`: "主人，电脑好烫呀，要不要休息一下？"
     - `emotion`: `<E:serious>`
6. **保存**：点击“保存同步”。
7. **测试**：运行 `python tools/sensor_mocker.py`，将 CPU 温度滑块拉到 90，观察宠物是否触发。

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。
