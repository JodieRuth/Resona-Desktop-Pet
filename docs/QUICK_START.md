# 🚀 快速开始 (Quick Start)

按照以下步骤，在几分钟内运行您的 ResonaDesktopPet。

## 0. 准备工作 (Prerequisites)
**必选环境**：
- **Microsoft Visual C++ Redistributable (2015-2022)**:
  - 许多核心库（如 PySide6, NumPy, SoVITS）依赖此环境。
  - **[点击此处从微软官网下载 x64 版本](https://aka.ms/vs/17/release/vc_redist.x64.exe)** 并安装。
- **Python 3.12** (如果您不打算使用 `setup.ps1` 的 Full Runtime 模式)。

## 1. 安装
1. **克隆仓库**：`git clone https://github.com/JodieRuth/Resona-Desktop-Pet.git`
2. **环境配置**：
   - 右键点击 `setup.ps1`，选择 **"使用 PowerShell 运行"**。
   - **方案 2 (推荐)**：为您创建一个独立的 Runtime 环境，不影响系统 Python。
   - **方案 3**：在当前目录下创建 `.venv` 虚拟环境。
   - 脚本会自动下载必要的库、默认资源包和 STT 模型。

## 2. 配置 AI 后端
1. 打开根目录下的 `config.cfg`。
2. **LLM 配置**：
   - `model_select`: 选择模型（1-10 或 Local）。支持的模型：
     - `1`: OpenAI (ChatGPT)
     - `2`: DeepSeek (默认，推荐)
     - `3`: Claude (Anthropic)
     - `4`: Kimi (Moonshot)
     - `5`: Gemini (Google)
     - `6`: Grok (xAI)
     - `7`: Qwen (通义千问)
     - `8`: GitHub Models
     - `9`: OpenAI Compatible (任何兼容 OpenAI API 格式的模型)
     - `10`: Zhipu (智谱 AI)
     - `Local`: 本地模型 (Ollama 等)
   - `api_key`: 填入您的 API Key。
   - `base_url`: 如果使用第三方服务或本地转发，请填写对应的 API 地址。
3. **SoVITS 配置**：
   - 确保已按照 README 的说明获取 SoVITS 整合包并解压到指定路径。
   - 设置 `enabled = true`（在 `[SoVITS]` 节中）。
4. **OCR 配置（可选）**：
   - 在 `config.cfg` 的 `[OCR]` 中配置 `enabled`、服务商与密钥。
   - **多模态模型**：设置 `vlm_enabled = true` 可使用多模态模型直接识别屏幕截图，此时 OCR 会被自动禁用。如果你选择的目标模型不具有多模态能力，后果自负，我无法预测实际上会怎么样。
   - 启用 OCR/VLM 会截取当前屏幕并发送到第三方服务进行识别，可能包含敏感信息。启用即视为知情并自行承担由此带来的全部后果。
5. **启用 MCP (高级/可选)**：
   - 在 `config.cfg` 中找到 `[MCP]` 节。
   - 设置 `enabled = true`。
   - **可选配置**：
     - `server_dir`: MCP 服务器工作目录（默认 `mcpserver`）
     - `startup_timeout`: MCP 服务器启动超时时间（秒，默认 20）
     - `max_tool_rounds`: 单次对话中工具最多调用轮数（默认 30）
   - **注意**：开启后 LLM 将获得文件读写与命令执行权限，且 Token 消耗会显著增加。请确保您了解相关风险。
6. **启用 HTML 服务器**：
   - 在 `config.cfg` 中找到 `[HTML]` 节。
   - 设置 `enabled = true`。
   - 启用后默认在 8000 端口运行，可通过其他设备访问局域网内本机的服务端。HTML 中部分功能被调整。
7. **启用定时任务（可选）**：
   - 在 `config.cfg` 中找到 `[Timer]` 节。
   - 设置 `enabled = true` 启用定时任务调度器。
   - MCP 工具可以写入定时任务，主程序会轮询并触发。

## 3. 运行
- 双击 `run.bat`。
- 看到桌面宠物出现后，您可以：
  - **点击它**：弹出对话框进行文字交流。
  - **按下 Ctrl+Shift+I**：开始/停止录音。
  - **右键点击**：切换服装、切换角色包或进入设置。

## 4. 进阶
- 想要修改角色的性格？编辑 `packs/Resona_Default/prompts/character_prompt.txt`。
- 想要添加自定义触发动作？运行 `tools/trigger_editor.py`。
- 想要更换立绘？使用 `tools/sprite_organizer.py`。
- 想要调试触发器？在 `config.cfg` 中设置 `debugtrigger = true`，然后运行 `tools/sensor_mocker.py`。

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。
