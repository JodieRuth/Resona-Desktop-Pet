# ⚙️ 后端服务模块 (Backend Services)

后端模块位于 `resona_desktop_pet/backend/`，负责处理 AI 逻辑与音频处理。

## 1. LLM 模块 (`llm_backend.py`)
负责与各种大模型 API 通讯。
- **统一调用**：基于 `litellm` 库实现统一的大模型 API 调用，支持 100+ 种模型。
- **对话历史管理**：内置 `ConversationHistory` 类，自动维护最近 N 轮对话。
- **多模型适配**：
  - `query_openai_compatible`: 支持 DeepSeek, GPT-4, LocalLLM 等。
  - `query_gemini`: 针对 Google Gemini 的历史格式进行了特殊适配。
  - `query_claude`: 支持 Anthropic Claude。
- **思考过程支持**：能够提取并记录 R1/Claude 等模型的 `<think>` 标签内容。
- **自动解析**：自动将模型返回的 JSON 字符串解析为 `LLMResponse` 对象（包含表情、显示文本、语音文本）。
- **OCR 上下文（可选）**：可按配置对屏幕进行文字识别并注入提示词，增强环境感知；启用后会将屏幕内容发送到第三方 OCR 服务，可能包含敏感信息，使用者需自行承担由此带来的全部后果。

## 2. TTS 模块 (`tts_backend.py`)
负责将文本转为语音。
- **GPT-SoVITS 集成**：通过本地 HTTP 接口与推理服务器通讯。
- **情感映射**：根据 LLM 返回的情感标签（如 `<E:smile>`），从当前资源包的 `emotions.json` 中查找对应的参考音频（`ref_wav`）和标注文本（`ref_text`）。
- **动态加载**：无需重启程序，切换资源包后自动更新参考素材。

### 2.1 远程 TTS 模式 (`tts_remote_handler.py`)
支持连接到远程 SoVITS 服务器，实现分布式语音合成。
- **服务器发现**：通过 UDP 广播自动发现局域网内的 SoVITS 服务器。
- **WebSocket 通信**：使用 WebSocket 与远程服务器建立长连接，实时传输文本和接收音频数据。
- **多资源包支持**：远程服务器可同时加载多个资源包的语音模型，客户端可动态切换。
- **配置方式**：在 `config.cfg` 中设置 `mode = server` 并配置 `server_host` 和 `server_port`。

```ini
[SoVITS]
mode = server              # local=本地模式, server=远程模式
server_auto_discover = true # 是否自动发现服务器
server_host = 127.0.0.1    # 远程服务器地址
server_port = 9876         # 远程服务器 WebSocket 端口
```

## 3. STT 模块 (`stt_backend.py`)
负责语音识别。
- **SenseVoice 引擎**：使用离线 SenseVoice 模型，具备极高的识别速度与准确率。项目中的 `setup.ps1` 安装脚本下载并使用的语音识别模型 SenseVoiceSmall 是由 Alibaba Group (FunASR) 开发并开源的，遵循 FunASR Model License 1.1。 该脚本使用了由 k2-fsa / sherpa-onnx 项目提供的 ONNX 转换版本。
- **自动静音检测 (VAD)**：在检测到一段时间的静音后自动停止录音并开始识别。
- **快捷键绑定**：支持全局热键（默认 `Ctrl+Shift+I`）呼出语音对话。

## 4. SoVITS 管理器 (`sovits_manager.py`)
负责管理 SoVITS 后台进程。
- **自动启动/关闭**：程序启动时自动寻找 `GPT-SoVITS` 路径并启动 API 服务器，程序关闭时自动清理进程。
- **运行时环境**：支持使用项目内置的精简运行时环境启动。

### 4.1 SoVITS 服务器模式 (`sovits_server.py`)
可将 SoVITS 作为独立服务器运行，为多个客户端提供语音合成服务。
- **独立运行**：通过 `run_sovits_server.py` 独立启动，不依赖主程序。
- **WebSocket 接口**：提供 WebSocket 接口供远程客户端连接。
- **服务发现**：通过 UDP 广播（端口 19876）自动宣告服务，方便客户端发现。
- **多客户端支持**：支持多个客户端同时连接，每个客户端可独立切换资源包。
- **多资源包管理**：服务器可同时加载多个资源包的模型权重，支持运行时切换。

**启动方式**：
```bash
python run_sovits_server.py
```

**配置项**（`config.cfg`）：
```ini
[SoVITS]
device = cuda              # 服务器使用的计算设备 (cuda/cpu)
sovits_api_port = 9880     # SoVITS API 端口
```

## 5. MCP 管理器 (`mcp_manager.py`)
负责 Model Context Protocol 的服务管理与工具调度。
- **自动发现**：启动时自动扫描 `mcpserver/` 目录下的 `.mcp.json/py/js` 文件，加载并启动对应的 MCP Server。
- **工具注入**：将发现的所有工具（Tools）转换为 LLM 可理解的 Schema，并注入到 System Prompt 中。
- **安全沙箱**：通过 `stdio` 管道与子进程通信，隔离工具执行环境（虽然工具本身可能具有高权限，需注意 `command_proxy` 等工具的风险）。
- **内置工具**：
  - `filesystem_tools`：文件读写、搜索、编辑。
  - `command_proxy`：执行系统 Shell 命令。
  - `timer_inbox`：写入定时任务到 JSON 收件箱，由主循环轮询触发。
  - `ocr_tools`：调用 OCR 接口识别屏幕内容（作为工具调用，而非被动注入）。

## 6. Web 服务器 (`web_server/`)
基于 FastAPI 构建的本地 Web 服务。
- **API 服务**：提供 HTTP 接口，支持静态文件服务。
- **WebSocket (`server.py`)**：核心通信通道，支持客户端（如 Web UI）与后端建立长连接。
  - **状态同步**：实时推送宠物的表情、动作、语音状态。
  - **远程控制**：接收客户端的指令控制宠物行为。
- **Session 管理 (`session_manager.py`)**：支持多客户端连接管理。

## 7. 物理引擎 (`physics/`)
位于 `resona_desktop_pet/physics/`，提供实验性的物理模拟。
- **Verlet 积分**：使用 Verlet 算法模拟粒子的运动轨迹。
- **碰撞检测**：检测屏幕边缘（`ScreenBoundary`）和窗口矩形，实现反弹效果。
- **状态机集成**：物理状态（如"被拖拽"、"飞行"、"落地"）与宠物的主逻辑状态机解耦但互通。

## 8. 定时任务模块 (`timer_backend.py`)
负责定时任务的调度与管理。
- **收件箱机制**：MCP 工具将定时任务写入 JSON 收件箱，主程序轮询读取。
- **任务队列**：内部维护任务队列，支持持久化未完成任务。
- **预合成语音**：可在任务触发前预合成语音，实现零延迟提醒。
- **配置项**：通过 `config.cfg` 中的 `[Timer]` 节进行配置。

## 9. 长期记忆系统 (`memory/`)
位于 `memory/` 目录，提供超越对话历史的长期记忆能力。

### 9.1 记忆管理器 (`memory_manager.py`)
核心记忆管理模块，负责记忆的存储与检索。
- **SQLite 数据库存储**：使用 SQLite 持久化存储记忆和对话历史。
- **分资源包隔离**：支持按资源包隔离记忆（`per_pack_memory = true`），每个角色拥有独立的记忆空间。
- **对话历史记录**：自动记录所有对话，支持按时间范围查询。
- **记忆注入**：在 LLM 调用前，自动将相关记忆注入 System Prompt。

### 9.2 向量存储 (`vector_store.py`)
基于向量嵌入的语义记忆系统，支持相似度搜索。
- **ONNX 模型支持**：使用 ONNX 格式的句子嵌入模型（如 sentence-transformers）。
- **语义检索**：将记忆内容编码为向量，支持基于语义的相似度搜索。
- **可选启用**：通过 `vector_enabled = true` 启用，需要下载 ONNX 模型到指定目录。
- **模型路径配置**：
```ini
[Memory]
vector_enabled = true
vector_model_path = memory/sentence-transformers
vector_model_file = onnx/model_quint8_avx2.onnx
```

### 9.3 启动处理器 (`startup_processor.py`)
在程序启动时处理上一次会话的记忆。
- **会话总结**：使用独立配置的 LLM 分析上一次会话内容，提取重要信息。
- **记忆转换**：将临时会话转换为长期记忆存储。
- **独立配置**：支持使用与主程序不同的 LLM 配置进行记忆处理。

**记忆系统配置**（`config.cfg`）：
```ini
[Memory]
enabled = true                    # 是否启用长期记忆
per_pack_memory = true            # 是否按资源包隔离记忆
force_operation = true            # 是否强制 LLM 使用记忆工具
startup_processing = true         # 启动时是否处理上一次会话
startup_base_url =                # 记忆处理使用的 LLM 地址（留空使用主配置）
startup_api_key =                 # 记忆处理使用的 API Key
startup_model_name = deepseek-chat # 记忆处理使用的模型
conversation_retention_days = 30  # 对话历史保留天数（0=永久保留）
```

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。
