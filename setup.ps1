# Resona Desktop Pet Ultimate Setup Script
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$PYTHON_EMBED_URL = 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
$PIP_GET_URL = 'https://bootstrap.pypa.io/get-pip.py'
$SOVITS_URL = 'https://huggingface.co/datasets/JodieRuth/test123/resolve/main/GPT-SoVITS-v2pro-20250604.zip'
$PACK_URL = 'https://huggingface.co/datasets/JodieRuth/test1/resolve/main/Resona_Default.zip'
# External Dependency: SenseVoiceSmall (by Alibaba FunASR)
# Distribution & Conversion by k2-fsa/sherpa-onnx (Apache-2.0)
$STT_URL = 'https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17.tar.bz2'

# --- GPU Detection ---
$gpus = Get-CimInstance Win32_VideoController
$isNvidia50 = $false
foreach ($gpu in $gpus) {
    $gpuName = $gpu.Name.ToUpper()
    if ($gpuName -like "*NVIDIA*" -and $gpuName -like "*RTX 50*") {
        $isNvidia50 = $true
        $SOVITS_URL = 'https://huggingface.co/datasets/JodieRuth/test123/resolve/main/GPT-SoVITS-v2pro-20250604-nvidia50.zip'
        Write-Host "[Resona] Detected NVIDIA 50-series GPU: $($gpu.Name). Using optimized SoVITS version." -ForegroundColor Green
        break
    }
}

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

# --- 0. Mirror Setup ---
Write-Host "`n[Mirror] Enable mirror acceleration? (Highly recommended for Mainland China)" -ForegroundColor Cyan
Write-Host "  - HuggingFace -> hf-mirror.com (Models & Assets)"
Write-Host "  - GitHub      -> gh-proxy.com  (STT Models)"
Write-Host "  - PyPI        -> tsinghua.edu  (Python Dependencies)"
$useMirror = Read-Host 'Enable these mirrors? (Y/N, default is N)'
if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
    $SOVITS_URL = $SOVITS_URL -replace 'huggingface.co', 'hf-mirror.com'
    $PACK_URL = $PACK_URL -replace 'huggingface.co', 'hf-mirror.com'
    # GitHub Mirror
    $STT_URL = "https://gh-proxy.com/" + $STT_URL
    Write-Host "[Resona] Using Mirrors: hf-mirror.com & gh-proxy.com" -ForegroundColor Cyan
}

# --- 0.1 C++ Runtime Check ---
Write-Host "`n[Check] Checking for Microsoft Visual C++ Redistributable..." -ForegroundColor Cyan
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
    Write-Host "This is REQUIRED for PySide6, NumPy, and SoVITS to run."
    Write-Host "Download link: https://aka.ms/vs/17/release/vc_redist.x64.exe"
    $installVC = Read-Host 'Would you like to open the download page? (Y/N, default is Y)'
    if ($installVC -ne 'N' -and $installVC -ne 'n') {
        Start-Process "https://aka.ms/vs/17/release/vc_redist.x64.exe"
        Write-Host "Please install the redistributable and then restart this script." -ForegroundColor Yellow
        pause
    }
} else {
    Write-Host "[Resona] C++ Runtime detected." -ForegroundColor Green
}

# --- 1. Proxy Setup ---
$useProxy = Read-Host 'Do you need a proxy for downloading? (Y/N, default is N)'
$proxyObject = $null
if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
    $proxyAddr = Read-Host 'Enter proxy address (e.g., 127.0.0.1)'
    $proxyPort = Read-Host 'Enter proxy port (e.g., 7890)'
    $fullProxy = "http://$($proxyAddr):$proxyPort"
    $env:HTTP_PROXY = $fullProxy
    $env:HTTPS_PROXY = $fullProxy
    
    # Configure PowerShell session to use this proxy for all web requests
    $proxyObject = New-Object System.Net.WebProxy($fullProxy)
    [System.Net.WebRequest]::DefaultWebProxy = $proxyObject
    Write-Host "[Resona] Proxy set to: $fullProxy"
}

# --- 2. Installation Mode ---
Write-Host "`n[Resona] Select Environment Installation Mode:" -ForegroundColor Cyan
Write-Host '1. Global Installation (Install to system Python)'
Write-Host '2. Virtual Environment (Create venv in project folder, RECOMMENDED)'
Write-Host '3. Full Runtime (Download portable Python 3.12, for users without Python)'
Write-Host '4. Skip Environment Deployment (Resource download only)'
$mode = Read-Host 'Enter number (1/2/3/4)'

$PYTHON_EXEC = 'python'
$skipInstall = $false

if ($mode -eq '3') {
    if (!(Test-Path 'runtime')) {
        New-Item -ItemType Directory -Path 'runtime'
        Write-Host '[Resona] Downloading Python 3.12 embedded version...'
        $curlPythonArgs = @("-L", "-f", $PYTHON_EMBED_URL, "-o", "python_embed.zip", "--retry", "5", "--connect-timeout", "30")
        if ($useProxy -eq 'Y' -or $useProxy -eq 'y') { $curlPythonArgs += @("-x", $fullProxy) }
        & curl.exe @curlPythonArgs
        
        Expand-Archive -Path 'python_embed.zip' -DestinationPath 'runtime' -Force
        Remove-Item 'python_embed.zip'

        Write-Host '[Resona] Configuring pip...'
        $pthFile = Get-Item 'runtime\python312._pth'
        (Get-Content $pthFile) -replace '#import site', 'import site' | Set-Content $pthFile
        
        $curlPipArgs = @("-L", "-f", $PIP_GET_URL, "-o", "runtime\get-pip.py", "--retry", "5", "--connect-timeout", "30")
        if ($useProxy -eq 'Y' -or $useProxy -eq 'y') { $curlPipArgs += @("-x", $fullProxy) }
        & curl.exe @curlPipArgs
        
        $getPipArgs = @("runtime\get-pip.py", "--no-warn-script-location")
        if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
            $getPipArgs += @("--index-url", "https://pypi.tuna.tsinghua.edu.cn/simple")
        }
        .\runtime\python.exe @getPipArgs
        Remove-Item 'runtime\get-pip.py'
        

        Write-Host '[Resona] Pre-installing build tools (setuptools, wheel)...'
        $preInstallArgs = @("install", "setuptools", "wheel", "--no-warn-script-location", "--prefer-binary")
        if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
            $preInstallArgs += @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
        }
        .\runtime\python.exe -m pip @preInstallArgs
    }
    $PYTHON_EXEC = '.\runtime\python.exe'
}
elseif ($mode -eq '2') {
    Write-Host '[Resona] Creating virtual environment (venv)...'
    python -m venv venv
    $PYTHON_EXEC = '.\venv\Scripts\python.exe'
}
elseif ($mode -eq '4') {
    Write-Host '[Resona] Skipping environment deployment.'
    $skipInstall = $true
}
else {
    Write-Host '[Resona] Using system Python.'
    $PYTHON_EXEC = 'python'
}

# --- 3. Requirements ---
if (-not $skipInstall) {
    Write-Host '[Resona] Installing dependencies from requirements.txt...'
    $pipArgs = @("install", "-r", "requirements.txt", "--no-warn-script-location", "--upgrade", "--prefer-binary")
    
    if ($useMirror -eq 'Y' -or $useMirror -eq 'y') {
        $pipArgs += @("-i", "https://pypi.tuna.tsinghua.edu.cn/simple")
    }

    & $PYTHON_EXEC -m pip @pipArgs
}

# --- 4. User Choice Collection ---
Write-Host "`n[Resona] Download Preference Collection:" -ForegroundColor Cyan
$doDownloadSovits = $false
$doDownloadPack = $false
$doDownloadStt = $false

if (!(Test-Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604')) {
    $res = Read-Host 'Download SoVITS Inference Engine (~7.7GB Zip / 10.5GB Unpacked)? (Y/N)'
    if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadSovits = $true }
}

if (!(Test-Path 'packs\Resona_Default')) {
    $res = Read-Host 'Download Default Assets Pack (Resona_Default)? (Y/N)'
    if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadPack = $true }
}

if (!(Test-Path 'models\stt\sensevoice')) {
    $res = Read-Host 'Download STT (SenseVoice) Model (3GB Unpacked)? (Y/N)'
    if ($res -eq 'Y' -or $res -eq 'y') { $doDownloadStt = $true }
}

# --- 5. Sequential Execution of Downloads ---

# SoVITS
if ($doDownloadSovits) {
    Write-Host "`n[Resona] Starting SoVITS download..." -ForegroundColor Cyan
    Write-Host '[Resona] Fetching SoVITS archive using curl (more reliable for large files)...'
    if (!(Test-Path 'GPT-SoVITS')) { New-Item -ItemType Directory -Path 'GPT-SoVITS' }
    
    $curlArgs = @("-L", "-f", "-C", "-", $SOVITS_URL, "-o", "sovits.zip", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
        $curlArgs += @("-x", $fullProxy)
    }
    
    Write-Host "[Resona] Running: curl.exe ..." -ForegroundColor Gray
    & curl.exe @curlArgs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting SoVITS (this may take a while)...'
        Expand-Archive -Path 'sovits.zip' -DestinationPath 'GPT-SoVITS' -Force
        Remove-Item 'sovits.zip'
        
        # Handle 50-series folder renaming
        if (Test-Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604-nvidia50') {
            Write-Host '[Resona] Renaming optimized SoVITS folder...'
            Rename-Item -Path 'GPT-SoVITS\GPT-SoVITS-v2pro-20250604-nvidia50' -NewName 'GPT-SoVITS-v2pro-20250604'
        }
    } else {
        Write-Error "[Resona] SoVITS Download failed."
    }
}

# Assets Pack
if ($doDownloadPack) {
    Write-Host "`n[Resona] Starting Assets Pack download..." -ForegroundColor Cyan
    Write-Host '[Resona] Fetching Assets Pack using curl...'
    if (!(Test-Path 'packs')) { New-Item -ItemType Directory -Path 'packs' }
    
    $curlArgs = @("-L", "-f", "-C", "-", $PACK_URL, "-o", "pack.zip", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
        $curlArgs += @("-x", $fullProxy)
    }

    & curl.exe @curlArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting Assets Pack...'
        Expand-Archive -Path 'pack.zip' -DestinationPath 'packs' -Force
        Remove-Item 'pack.zip'
    } else {
        Write-Error "[Resona] Assets Pack Download failed."
    }
}

# STT Model
if ($doDownloadStt) {
    Write-Host "`n[Resona] Starting STT Model download..." -ForegroundColor Cyan
    Write-Host '[Resona] Fetching STT Model...'
    if (!(Test-Path 'models\stt')) { New-Item -ItemType Directory -Path 'models\stt' }
    
    $curlArgs = @("-L", "-f", "-C", "-", $STT_URL, "-o", "stt_model.tar.bz2", "--retry", "5", "--connect-timeout", "30")
    if ($useProxy -eq 'Y' -or $useProxy -eq 'y') {
        $curlArgs += @("-x", $fullProxy)
    }

    & curl.exe @curlArgs

    if ($LASTEXITCODE -eq 0) {
        Write-Host '[Resona] Extracting STT Model (this may take a while)...'
        if (!(Test-Path 'models\stt\sensevoice')) { New-Item -ItemType Directory -Path 'models\stt\sensevoice' }
        & tar.exe -xvf stt_model.tar.bz2 -C models\stt\sensevoice --strip-components 1
        Remove-Item 'stt_model.tar.bz2'
    } else {
        Write-Error "[Resona] STT Model Download failed."
    }
}

Write-Host "`n[Resona] Setup complete! Please run run.bat to start." -ForegroundColor Green
pause
