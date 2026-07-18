@echo off
echo Starting Micraft Growth Engine...

if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found at venv\Scripts\activate.bat
    echo Please ensure the python virtual environment is created and configured.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo Starting FastAPI Server...
echo Press Ctrl+C to stop the server.
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

pause
