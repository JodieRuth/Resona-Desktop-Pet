# ⚙️ 后端服务模块 (Backend Services)

后端模块位于 `resona_desktop_pet/backend/`，负责处理 AI 逻辑与音频处理。

## 1. LLM 模块 (`llm_backend.py`)
负责与各种大模型 API 通讯。
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

## 3. STT 模块 (`stt_backend.py`)
负责语音识别。
- **SenseVoice 引擎**：使用离线 SenseVoice 模型，具备极高的识别速度与准确率。项目中的 `setup.ps1` 安装脚本下载并使用的语音识别模型 SenseVoiceSmall 是由 Alibaba Group (FunASR) 开发并开源的，遵循 FunASR Model License 1.1。 该脚本使用了由 k2-fsa / sherpa-onnx 项目提供的 ONNX 转换版本。
- **自动静音检测 (VAD)**：在检测到一段时间的静音后自动停止录音并开始识别。
- **快捷键绑定**：支持全局热键（默认 `Ctrl+Shift+I`）呼出语音对话。

## 4. SoVITS 管理器 (`sovits_manager.py`)
负责管理 SoVITS 后台进程。
- **自动启动/关闭**：程序启动时自动寻找 `GPT-SoVITS` 路径并启动 API 服务器，程序关闭时自动清理进程。
- **运行时环境**：支持使用项目内置的精简运行时环境启动。

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。
