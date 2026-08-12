# QAA-AirType 打包脚本
# 优先使用 conda 环境（存在时），否则使用系统 Python

$condaHook = "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1"
if (Test-Path $condaHook) {
    . $condaHook
    conda activate "$env:USERPROFILE\miniconda3"
}

python -m PyInstaller --onefile --windowed --name=QAA-AirType --icon=icon.ico `
    --add-data "icon.ico;." `
    --add-data "src/default.html;." `
    --add-data "src/static;static" `
    --add-data "theme/mqtt.html;theme" `
    --runtime-tmpdir=. `
    src\remote_server.py
