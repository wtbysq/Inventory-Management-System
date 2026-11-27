# Build script for InventoryManager.exe
# Run:
#   powershell -ExecutionPolicy Bypass -File .\build_exe.ps1

$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found: $python"
}

Write-Host "[1/4] Installing project dependencies..."
& $python -m pip install -r requirements.txt

Write-Host "[2/4] Installing PyInstaller..."
& $python -m pip install "pyinstaller>=6.0"

Write-Host "[3/4] Cleaning old build..."
$running = Get-Process InventoryManager -ErrorAction SilentlyContinue
if ($running) {
    throw "InventoryManager.exe is running. Close it before building."
}
if (Test-Path "build") {
    Remove-Item "build" -Recurse -Force
}
if (Test-Path "dist") {
    Remove-Item "dist" -Recurse -Force
}

Write-Host "[4/4] Building exe..."
& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name "InventoryManager" `
    --collect-all uvicorn `
    --collect-all fastapi `
    --collect-all starlette `
    --collect-all pydantic `
    --collect-all pydantic_core `
    --collect-all pydantic_settings `
    --collect-all sqlalchemy `
    --hidden-import pymysql `
    --hidden-import greenlet `
    --hidden-import app.main `
    --add-data "app/static;app/static" `
    launcher.py

Copy-Item ".env.example" "dist\.env.example" -Force

# 把前端静态文件复制到 exe 目录：
# exe 运行时会优先读取同目录的 static，改页面后只需替换这个文件夹，无需重新打包。
Copy-Item "app\static" "dist\static" -Recurse -Force

# 打包产物直接输出到同级的「移植文件」目录，源码目录里不留 exe。
$exportDir = Join-Path (Split-Path $PSScriptRoot -Parent) "移植文件"
New-Item -ItemType Directory -Force $exportDir | Out-Null

Copy-Item "dist\InventoryManager.exe" (Join-Path $exportDir "InventoryManager.exe") -Force
Copy-Item "app\static" (Join-Path $exportDir "static") -Recurse -Force
Copy-Item ".env.example" (Join-Path $exportDir ".env.example") -Force

Write-Host ""
Write-Host "Build finished:"
Write-Host "  $exportDir\InventoryManager.exe   <- 双击启动"
Write-Host "  $exportDir\static\                <- 前端文件（改页面只需替换这里）"
Write-Host "Put a .env file next to the exe to configure MySQL."
