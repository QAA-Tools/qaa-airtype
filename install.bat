@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在安装 QAA AirType 依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo 安装失败，请确认 Python 已安装并加入 PATH
  pause
  exit /b 1
)
echo 安装完成，双击 start.bat 启动程序
pause
