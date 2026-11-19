@echo off
REM Shiplystic lead pipeline worker. Register in Windows Task Scheduler:
REM   Trigger "At log on", Action: this file, "Start in": this folder.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if exist venv\Scripts\python.exe (set PY=venv\Scripts\python.exe) else (set PY=python)
%PY% scripts\pipeline_worker.py >> exports\pipeline_worker.log 2>&1
