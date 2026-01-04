. "$env:USERPROFILE\miniconda3\shell\condabin\conda-hook.ps1"
conda activate "$env:USERPROFILE\miniconda3"
pyinstaller --onefile --windowed --name=QAA-AirType --icon=icon.ico --add-data "icon.ico;." --add-data "src/default.html;." --runtime-tmpdir=. src\remote_server.py