@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==== DraveLeon - EXE bouwen ====
py -3.12 -c "import PyQt6.QtMultimedia, neuvoice, onnxruntime" || (echo FOUT: py -3.12 mist PyQt6/neuvoice/onnxruntime & pause & exit /b 1)
py -3.12 -m PyInstaller --noconfirm --clean --onedir --windowed --name DraveLeon --icon assets\icon.ico ^
  --add-data "assets;assets" --hidden-import leon --hidden-import uitspraak ^
  --collect-all neuvoice --collect-all onnxruntime ^
  --exclude-module torch --exclude-module torchvision --exclude-module torchaudio --exclude-module tensorflow ^
  --exclude-module transformers --exclude-module matplotlib --exclude-module pandas --exclude-module scipy ^
  --exclude-module PyQt6.QtWebEngineCore --exclude-module tkinter draveleon.py
if errorlevel 1 (echo FOUT: PyInstaller is mislukt & pause & exit /b 1)
if not exist "dist\DraveLeon\DraveLeon.exe" (echo FOUT: geen exe gemaakt & pause & exit /b 1)
xcopy /E /I /Y assets "dist\DraveLeon\assets" >nul
if exist DraveLeon-Snelgids.pdf copy /Y DraveLeon-Snelgids.pdf "dist\DraveLeon\" >nul
echo.
echo KLAAR: dist\DraveLeon\DraveLeon.exe
