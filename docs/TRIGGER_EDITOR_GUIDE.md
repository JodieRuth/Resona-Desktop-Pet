# 🎮 Trigger Editor 快速上手指南

`trigger_editor.py` 是 ResonaDesktopPet 的核心逻辑配置工具。它让您不需要编写任何代码，就能让宠物拥有"生命力"。

## 1. 基础概念
一个触发器由三部分组成：
- **基础信息**：ID、描述、冷却时间、触发概率等。
- **判定条件 (Conditions)**：满足什么条件时触发。
- **响应动作 (Actions)**：触发后宠物做什么。

## 2. 判定条件 (Conditions) 详解

您可以组合多个条件，支持嵌套逻辑 (AND/OR/CUMULATIVE)。

### 2.1 系统状态
- **cpu_temp**: CPU 温度超过设定值（摄氏度）
- **gpu_temp**: GPU 温度超过设定值（摄氏度）
- **cpu_usage**: CPU 占用率超过设定值（百分比）
- **gpu_usage**: GPU 占用率超过设定值（百分比）
- **battery_level**: 电池电量检测（笔记本），支持充电状态检测
  - `gt`: 大于值
  - `lt`: 小于值
  - `charging`: 是否正在充电（true/false）

### 2.2 软件环境
- **process_active**: 特定软件在前台时触发
  - `pnames`: 进程名列表（如 `["notepad.exe", "chrome.exe"]`）
- **process_background**: 特定进程在后台运行
  - `pnames`: 进程名列表
  - `only_new`: 仅检测新启动的进程
- **process_uptime**: 进程已存活的时间
  - `pname`: 进程名
  - `gt`: 大于秒数
  - `lt`: 小于秒数（可选）
  - `log`: 触发时打印日志（可选）
- **url_match**: 浏览器访问特定网页时触发（仅支持 Chrome/Edge）
  - `keywords`: URL 关键词列表
- **title_match**: 窗口标题匹配关键词
  - `keywords`: 标题关键词列表

### 2.3 用户交互
- **hover_duration**: 鼠标悬停在宠物身上的时长（秒）
- **leave_duration**: 鼠标离开宠物区域的时长（秒）
- **long_press**: 长按立绘的时长（秒）
- **click_count**: 快速点击次数
  - `count`: 点击次数
  - `duration`: 时间窗口（秒）
- **idle_duration**: 用户闲置时长（秒）
- **idle_recovery**: 闲置结束恢复时触发
  - `sec`: 闲置时长阈值

### 2.4 物理引擎相关（实验性）
- **physics_acceleration_threshold**: 物理加速度超过阈值
  - `gt`: 加速度值
- **physics_bounce_count**: 物理反弹次数
  - `count`: 反弹次数
- **physics_fall_distance**: 物理下落距离超过阈值
  - `gt`: 距离值（像素）
- **physics_window_collision_count**: 与其他窗口碰撞次数
  - `count`: 碰撞次数

### 2.5 环境信息
- **fullscreen**: 进入全屏模式时触发
- **weather_match**: 天气状态匹配
  - `keywords`: 天气关键词列表（如 `["rain", "snow"]`）
- **time_range**: 在特定时间段内
  - `range`: 时间范围（如 `"23:00-05:00"`）
- **date_match**: 特定日期
  - `date`: 日期（格式 `"MM-DD"`，如 `"12-25"`）
- **music_match**: 网易云音乐正在播放的歌曲匹配
  - `keywords`: 歌曲/歌手关键词列表
  - `only_on_change`: 仅切歌时触发一次（默认 true）

### 2.6 剪贴板与文件
- **clip_match**: 剪贴板内容匹配关键词
  - `keywords`: 关键词列表
- **file_drop**: ~~文件拖入检测~~（暂时不可用）
  - `exts`: 允许的文件后缀列表
  - `name_keywords`: 文件名包含的关键词

### 2.7 插件扩展
- **plugin_check**: 插件状态检查
  - `plugin_id`: 插件 ID
  - `expect_bool`: 期望的布尔返回值
  - `match_text`: 文本匹配（可选）
  - `gt_value`: 数值大于（可选）
  - `lt_value`: 数值小于（可选）

### 2.8 逻辑组合
- **AND**: 所有子条件必须全部满足
- **OR**: 满足其中一个即可
- **CUMULATIVE**: 累计满足（曾达成过的条件会被记录）

## 3. 响应动作 (Actions) 详解

触发后，按顺序执行以下动作：

### 3.1 基础动作
- **speak**: 播放一段特定的台词
  - `text`: 显示的文本内容
  - `emotion`: 情感标签（如 `<E:smile>`）
  - `voice_file`: 预设音频文件路径（可选，相对于资源包 audio 目录）

- **delay**: 等待指定时间
  - `sec`: 等待秒数（0-300）

- **move_to**: 将宠物移动到屏幕特定位置
  - `pos`: 位置（`top_left` 或 `bottom_right`）

- **fade_out**: 改变透明度
  - `opacity`: 目标透明度（0.0-1.0）
  - `sec`: 持续时间（秒），之后自动恢复
  - `hover_recovery`: 悬停恢复时间（秒，可选）

- **lock_interaction**: 锁定交互（禁止点击）
  - `sec`: 锁定时长（秒，0-300）

- **exit_app**: 关闭程序

### 3.2 物理引擎动作（实验性）
- **physics_add_directional_acceleration**: 添加定向加速度
  - `direction`: 方向（1-8，对应 8 个方向）
  - `magnitude`: 加速度大小

- **physics_disable_temporarily**: 临时禁用物理引擎
  - `sec`: 禁用时长（秒）

- **physics_multiply_forces**: 物理力倍率
  - `multiplier`: 倍率值
  - `sec`: 持续时长（秒）

### 3.3 随机与插件
- **random_group**: 从多个预设动作中随机选一个执行
  - `branches`: 分支列表，每个分支包含 `weight`（权重）和 `actions`（动作列表）

- **插件动作**: 通过插件扩展的自定义动作类型
  - 动作类型名由插件定义
  - `params`: 插件参数列表

## 4. 快速上手步骤

1. **打开编辑器**：运行 `python tools/trigger_editor.py`
2. **选择资源包**：在下拉框选择您的资源包
3. **创建新规则**：
   - 点击"新增触发器"
   - ID 设为 `high_cpu_warning`
   - 规则描述写"CPU 温度过高警告"
4. **设置条件**：
   - 条件类型选 `cpu_temp`，点击"添加条件"
   - 在右侧面板，将 `gt` (大于) 设为 `85`
5. **设置动作**：
   - 动作类型选 `speak`，点击"插入动作"
   - 在右侧面板设置：
     - `text`: "主人，电脑好烫呀，要不要休息一下？"
     - `emotion`: `<E:serious>`
6. **保存**：点击"保存同步"
7. **测试**：运行 `python tools/sensor_mocker.py`，将 CPU 温度滑块拉到 90，观察宠物是否触发

## 5. 高级技巧

### 5.1 嵌套逻辑示例
```json
{
  "logic": "OR",
  "conditions": [
    {
      "logic": "AND",
      "conditions": [
        {"type": "cpu_temp", "gt": 80},
        {"type": "process_active", "pnames": ["game.exe"]}
      ]
    },
    {"type": "battery_level", "lt": 20, "charging": false}
  ]
}
```
这个例子表示：当（CPU 温度高且正在玩游戏）或（电池电量低且未充电）时触发。

### 5.2 随机动作示例
```json
{
  "type": "random_group",
  "branches": [
    {
      "weight": 1,
      "actions": [{"type": "speak", "text": "你好！", "emotion": "<E:smile>"}]
    },
    {
      "weight": 2,
      "actions": [{"type": "speak", "text": "嗨~", "emotion": "<E:happy>"}]
    }
  ]
}
```
这个例子表示：以 1:2 的概率随机选择两个分支之一执行。

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。
