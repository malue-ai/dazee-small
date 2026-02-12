#Requires -Version 5.1
param(
    [switch]$SkipBackend,
    [switch]$Clean
)

$ErrorActionPreference = "Continue"
$ProgressPreference = "SilentlyContinue"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path "$ScriptDir\..").Path
$FrontendDir = Join-Path $ProjectRoot "frontend"
$BinariesDir = Join-Path $FrontendDir "src-tauri\binaries"

function Info  { param([string]$m) Write-Host "===> $m" -ForegroundColor Cyan }
function Warn  { param([string]$m) Write-Host "WARN: $m" -ForegroundColor Yellow }
function Fail  { param([string]$m) Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }
function Ok    { param([string]$m) Write-Host "  OK  $m" -ForegroundColor Green }

function Test-Cmd {
    param([string]$c)
    $null -ne (Get-Command $c -ErrorAction SilentlyContinue)
}

function Refresh-Path {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    $cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
    if (Test-Path $cargoBin) {
        if ($env:Path -notlike "*$cargoBin*") { $env:Path = "$cargoBin;$env:Path" }
    }
}

# ==================== Step 0: Check Environment ====================

Info "Step 0: Checking build environment..."
Write-Host ""

$installed = $false
$hasWinget = Test-Cmd "winget"
if ($hasWinget) { Ok "winget available" } else { Warn "winget not found, will use direct download" }

# --- Python 3.12 ---
function Find-Python {
    foreach ($c in @("python3.12", "python3", "python", "py")) {
        if (Test-Cmd $c) {
            try {
                $v = ""
                if ($c -eq "py") { $v = (& py -3 --version 2>&1) | Out-String }
                else { $v = (& $c --version 2>&1) | Out-String }
                if ($v -match "Python 3\.1[23]") {
                    if ($c -eq "py") { return "py" }
                    return $c
                }
            } catch { }
        }
    }
    return $null
}

$PythonCmd = Find-Python
if ($PythonCmd) {
    if ($PythonCmd -eq "py") { $pv = (& py -3 --version 2>&1) | Out-String }
    else { $pv = (& $PythonCmd --version 2>&1) | Out-String }
    Ok "Python: $($pv.Trim())"
} else {
    Info "Installing Python 3.12..."
    if ($hasWinget) {
        & winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
    } else {
        $url = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
        $tmp = Join-Path $env:TEMP "python-installer.exe"
        Info "  Downloading..."
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        Start-Process -FilePath $tmp -ArgumentList "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_pip=1" -Wait
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
    Refresh-Path
    $PythonCmd = Find-Python
    if (-not $PythonCmd) { Fail "Python not found after install. Please install Python 3.12 manually and add to PATH." }
    $installed = $true
    Ok "Python installed"
}

# --- Node.js ---
if (Test-Cmd "node") {
    $nv = (node --version) -replace "v", ""
    $nm = [int]($nv.Split(".")[0])
    if ($nm -ge 18) {
        Ok "Node.js: v$nv"
    } else {
        Info "Node.js too old v$nv, upgrading..."
        if ($hasWinget) {
            & winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
        } else {
            $url = "https://nodejs.org/dist/v20.18.1/node-v20.18.1-x64.msi"
            $tmp = Join-Path $env:TEMP "node-installer.msi"
            Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
            Start-Process msiexec -ArgumentList "/i", "$tmp", "/quiet", "/norestart" -Wait
            Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        }
        Refresh-Path
        $installed = $true
    }
} else {
    Info "Installing Node.js 20 LTS..."
    if ($hasWinget) {
        & winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
    } else {
        $url = "https://nodejs.org/dist/v20.18.1/node-v20.18.1-x64.msi"
        $tmp = Join-Path $env:TEMP "node-installer.msi"
        Info "  Downloading..."
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        Start-Process msiexec -ArgumentList "/i", "$tmp", "/quiet", "/norestart" -Wait
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
    Refresh-Path
    if (-not (Test-Cmd "node")) { Fail "Node.js install failed. Please install manually: https://nodejs.org" }
    $installed = $true
    Ok "Node.js installed"
}

# --- MSVC Build Tools (required by Rust on Windows) ---
$hasMSVC = $false
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vsWhere) {
    $vsPath = (& $vsWhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>&1) | Out-String
    if ($vsPath.Trim()) { $hasMSVC = $true }
}
# Also check for standalone Build Tools via registry
if (-not $hasMSVC) {
    $clExe = Get-ChildItem "C:\Program Files\Microsoft Visual Studio" -Recurse -Filter "cl.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $clExe) {
        $clExe = Get-ChildItem "C:\Program Files (x86)\Microsoft Visual Studio" -Recurse -Filter "cl.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    }
    if ($clExe) { $hasMSVC = $true }
}

if ($hasMSVC) {
    Ok "MSVC Build Tools found"
} else {
    Info "MSVC Build Tools not found (required by Rust compiler)"
    Info "  Installing Visual Studio Build Tools..."
    if ($hasWinget) {
        & winget install Microsoft.VisualStudio.2022.BuildTools --accept-source-agreements --accept-package-agreements --silent --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
    } else {
        $vsUrl = "https://aka.ms/vs/17/release/vs_BuildTools.exe"
        $vsTmp = Join-Path $env:TEMP "vs_BuildTools.exe"
        Info "  Downloading Build Tools installer..."
        Invoke-WebRequest -Uri $vsUrl -OutFile $vsTmp -UseBasicParsing
        Start-Process -FilePath $vsTmp -ArgumentList "--wait", "--passive", "--add", "Microsoft.VisualStudio.Workload.VCTools", "--includeRecommended" -Wait
        Remove-Item $vsTmp -Force -ErrorAction SilentlyContinue
    }
    Refresh-Path
    $installed = $true
    Ok "MSVC Build Tools installed (may need restart if Rust compile fails)"
}

# --- CMake (required by llama-cpp-python compilation) ---
Refresh-Path
if (Test-Cmd "cmake") {
    Ok "CMake: $((cmake --version | Select-Object -First 1).Trim())"
} else {
    Info "Installing CMake (required by llama-cpp-python)..."
    if ($hasWinget) {
        & winget install Kitware.CMake --accept-source-agreements --accept-package-agreements --silent
    } else {
        $cmakeUrl = "https://github.com/Kitware/CMake/releases/download/v3.31.4/cmake-3.31.4-windows-x86_64.msi"
        $cmakeTmp = Join-Path $env:TEMP "cmake-installer.msi"
        Info "  Downloading CMake..."
        Invoke-WebRequest -Uri $cmakeUrl -OutFile $cmakeTmp -UseBasicParsing
        Start-Process msiexec -ArgumentList "/i", "$cmakeTmp", "/quiet", "/norestart", "ADD_CMAKE_TO_PATH=System" -Wait
        Remove-Item $cmakeTmp -Force -ErrorAction SilentlyContinue
    }
    Refresh-Path
    if (-not (Test-Cmd "cmake")) { Fail "CMake install failed. Please install manually: https://cmake.org/download/" }
    $installed = $true
    Ok "CMake installed"
}

# --- Rust ---
Refresh-Path
if ((Test-Cmd "rustc") -and (Test-Cmd "cargo")) {
    Ok "Rust: $(rustc --version)"
} else {
    Info "Installing Rust..."
    if ($hasWinget) {
        & winget install Rustlang.Rustup --accept-source-agreements --accept-package-agreements --silent
        Refresh-Path
        if (Test-Cmd "rustup") { & rustup default stable }
    } else {
        $url = "https://win.rustup.rs/x86_64"
        $tmp = Join-Path $env:TEMP "rustup-init.exe"
        Info "  Downloading rustup..."
        Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing
        Start-Process -FilePath $tmp -ArgumentList "-y", "--default-toolchain", "stable" -Wait
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
    Refresh-Path
    if (-not (Test-Cmd "cargo")) { Fail "Rust install failed. Please install manually: https://rustup.rs" }
    $installed = $true
    Ok "Rust installed"
}

# --- Python venv ---
$VenvDir = Join-Path $ProjectRoot ".venv"
$VenvPy = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $VenvPy)) {
    Info "Creating Python venv..."
    if ($PythonCmd -eq "py") { & py -3 -m venv $VenvDir }
    else { & $PythonCmd -m venv $VenvDir }
    $installed = $true
    Ok "venv created"
} else {
    Ok "venv exists"
}

# --- Configure pip mirror (China-friendly, permanent) ---
# Set pip mirror globally so ALL pip commands use it automatically.
# This avoids SSL issues when connecting to pypi.org from China.
Info "Configuring pip mirror..."
$pipMirrors = @(
    @{ url = "https://pypi.tuna.tsinghua.edu.cn/simple"; host = "pypi.tuna.tsinghua.edu.cn" },
    @{ url = "https://mirrors.aliyun.com/pypi/simple"; host = "mirrors.aliyun.com" },
    @{ url = "https://pypi.douban.com/simple"; host = "pypi.douban.com" }
)

$mirrorSet = $false
foreach ($m in $pipMirrors) {
    try {
        $wr = [System.Net.HttpWebRequest]::Create($m.url)
        $wr.Timeout = 8000
        $wr.UserAgent = "pip/24.0"
        $resp = $wr.GetResponse()
        $resp.Close()
        # Mirror reachable - configure pip permanently
        & $VenvPip config set global.index-url $m.url 2>&1 | Out-Null
        & $VenvPip config set global.trusted-host $m.host 2>&1 | Out-Null
        Ok "pip mirror: $($m.host)"
        $mirrorSet = $true
        break
    } catch {
        continue
    }
}
if (-not $mirrorSet) {
    Warn "No China pip mirror reachable, using default PyPI (may be slow)"
}

# --- Install Python dependencies ---
Info "Installing Python dependencies (this may take a few minutes)..."
$reqFile = Join-Path $ProjectRoot "requirements.txt"
& $VenvPip install -r $reqFile 2>&1 | Tee-Object -Variable pipOutput | ForEach-Object {
    $line = $_.ToString()
    if ($line -match "error|ERROR|Failed|Could not") { Warn "  $line" }
}
# Check pip exit code (Tee-Object preserves $LASTEXITCODE)
if ($LASTEXITCODE -ne 0) {
    Warn "pip install exited with code $LASTEXITCODE - some packages may have failed"
}

# Verify critical packages are installed
$criticalPkgs = @(
    # Web framework
    "fastapi", "uvicorn", "pydantic",
    # LLM clients
    "anthropic", "openai",
    # Async I/O
    "aiofiles", "aiohttp", "httpx",
    # Database
    "aiosqlite", "sqlalchemy",
    # Core utilities
    "yaml", "tiktoken", "numpy", "json5",
    # Memory system
    "sqlite_vec",
    # File processing
    "PIL",
    # Scheduling
    "apscheduler",
    # WebSocket
    "websockets"
)
$missingPkgs = @()
foreach ($pkg in $criticalPkgs) {
    $chk = & $VenvPy -c "import $pkg" 2>&1
    if ($LASTEXITCODE -ne 0) { $missingPkgs += $pkg }
}
if ($missingPkgs.Count -gt 0) {
    Fail "Critical packages missing: $($missingPkgs -join ', '). pip install failed - check your network connection."
}
Ok "Python deps verified ($($criticalPkgs.Count) critical packages)"

# --- Install PyInstaller ---
Info "Checking PyInstaller..."
$pyiCheck = & $VenvPy -c "import PyInstaller; print(PyInstaller.__version__)" 2>&1
if ($pyiCheck -match "^\d+\.\d+") {
    Ok "PyInstaller $($pyiCheck.Trim()) ready"
} else {
    Info "  Installing PyInstaller..."
    & $VenvPip install pyinstaller 2>&1 | ForEach-Object { Write-Host "    $_" }
    # Verify
    $pyiCheck2 = & $VenvPy -c "import PyInstaller; print(PyInstaller.__version__)" 2>&1
    if ($pyiCheck2 -match "^\d+\.\d+") {
        Ok "PyInstaller $($pyiCheck2.Trim()) installed"
    } else {
        Fail "PyInstaller install failed. Check network and try: .venv\Scripts\pip install pyinstaller"
    }
}

# --- Configure npm mirror (China-friendly) ---
Info "Configuring npm mirror..."
$currentRegistry = (& npm config get registry 2>&1).ToString().Trim()
if ($currentRegistry -match "npmmirror|taobao|cnpm") {
    Ok "npm mirror: $currentRegistry"
} else {
    & npm config set registry https://registry.npmmirror.com 2>&1 | Out-Null
    Ok "npm mirror: registry.npmmirror.com"
}

# --- Install npm deps ---
# Use .package-lock.json as integrity marker (created only after successful npm install)
$nm = Join-Path $FrontendDir "node_modules"
$lockMarker = Join-Path $nm ".package-lock.json"
if ((-not (Test-Path $nm)) -or (-not (Test-Path $lockMarker))) {
    if ((Test-Path $nm) -and (-not (Test-Path $lockMarker))) {
        Warn "node_modules exists but appears incomplete, reinstalling..."
    }
    Info "Installing frontend npm deps..."
    Push-Location $FrontendDir
    & npm install
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "npm install failed. Check your network." }
    Pop-Location
    $installed = $true
    Ok "npm deps installed"
} else {
    Ok "npm deps exist"
}

# --- Configure Rust cargo mirror (China-friendly) ---
$cargoConfigDir = Join-Path $env:USERPROFILE ".cargo"
$cargoConfigFile = Join-Path $cargoConfigDir "config.toml"
if (-not (Test-Path $cargoConfigFile)) {
    Info "Configuring cargo mirror (rsproxy.cn)..."
    New-Item -ItemType Directory -Force -Path $cargoConfigDir | Out-Null
    @"
[source.crates-io]
replace-with = 'rsproxy-sparse'

[source.rsproxy]
registry = "https://rsproxy.cn/crates.io-index"

[source.rsproxy-sparse]
registry = "sparse+https://rsproxy.cn/index/"

[registries.rsproxy]
index = "https://rsproxy.cn/crates.io-index"

[net]
git-fetch-with-cli = true
"@ | Set-Content -Path $cargoConfigFile -Encoding UTF8
    Ok "cargo mirror: rsproxy.cn"
} else {
    $cargoContent = Get-Content $cargoConfigFile -Raw -ErrorAction SilentlyContinue
    if ($cargoContent -match "rsproxy|ustc|tuna") {
        Ok "cargo mirror: already configured"
    } else {
        Ok "cargo config: using existing config"
    }
}

Write-Host ""
if ($installed) { Info "Environment ready - installed missing deps" }
else { Info "Environment ready - all deps found, skipped install" }
Write-Host ""

# ==================== Sync Version ====================
Info "Syncing version..."
& $VenvPy (Join-Path $ProjectRoot "scripts\sync_version.py")
if ($LASTEXITCODE -ne 0) { Fail "Version sync failed" }

# ==================== Clean ====================
if ($Clean) {
    Info "Cleaning build artifacts..."
    @(
        (Join-Path $ProjectRoot "build"),
        (Join-Path $ProjectRoot "dist"),
        (Join-Path $FrontendDir "dist"),
        (Join-Path $FrontendDir "src-tauri\target")
    ) | ForEach-Object {
        if (Test-Path $_) { Remove-Item $_ -Recurse -Force; Write-Host "  cleaned: $_" }
    }
    Get-ChildItem (Join-Path $BinariesDir "zenflux-backend-*") -ErrorAction SilentlyContinue | Remove-Item -Force
    $intDir = Join-Path $BinariesDir "_internal"
    if (Test-Path $intDir) { Remove-Item $intDir -Recurse -Force }
    Info "Clean done"
}

# ==================== Step 1: Build Python Backend ====================

if (-not $SkipBackend) {
    Info "Step 1/3: Building Python backend with PyInstaller..."
    Push-Location $ProjectRoot
    & $VenvPy scripts\build_backend.py
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Backend build failed" }
    Pop-Location
    Info "Backend build done"
} else {
    Info "Step 1/3: Skipped backend build"
    $sidecar = Join-Path $BinariesDir "zenflux-backend-x86_64-pc-windows-msvc.exe"
    if (-not (Test-Path $sidecar)) { Warn "No sidecar binary found in binaries/" }
}

# ==================== Pre-download Tauri Build Tools ====================
# WiX and NSIS are downloaded from GitHub by Tauri at build time.
# In China this often times out. Pre-download from mirrors to avoid stalling.

function Download-WithMirror {
    param(
        [string]$GithubUrl,
        [string]$OutFile,
        [int]$TimeoutSec = 120
    )
    # Mirror list (China-friendly GitHub proxies)
    $mirrors = @(
        "https://ghfast.top/",
        "https://mirror.ghproxy.com/",
        "https://gh-proxy.com/",
        ""  # direct GitHub as fallback
    )
    foreach ($prefix in $mirrors) {
        $url = "${prefix}${GithubUrl}"
        $label = if ($prefix) { $prefix } else { "GitHub direct" }
        Write-Host "    Trying: $label ..." -NoNewline
        try {
            $wr = [System.Net.HttpWebRequest]::Create($url)
            $wr.Timeout = $TimeoutSec * 1000
            $wr.ReadWriteTimeout = $TimeoutSec * 1000
            $wr.UserAgent = "Mozilla/5.0"
            $resp = $wr.GetResponse()
            $stream = $resp.GetResponseStream()
            $fs = [System.IO.File]::Create($OutFile)
            $stream.CopyTo($fs)
            $fs.Close()
            $stream.Close()
            $resp.Close()
            $mb = [math]::Round((Get-Item $OutFile).Length / 1MB, 1)
            Write-Host " OK (${mb} MB)" -ForegroundColor Green
            return $true
        } catch {
            Write-Host " Failed" -ForegroundColor Yellow
        }
    }
    return $false
}

Info "Pre-downloading Tauri build tools (WiX / NSIS)..."

# --- WiX 3.14 ---
$wixDir = Join-Path $env:LOCALAPPDATA "tauri\WixTools314"
if (Test-Path (Join-Path $wixDir "light.exe")) {
    Ok "WiX 3.14 already cached"
} else {
    Info "  Downloading WiX 3.14..."
    $wixZip = Join-Path $env:TEMP "wix314-binaries.zip"
    $wixUrl = "https://github.com/nicehash/wix/releases/download/wix3142rtm/wix314-binaries.zip"
    $ok = Download-WithMirror -GithubUrl $wixUrl -OutFile $wixZip
    if ($ok -and (Test-Path $wixZip)) {
        New-Item -ItemType Directory -Force -Path $wixDir | Out-Null
        try {
            & tar -xf $wixZip -C $wixDir 2>&1 | Out-Null
        } catch {
            Expand-Archive -Path $wixZip -DestinationPath $wixDir -Force
        }
        Remove-Item $wixZip -Force -ErrorAction SilentlyContinue
        if (Test-Path (Join-Path $wixDir "light.exe")) {
            Ok "WiX 3.14 ready"
        } else {
            Warn "WiX extraction may have issues, Tauri will retry"
        }
    } else {
        Warn "WiX download failed, Tauri will try GitHub directly (may be slow)"
    }
}

# --- NSIS 3.11 ---
$nsisToolDir = Join-Path $env:LOCALAPPDATA "tauri\NSIS"
if (Test-Path (Join-Path $nsisToolDir "makensis.exe")) {
    Ok "NSIS 3.11 already cached"
} else {
    Info "  Downloading NSIS 3.11..."
    $nsisZip = Join-Path $env:TEMP "nsis-3.11.zip"
    $nsisUrl = "https://github.com/nicehash/nsis/releases/download/nsis-3.11/nsis-3.11.zip"
    $ok = Download-WithMirror -GithubUrl $nsisUrl -OutFile $nsisZip
    if ($ok -and (Test-Path $nsisZip)) {
        $nsisTmp = Join-Path $env:TEMP "nsis-extract"
        if (Test-Path $nsisTmp) { Remove-Item $nsisTmp -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $nsisTmp | Out-Null
        try {
            & tar -xf $nsisZip -C $nsisTmp 2>&1 | Out-Null
        } catch {
            Expand-Archive -Path $nsisZip -DestinationPath $nsisTmp -Force
        }
        # NSIS zip may contain a subfolder like nsis-3.11/
        $inner = Get-ChildItem $nsisTmp -Directory | Select-Object -First 1
        $srcDir = if ($inner -and (Test-Path (Join-Path $inner.FullName "makensis.exe"))) { $inner.FullName } else { $nsisTmp }

        New-Item -ItemType Directory -Force -Path $nsisToolDir | Out-Null
        Copy-Item "$srcDir\*" $nsisToolDir -Recurse -Force
        Remove-Item $nsisTmp -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item $nsisZip -Force -ErrorAction SilentlyContinue
        if (Test-Path (Join-Path $nsisToolDir "makensis.exe")) {
            Ok "NSIS 3.11 ready"
        } else {
            Warn "NSIS extraction may have issues, Tauri will retry"
        }
    } else {
        Warn "NSIS download failed, Tauri will try GitHub directly (may be slow)"
    }
}

# --- NSIS Tauri plugin ---
$pluginDir = Join-Path $nsisToolDir "Plugins\x86-unicode"
if (Test-Path $pluginDir) {
    $pluginUrl = "https://github.com/nicehash/nsis/releases/download/nsis-3.11/nsis_tauri_utils.dll"
    $pluginFile = Join-Path $pluginDir "nsis_tauri_utils.dll"
    if (-not (Test-Path $pluginFile)) {
        Info "  Downloading NSIS Tauri plugin..."
        Download-WithMirror -GithubUrl $pluginUrl -OutFile $pluginFile | Out-Null
    }
}

Write-Host ""

# ==================== Step 2: Build Tauri App ====================

Info "Step 2/3: Building Tauri app..."
Push-Location $FrontendDir

if (-not (Test-Path "node_modules")) { & npm install }
$env:CI = ""

Info "  Running: npm run tauri:build"
& npm run tauri:build
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Tauri build failed" }
Pop-Location

# ==================== Step 3: Collect Output ====================

Info "Step 3/3: Collecting build output..."

$OutputDir = Join-Path $ProjectRoot "dist"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# Copy _internal to release dir for portable use
$intSrc = Join-Path $BinariesDir "_internal"
if (Test-Path $intSrc) {
    $relDir = Join-Path $FrontendDir "src-tauri\target\release"
    $intDst = Join-Path $relDir "_internal"
    if (-not (Test-Path $intDst)) {
        Copy-Item $intSrc $intDst -Recurse -Force
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  BUILD COMPLETE!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

# NSIS installer
$nsisDir = Join-Path $FrontendDir "src-tauri\target\release\bundle\nsis"
$exeFile = Get-ChildItem $nsisDir -Filter "*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1

if ($exeFile) {
    $mb = [math]::Round($exeFile.Length / 1MB, 1)
    Copy-Item $exeFile.FullName $OutputDir -Force
    Info "NSIS installer: $($exeFile.Name) -- ${mb} MB"
    Info "Copied to: $OutputDir\$($exeFile.Name)"
} else {
    Warn "NSIS installer not found"
}

# MSI
$msiDir = Join-Path $FrontendDir "src-tauri\target\release\bundle\msi"
$msiFile = Get-ChildItem $msiDir -Filter "*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($msiFile) {
    $mb = [math]::Round($msiFile.Length / 1MB, 1)
    Copy-Item $msiFile.FullName $OutputDir -Force
    Info "MSI installer: $($msiFile.Name) -- ${mb} MB"
}

Write-Host ""
Info "Output dir: $OutputDir"
Info "Send the installer to users. Double-click to install!"
Write-Host ""
