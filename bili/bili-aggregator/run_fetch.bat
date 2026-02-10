@echo off
cd /d %~dp0
.\.venv\Scripts\python.exe -c "from app.config import load_config; from app.fetcher import run_fetch; print(run_fetch(load_config()))"
