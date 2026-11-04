# 安装拾帧的开发依赖。脚本只写入项目目录，不修改系统 PATH。
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$toolsRoot = Join-Path $projectRoot ".tools"
$uvLocal = Join-Path $toolsRoot "uv.exe"
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv -and (Test-Path $uvLocal)) {
    $uvPath = $uvLocal
} elseif ($uv) {
    $uvPath = $uv.Source
} else {
    Write-Host "正在下载 uv..."
    New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
    $uvJson = Join-Path $toolsRoot "uv-pypi.json"
    $uvWheel = Join-Path $toolsRoot "uv.whl"
    $uvExtract = Join-Path $toolsRoot "uv-download"
    & curl.exe -L --fail --retry 3 --output $uvJson "https://pypi.org/pypi/uv/json"
    $uvMeta = Get-Content -Raw $uvJson | ConvertFrom-Json
    $uvFile = $uvMeta.urls | Where-Object { $_.filename -like "*win_amd64.whl" } | Select-Object -First 1
    if (-not $uvFile) {
        throw "没有找到适用于 Windows x64 的 uv 发布包"
    }
    & curl.exe -L --fail --retry 3 --output $uvWheel $uvFile.url
    Expand-Archive -LiteralPath $uvWheel -DestinationPath $uvExtract -Force
    $downloadedUv = Get-ChildItem -Path $uvExtract -Filter "uv.exe" -Recurse | Select-Object -First 1
    if (-not $downloadedUv) {
        throw "uv 解压后没有找到 uv.exe"
    }
    Copy-Item -LiteralPath $downloadedUv.FullName -Destination $uvLocal -Force
    $uvPath = $uvLocal
}

Write-Host "正在安装 Python 3.12..."
& $uvPath python install 3.12

Write-Host "正在安装后端依赖..."
Push-Location (Join-Path $projectRoot "backend")
try {
    & $uvPath sync --dev
} finally {
    Pop-Location
}

$ffmpeg = Join-Path $toolsRoot "ffmpeg\bin\ffmpeg.exe"
if (-not (Test-Path $ffmpeg)) {
    Write-Host "正在下载 FFmpeg..."
    $ffmpegZip = Join-Path $toolsRoot "ffmpeg.zip"
    $ffmpegExtract = Join-Path $toolsRoot "ffmpeg-download"
    & curl.exe -L --fail --retry 3 --output $ffmpegZip "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $ffmpegExtract -Force
    $ffmpegExe = Get-ChildItem -Path $ffmpegExtract -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
    if (-not $ffmpegExe) {
        throw "FFmpeg 压缩包中缺少 ffmpeg.exe"
    }
    $ffmpegRoot = Split-Path (Split-Path $ffmpegExe.FullName -Parent) -Parent
    $ffmpegTarget = Join-Path $toolsRoot "ffmpeg"
    if (Test-Path $ffmpegTarget) {
        Remove-Item -LiteralPath $ffmpegTarget -Recurse -Force
    }
    Move-Item -LiteralPath $ffmpegRoot -Destination $ffmpegTarget
}

Write-Host "正在安装前端依赖..."
Push-Location (Join-Path $projectRoot "frontend")
try {
    npm install
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "开发环境已就绪。"
Write-Host "后端：cd backend; uv run uvicorn app.main:app --reload --port 8000"
Write-Host "前端：cd frontend; npm run dev"

