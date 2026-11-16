@echo off
rem Builds dist\Hanpaper\ (PyInstaller) and packaging\Output\Hanpaper-Setup.exe (Inno Setup).
rem Keep this file ASCII: cmd.exe parses .bat files in the OEM code page.
setlocal
cd /d "%~dp0.."
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  py -3 -m venv .venv || exit /b 1
)
"%PY%" -m pip install -q --disable-pip-version-check -r requirements.txt pyinstaller Pillow || exit /b 1
"%PY%" packaging\make_icon.py || exit /b 1
"%PY%" -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging\hanpaper.spec || exit /b 1

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo [!] Inno Setup not found: skipped the installer. dist\Hanpaper can be zipped and shared as is.
  exit /b 0
)
"%ISCC%" /Q packaging\installer.iss || exit /b 1
echo.
echo [v] Done: packaging\Output
endlocal
