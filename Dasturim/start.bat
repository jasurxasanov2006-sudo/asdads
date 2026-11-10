@echo off
setlocal
cd /d "%~dp0backend"

if not exist "venv\Scripts\activate.bat" (
  echo Xato: backend\venv topilmadi. README.md dagi o'rnatish qadamlarini bajaring.
  pause
  exit /b 1
)

call "venv\Scripts\activate.bat"
start "" "http://127.0.0.1:8000/"
uvicorn main:app --reload --host 127.0.0.1 --port 8000
