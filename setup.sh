#!/bin/bash


ERROR_OCCURRED=0
ERROR_MESSAGES=()
LAST_ERROR=""

error_handler() {
    local exit_code=$?
    local error_line="${BASH_LINENO[0]}"
    local error_command="${BASH_COMMAND}"
    

    if [ $exit_code -eq 0 ]; then
        return
    fi
    
    ERROR_OCCURRED=1
    LAST_ERROR="退出码: $exit_code, 行: $error_line, 命令: $error_command"
    ERROR_MESSAGES+=("$LAST_ERROR")
    
    echo -e "\n[错误捕获] $LAST_ERROR" >&2
    
    return $exit_code
}

trap error_handler ERR

safe_exit() {
    local exit_code=${1:-0}
    
    if [ $exit_code -ne 0 ]; then
        ERROR_OCCURRED=1
        LAST_ERROR="安全退出，退出码: $exit_code"
        ERROR_MESSAGES+=("$LAST_ERROR")
        echo "[错误] $LAST_ERROR" >&2
    fi
    
    if [ $ERROR_OCCURRED -eq 1 ]; then
        echo -e "\n════════════════════════════════════════"
        echo "错误摘要:"
        for err_msg in "${ERROR_MESSAGES[@]}"; do
            echo "  • $err_msg"
        done
        echo "════════════════════════════════════════"
        
        echo -e "\n脚本遇到错误，但已继续执行。"
        echo "按Enter键查看最终结果..."
        read -n 1 -s
        echo
    fi
    
    exit $exit_code
}

PYTHON_EMBED_URL='https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
PIP_GET_URL='https://bootstrap.pypa.io/get-pip.py'
SOVITS_URL='https://hf-mirror.com/datasets/JodieRuth/test123/resolve/main/GPT-SoVITS-v2pro-20250604.zip'
PACK_URL='https://hf-mirror.com/datasets/JodieRuth/test1/resolve/main/Resona_Default.zip'
STT_URL='https://gh-proxy.com/https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2'


DISCLAIMER="*******************************************************************************
*                                DISCLAIMER                                   *
*******************************************************************************
* This code is licensed under MIT License.                                    *
* The assets downloaded by this script contain third-party copyrighted        *
* materials (Navel / Okura Resona).                                           *
* 1. Assets are for personal research and non-commercial use only.            *
* 2. Commercial use of assets or models is strictly prohibited.               *
* 3. This script is a tool only and does not own or distribute the assets.    *
*******************************************************************************"

clear
echo "$DISCLAIMER"
echo -e "\n[Resona] Starting Linux Setup Script..."
echo

# --- 0. Check for required system tools ---
echo "[Check] Checking for required system tools..."
MISSING_TOOLS=""

PYTHON_CMD=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
    echo "[信息] 使用 'python' 命令代替 'python3'"
else
    MISSING_TOOLS="$MISSING_TOOLS python3/python"
fi

PIP_CMD=""
if command -v pip3 >/dev/null 2>&1; then
    PIP_CMD="pip3"
elif command -v pip >/dev/null 2>&1; then
    PIP_CMD="pip"
    echo "[信息] 使用 'pip' 命令代替 'pip3'"
else
    MISSING_TOOLS="$MISSING_TOOLS pip3/pip"
fi

command -v curl >/dev/null 2>&1 || MISSING_TOOLS="$MISSING_TOOLS curl"
command -v tar >/dev/null 2>&1 || MISSING_TOOLS="$MISSING_TOOLS tar"
command -v unzip >/dev/null 2>&1 || MISSING_TOOLS="$MISSING_TOOLS unzip"

if [ -n "$MISSING_TOOLS" ]; then
    echo "[警告] 缺少必需工具:$MISSING_TOOLS"
    echo "请使用包管理器安装这些工具:"
    echo "  Debian/Ubuntu: sudo apt install python3 python3-pip curl tar unzip"
    echo "  Fedora/RHEL: sudo dnf install python3 python3-pip curl tar unzip"
    echo "  Arch: sudo pacman -S python python-pip curl tar unzip"
    echo "  其他发行版: 请安装对应的python、pip、curl、tar、unzip包"
    read -p "继续执行？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "[信息] 用户选择退出安装。"
        safe_exit 1
    fi
fi

# --- 0.1 System dependencies for audio and GUI ---
echo "[Check] Checking for system dependencies..."
if ! pkg-config --exists portaudio-2.0 2>/dev/null; then
    echo "[Info] PortAudio development files not found. pyaudio may need them."
    echo "  Debian/Ubuntu: sudo apt install portaudio19-dev"
    echo "  Fedora/RHEL: sudo dnf install portaudio-devel"
    echo "  Arch: sudo pacman -S portaudio"
fi

if ! pkg-config --exists Qt6Core 2>/dev/null; then
    echo "[Info] Qt6 development files not found. PySide6 may need them."
    echo "  Debian/Ubuntu: sudo apt install qt6-base-dev"
    echo "  Fedora/RHEL: sudo dnf install qt6-qtbase-devel"
    echo "  Arch: sudo pacman -S qt6-base"
fi

# --- 1. Mirror Setup ---
echo -e "\n[Mirror] Enable mirror acceleration? (Recommended for Mainland China)"
echo "  - HuggingFace -> hf-mirror.com (Models & Assets)"
echo "  - GitHub      -> gh-proxy.com  (STT Models)"
echo "  - PyPI        -> tsinghua.edu  (Python Dependencies)"
read -p "Enable these mirrors? (Y/N, default is N): " use_mirror
use_mirror=${use_mirror:-N}

if [[ $use_mirror == "Y" || $use_mirror == "y" ]]; then
    SOVITS_URL=${SOVITS_URL//huggingface\.co/hf-mirror.com}
    PACK_URL=${PACK_URL//huggingface\.co/hf-mirror.com}
    STT_URL="https://gh-proxy.com/${STT_URL#https://}"
    echo "[Resona] Using Mirrors: hf-mirror.com (HuggingFace) & gh-proxy.com (GitHub)"

fi

# --- 2. Proxy Setup ---
read -p "Do you need a proxy for downloading? (Y/N, default is N): " use_proxy
use_proxy=${use_proxy:-N}

if [[ $use_proxy == "Y" || $use_proxy == "y" ]]; then
    read -p "Enter proxy address (e.g., 127.0.0.1): " proxy_addr
    read -p "Enter proxy port (e.g., 7890): " proxy_port
    export http_proxy="http://$proxy_addr:$proxy_port"
    export https_proxy="http://$proxy_addr:$proxy_port"
    echo "[Resona] Proxy set to: http://$proxy_addr:$proxy_port"
fi

# --- 3. Installation Mode ---
echo -e "\n[Resona] Select Environment Installation Mode:"
echo "1. Global Installation (Install to system Python)"
echo "2. Virtual Environment (Create venv in project folder, RECOMMENDED)"
echo "3. Full Runtime (Download portable Python 3.12, for users without Python)"
echo "4. Skip Environment Deployment (Resource download only)"
read -p "Enter number (1/2/3/4, default is 2): " mode
mode=${mode:-2}

PYTHON_EXEC="${PYTHON_CMD:-python3}"
PIP_EXEC="${PIP_CMD:-pip3}"
skip_install=false

case $mode in
    1)
        echo "[Resona] Using system Python."
        ;;
    2)
        echo "[Resona] Creating virtual environment (venv)..."
        $PYTHON_EXEC -m venv venv
        PYTHON_EXEC="./venv/bin/python"
        PIP_EXEC="./venv/bin/pip"
        ;;
    3)
        echo "[Resona] Downloading portable Python..."
        if [ ! -d "runtime" ]; then
            mkdir -p runtime
            echo "[Resona] Downloading Python 3.12 embedded version..."
            curl -L -f "$PYTHON_EMBED_URL" -o python_embed.zip --retry 5 --connect-timeout 30
            unzip -q python_embed.zip -d runtime
            rm python_embed.zip

            echo "[Resona] Configuring pip..."
            pth_file=$(find runtime -name "python*._pth" | head -n1)
            if [ -f "$pth_file" ]; then
                sed -i 's/#import site/import site/' "$pth_file"
            fi
            
            curl -L -f "$PIP_GET_URL" -o runtime/get-pip.py --retry 5 --connect-timeout 30
            ./runtime/python runtime/get-pip.py --no-warn-script-location
            rm runtime/get-pip.py

            echo "[Resona] Pre-installing build tools (setuptools, wheel)..."
            ./runtime/python -m pip install setuptools wheel --no-warn-script-location --prefer-binary
        fi
        PYTHON_EXEC="./runtime/python"
        PIP_EXEC="./runtime/python -m pip"
        ;;
    4)
        echo "[Resona] Skipping environment deployment."
        skip_install=true
        ;;
    *)
        echo "[Resona] Invalid choice, using virtual environment."
        $PYTHON_EXEC -m venv venv
        PYTHON_EXEC="./venv/bin/python"
        PIP_EXEC="./venv/bin/pip"
        ;;
esac

# --- 4. Requirements Installation ---
if [ "$skip_install" = false ]; then
    echo "[Resona] Installing dependencies from requirements.txt..."
    pip_args="install -r requirements.txt --no-warn-script-location --upgrade --prefer-binary"
    
    if [[ $use_mirror == "Y" || $use_mirror == "y" ]]; then
        pip_args="$pip_args -i https://pypi.tuna.tsinghua.edu.cn/simple"
    fi
    
    $PIP_EXEC $pip_args
fi

# --- 5. User Choice Collection ---
echo -e "\n[Resona] Download Preference Collection:"

do_download_sovits=false
do_download_pack=false
do_download_stt=false


if [ -f "GPT-SoVITS/GPT-SoVITS-v2pro-20250604/api_v2.py" ]; then
    echo "[Resona] SoVITS detected. Skipping."
else
    read -p "Download SoVITS Inference Engine (~7.7GB Zip / 10.5GB Unpacked)? (Y/N): " res
    if [[ $res == "Y" || $res == "y" ]]; then
        do_download_sovits=true
    fi
fi

if [ -f "packs/Resona_Default/pack.json" ]; then
    echo "[Resona] Default Pack detected. Skipping."
else
    read -p "Download Default Assets Pack (Resona_Default)? (Y/N): " res
    if [[ $res == "Y" || $res == "y" ]]; then
        do_download_pack=true
    fi
fi

stt_installed=false
if [ -f "models/stt/sensevoice/model.int8.onnx" ] || [ -f "models/stt/sensevoice/zh.onnx" ]; then
    stt_installed=true
fi
if [ "$stt_installed" = false ] && [ -n "$(find models/stt/sensevoice -name '*.onnx' 2>/dev/null | head -n1)" ]; then
    stt_installed=true
fi

if [ "$stt_installed" = true ]; then
    echo "[Resona] STT Model detected. Skipping."
else
    read -p "Download STT (SenseVoice) Model (3GB Unpacked)? (Y/N): " res
    if [[ $res == "Y" || $res == "y" ]]; then
        do_download_stt=true
    fi
fi

if [ -f "ffmpeg/bin/ffmpeg" ]; then
    echo "[Resona] FFmpeg detected."
else
    echo -e "\n[Resona] FFmpeg is required for audio processing."
    echo "Please install ffmpeg using your system package manager:"
    echo "  Debian/Ubuntu: sudo apt install ffmpeg"
    echo "  Fedora/RHEL: sudo dnf install ffmpeg"
    echo "  Arch: sudo pacman -S ffmpeg"
    echo "  macOS (Homebrew): brew install ffmpeg"
    echo "After installation, ensure ffmpeg is available in your PATH."
    echo "You can verify by running: ffmpeg -version"
    echo
    echo "If you have installed ffmpeg elsewhere, you can copy the executable"
    echo "to ffmpeg/bin/ffmpeg in this directory."
fi

# --- 6. Sequential Execution of Downloads ---

if [ "$do_download_sovits" = true ]; then
    echo -e "\n[Resona] Starting SoVITS download..."
    echo "[Resona] Fetching SoVITS archive using curl..."
    mkdir -p GPT-SoVITS
    
    echo "[Resona] Downloading (this may take a while)..."
    curl -L -f -C - "$SOVITS_URL" -o sovits.zip --retry 5 --connect-timeout 30
    
    if [ $? -eq 0 ]; then
        echo "[Resona] Extracting SoVITS (this may take a while)..."
        unzip -q sovits.zip -d GPT-SoVITS
        rm sovits.zip
        
        if [ -d "GPT-SoVITS/GPT-SoVITS-v2pro-20250604-nvidia50" ]; then
            echo "[Resona] Renaming optimized SoVITS folder..."
            mv "GPT-SoVITS/GPT-SoVITS-v2pro-20250604-nvidia50" "GPT-SoVITS/GPT-SoVITS-v2pro-20250604"
        fi
    else
        echo "[Resona] SoVITS Download failed."
    fi
fi

# Assets Pack
if [ "$do_download_pack" = true ]; then
    echo -e "\n[Resona] Starting Assets Pack download..."
    echo "[Resona] Fetching Assets Pack using curl..."
    mkdir -p packs
    
    curl -L -f -C - "$PACK_URL" -o pack.zip --retry 5 --connect-timeout 30
    
    if [ $? -eq 0 ]; then
        echo "[Resona] Extracting Assets Pack..."
        unzip -q pack.zip -d packs
        rm pack.zip
    else
        echo "[Resona] Assets Pack Download failed."
    fi
fi

# STT Model
if [ "$do_download_stt" = true ]; then
    echo -e "\n[Resona] Starting STT Model download..."
    echo "[Resona] Fetching STT Model..."
    mkdir -p models/stt
    
    curl -L -f -C - "$STT_URL" -o stt_model.tar.bz2 --retry 5 --connect-timeout 30
    
    if [ $? -eq 0 ]; then
        echo "[Resona] Extracting STT Model (this may take a while)..."
        mkdir -p models/stt/sensevoice
        tar -xf stt_model.tar.bz2 -C models/stt/sensevoice --strip-components=1
        rm stt_model.tar.bz2
    else
        echo "[Resona] STT Model Download failed."
    fi
fi



if [ $ERROR_OCCURRED -eq 1 ]; then
    echo -e "\n════════════════════════════════════════"
    echo "安装完成，但检测到以下错误："
    for err_msg in "${ERROR_MESSAGES[@]}"; do
        echo "  • $err_msg"
    done
    echo "════════════════════════════════════════"
    echo -e "\n[警告] 安装过程中出现错误，部分功能可能无法正常工作。"
    echo "建议检查上述错误信息并解决问题后重新运行安装。"
else
    echo -e "\n[Resona] 安装成功完成！"
fi

echo -e "\n[Resona] Setup complete!"
echo "To start Resona Desktop Pet, run:"
if [ "$mode" = "2" ]; then
    echo "  source venv/bin/activate"
    echo "  python main.py"
elif [ "$mode" = "3" ]; then
    echo "  ./runtime/python main.py"
else
    echo "  ${PYTHON_CMD:-python3} main.py"
fi
echo
echo "Or create a shell script with the appropriate python command."

echo -e "\n════════════════════════════════════════"
if [ $ERROR_OCCURRED -eq 1 ]; then
    echo "按Enter键退出（建议查看上方错误信息）..."
else
    echo "按Enter键退出..."
fi
read -n 1 -s
echo