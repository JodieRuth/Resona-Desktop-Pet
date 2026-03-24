# 🛠️ 技术架构 (Technical Architecture) 

本项目采用模块化设计，主要分为 UI 层、逻辑控制层与后端服务层。

## 1. 核心技术栈
- **UI 框架**：PySide6 (Python + Qt)
- **大语言模型 (LLM)**：OpenAI API 兼容接口 / Gemini API / Claude API（通过 litellm 库统一调用）
- **语音合成 (TTS)**：GPT-SoVITS (本地推理服务器)
- **语音识别 (STT)**：SenseVoice (基于 sherpa-onnx 的本地离线引擎)
- **图像处理**：Pillow (PIL)
- **Web 服务**：FastAPI + WebSocket
- **物理引擎**：自定义 Verlet 积分物理引擎（实验性）

## 2. 目录结构说明
```text
D:\GitHub\Resona-Desktop-Pet\
├── main.py                     # 程序入口
├── config.cfg                  # 主配置文件
├── resona_desktop_pet/         # 核心源代码
│   ├── backend/                # 后端服务模块 (LLM/TTS/STT/MCP)
│   │   ├── llm_backend.py      # LLM 调用与对话历史管理
│   │   ├── tts_backend.py      # 语音合成接口
│   │   ├── stt_backend.py      # 语音识别接口
│   │   ├── sovits_manager.py   # SoVITS 进程管理
│   │   └── mcp_manager.py      # MCP 工具管理
│   ├── config/                 # 配置与资源包管理
│   │   ├── config_manager.py   # 配置管理器
│   │   └── pack_manager.py     # 资源包管理器（含插件加载）
│   ├── ui/                     # 用户界面组件
│   │   ├── luna/               # 主 UI 模块
│   │   │   ├── main_window.py  # 主窗口
│   │   │   ├── character_view.py # 立绘显示
│   │   │   └── io_overlay.py   # 对话框组件
│   │   ├── tray_icon.py        # 托盘图标
│   │   ├── settings_dialog.py  # 设置对话框
│   │   └── debug_panel.py      # 调试面板
│   ├── physics/                # 物理引擎（实验性）
│   │   ├── engine.py           # 物理计算核心
│   │   ├── bridge.py           # 物理引擎与 UI 桥接
│   │   └── env_scanner.py      # 环境扫描（窗口检测）
│   ├── web_server/             # Web 服务与远程控制
│   │   ├── server.py           # FastAPI 服务器
│   │   └── session_manager.py  # WebSocket 会话管理
│   ├── utils/                  # 工具函数
│   │   └── audio_utils.py      # 音频处理工具
│   ├── behavior_monitor.py     # 系统监控与触发逻辑核心
│   └── cleanup_manager.py      # 进程清理管理器
├── packs/                      # 资源包存储目录
├── tools/                      # 开发与调试辅助工具
├── mcpserver/                  # MCP 工具脚本目录
└── docs/                       # 项目文档
```

## 3. 工作流程
1. **启动阶段**：
   - 加载 `config.cfg` 及选定的 `pack.json`。
   - 初始化 UI (MainWindow) 及后端服务 (LLM/TTS/STT/MCP)。
   - 启动 `BehaviorMonitor` 监听系统事件与用户交互。
   - 如启用，启动 Web 服务器和物理引擎。
2. **交互阶段 (主动)**：
   - 用户点击立绘或使用快捷键启动 STT。
   - STT 将语音转为文本发送给 LLM。
   - LLM 根据提示词 (Prompt) 生成包含情感标签的 JSON 响应。
   - TTS 后端根据情感标签合成语音，UI 显示文本并切换立绘情感。
3. **交互阶段 (被动/触发)**：
   - `BehaviorMonitor` 轮询传感器数据（CPU/GPU 等）或监听系统钩子（窗口切换）。
   - 匹配资源包中 `triggers.json` 定义的条件。
   - 按照定义的 `actions` 序列执行反馈（说话、移动、渐变等）。
4. **Web 远程控制**（可选）：
   - 通过 WebSocket 连接，支持远程设备控制宠物。
   - 提供 HTTP API 获取状态和发送指令。

## 4. 后端服务解耦
- **LLMBackend**：封装了不同供应商的 API 调用，统一输出为结构化的 `LLMResponse` 对象。支持思考过程提取、OCR 上下文注入、IP 地理位置上下文。
- **TTSBackend**：通过 HTTP API 与 GPT-SoVITS 交互，动态从当前资源包读取参考音频。
- **STTBackend**：运行在独立的线程中，通过 `pyaudio` 采集音频并使用 `sherpa-onnx` 本地识别。支持 VAD 自动静音检测。
- **MCPManager**：管理 Model Context Protocol 工具，自动扫描 `mcpserver/` 目录加载工具脚本，将工具描述注入 LLM 的 System Prompt。
- **SoVITSManager**：管理 SoVITS 推理服务器的启动和关闭，自动查找并启动 `api_v2.py`。

## 5. 物理引擎（实验性）
- **Verlet 积分**：使用 Verlet 算法模拟粒子运动轨迹。
- **碰撞检测**：检测屏幕边界和窗口矩形，实现反弹效果。
- **状态追踪**：记录反弹次数、窗口碰撞次数、下落距离等，可作为触发器条件。
- **配置灵活**：通过 `config.cfg` 的 `[Physics]` 节配置重力、摩擦、弹性等参数。

## 6. 资源包与插件系统
- **PackManager**：管理资源包加载，支持多角色切换。
- **插件加载**：支持从资源包 `plugins/` 目录动态加载 Python 脚本，扩展触发器和动作。
- **多服装支持**：一个角色可配置多套服装，运行时切换。

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。
