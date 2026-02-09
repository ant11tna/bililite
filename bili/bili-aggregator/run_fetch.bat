@echo off
cd /d %~dp0
.\.venv\Scripts\python.exe -c "import yaml; from app.fetcher import run_fetch; cfg=yaml.safe_load(open('config.yaml','r',encoding='utf-8')); print(run_fetch(cfg))"
