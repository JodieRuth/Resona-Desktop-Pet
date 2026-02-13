# Resona Desktop Pet - One-Click Zero-Config Setup Script
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# --- Configuration ---
# Using mirrors by default for best experience
$PYTHON_EMBED_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
$PIP_GET_URL = 'https://bootstrap.pypa.io/get-pip.py'
$SOVITS_URL = 'https://hf-mirror.com/datasets/JodieRuth/test123/resolve/main/GPT-SoVITS-v2pro-20250604.zip'
$PACK_URL = 'https://hf-mirror.com/datasets/JodieRuth/test1/resolve/main/Resona_Default.zip'
$STT_URL = 'https://gh-proxy.com/https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2'

$DISCLAIMER = @'
*******************************************************************************
*                                DISCLAIMER                                   *
*******************************************************************************
* This code is licensed under CC BY-NC-SA 4.0.                                *
* The assets downloaded by this script contain third-party copyrighted        *
* materials (Navel / Okura Resona).                                           *
* 1. Assets are for personal research and non-commercial use only.            *
* 2. Commercial use of assets or models is strictly prohibited.               *
* 3. This script is a tool only and does not own or distribute the assets.    *
*******************************************************************************
'@

Clear-Host
Write-Host $DISCLAIMER -ForegroundColor Yellow
Write-Host "`n[Resona] Starting One-Click Setup (Zero-Config Mode)..." -ForegroundColor Cyan

# --- 0. C++ Runtime Check ---
Write-Host "[Check] Checking for Microsoft Visual C++ Redistributable..." -ForegroundColor Cyan
$vc_installed = $false
$vc_registry_paths = @(
    "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\x64"
)

foreach ($path in $vc_registry_paths) {
    if (Test-Path $path) {
        $vc_installed = $true
        break
    }
}

if (-not $vc_installed) {
    Write-Host "[Warning] Microsoft Visual C++ Redistributable (2015-2022) not detected!" -ForegroundColor Yellow
    Write-Host "This is REQUIRED for the application to run."
    Write-Host "Download link: https://aka.ms/vs/17/release/vc_redist.x64.exe"
    $installVC = Read-Host 'Would you like to open the download page? (Y/N, default is Y)'
    if ($installVC -ne 'N' -and $installVC -ne 'n') {
        Start-Process "https://aka.ms/vs/17/release/vc_redist.x64.exe"
        Write-Host "Please install the redistributable and then restart this script." -ForegroundColor Yellow
        pause
        exit
    }
} else {
    Write-Host "[Resona] C++ Runtime detected." -ForegroundColor Green
}

# --- GPU Detection ---
$gpus = Get-CimInstance Win32_VideoController
foreach ($gpu in $gpus) {
    if ($gpu.Name -like "*RTX 50*") {
        $SOVITS_URL = 'https://hf-mirror.com/datasets/JodieRuth/test123/resolve/main/GPT-SoVITS-v2pro-20250604-nvidia50.zip'
        Write-Host "[Resona] Detected NVIDIA 50-series GPU: $($gpu.Name). Using optimized version." -ForegroundColor Green
        break
    }
}

# --- 1. Python Runtime Installation ---
if (!(Test-Path 'runtime')) {
    New-Item -ItemType Directory -Path 'runtime'
    Write-Host '[Resona] Downloading Python 3.12 runtime...'
    Invoke-WebRequest -Uri $PYTHON_EMBED_URL -OutFile 'python_embed.zip'
    Expand-Archive -Path 'python_embed.zip' -DestinationPath 'runtime' -Force
    Remove-Item 'python_embed.zip'

    Write-Host '[Resona] Configuring environment...'
    $pthFile = Get-Item 'runtime\python312._pth'
    (Get-Content $pthFile) -replace '#import site', 'import site' | Set-Content $pthFile
    Invoke-WebRequest -Uri $PIP_GET_URL -OutFile 'runtime\get-pip.py'
    .\runtime\python.exe runtime\get-pip.py --no-warn-script-location --index-url https://pypi.tuna.tsinghua.edu.cn/simple
    Remove-Item 'runtime\get-pip.py'
    
    Write-Host '[Resona] Installing build tools...'
    .\runtime\python.exe -m pip install setuptools wheel --no-warn-script-location --prefer-binary -i https://pypi.tuna.tsinghua.edu.cn/simple
}
$PYTHON_EXEC = '.\runtime\python.exe'

# --- 2. Dependencies ---
Write-Host "[Resona] Installing requirements..."
& $PYTHON_EXEC -m pip install -r requirements.txt --no-warn-script-location --upgrade --prefer-binary -i https://pypi.tuna.tsinghua.edu.cn/simple

# --- 3. Downloads ---

# SoVITS
if (!(Test-Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604')) {
    Write-Host "`n[Resona] Downloading SoVITS Engine (~7.7GB)..." -ForegroundColor Cyan
    if (!(Test-Path 'GPT-SoVITS')) { New-Item -ItemType Directory -Path 'GPT-SoVITS' }
    $curlArgs = @("-L", "-f", "-C", "-", $SOVITS_URL, "-o", "sovits.zip", "--retry", "5")
    & curl.exe @curlArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting SoVITS...'
        Expand-Archive -Path 'sovits.zip' -DestinationPath 'GPT-SoVITS' -Force
        Remove-Item 'sovits.zip'
        if (Test-Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604-nvidia50') {
            Rename-Item -Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604-nvidia50' -NewName 'GPT-SoVITS-v2pro-20250604'
        }
    }
}

# Assets Pack
if (!(Test-Path 'packs\Resona_Default')) {
    Write-Host "`n[Resona] Downloading Assets Pack..." -ForegroundColor Cyan
    if (!(Test-Path 'packs')) { New-Item -ItemType Directory -Path 'packs' }
    $curlArgs = @("-L", "-f", "-C", "-", $PACK_URL, "-o", "pack.zip", "--retry", "5")
    & curl.exe @curlArgs
    if ($LASTEXITCODE -eq 0) {
        Expand-Archive -Path 'pack.zip' -DestinationPath 'packs' -Force
        Remove-Item 'pack.zip'
    }
}

# STT Model
if (!(Test-Path 'models\stt\sensevoice')) {
    Write-Host "`n[Resona] Downloading STT Model..." -ForegroundColor Cyan
    if (!(Test-Path 'models\stt')) { New-Item -ItemType Directory -Path 'models\stt' }
    $curlArgs = @("-L", "-f", "-C", "-", $STT_URL, "-o", "stt_model.tar.bz2", "--retry", "5")
    & curl.exe @curlArgs
    if ($LASTEXITCODE -eq 0) {
        if (!(Test-Path 'models\stt\sensevoice')) { New-Item -ItemType Directory -Path 'models\stt\sensevoice' }
        & tar.exe -xvf stt_model.tar.bz2 -C models\stt\sensevoice --strip-components 1
        Remove-Item 'stt_model.tar.bz2'
    }
}

Write-Host "`n[Resona] All-in-one setup complete! Please run run.bat to start." -ForegroundColor Green
pause
