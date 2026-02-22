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
   - `model_type`: 选择 1 (DeepSeek/OpenAI), 5 (Gemini) 或 3 (Claude)。
   - `api_key`: 填入您的 API Key。
   - `base_url`: 如果使用 DeepSeek 或本地转发，请填写（如 `https://api.deepseek.com`）。
3. **SoVITS 配置**：
   - 确保已按照 README 的说明获取 SoVITS 整合包并解压到指定路径。
   - 设置 `sovits_enabled = true`。
4. **OCR 配置（可选）**：
   - 在 `config.cfg` 的 `[OCR]` 中配置 `enabled`、服务商与密钥。
   - 启用 OCR 会截取当前屏幕并发送到第三方 OCR 服务进行识别，可能包含敏感信息。启用即视为知情并自行承担由此带来的全部后果。
5. **启用 MCP (高级/可选)**：
   - 在 `config.cfg` 中找到 `[MCP]` 节。
   - 设置 `enabled = true`。
   - **注意**：开启后 LLM 将获得文件读写与命令执行权限，且 Token 消耗会显著增加。请确保您了解相关风险。
6. **启用 HTML 服务器**
   - 在 `config.cfg` 中找到 `[HTML]` 节
   - 设置 `enabled = true`。
   - 启用后默认在8000端口下运行，可通过其他设备访问局域网内本机的服务端。HTML 中部分功能被调整。

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

---
本文档部分使用大语言模型辅助生成，翻译亦由大语言模型完成，如出现任何偏差不代表作者的真实意愿。
