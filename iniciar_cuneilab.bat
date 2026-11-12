@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  echo Iniciando CuneiLab en http://127.0.0.1:8765
  start "" "http://127.0.0.1:8765"
  py -3 server.py
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    start "" "http://127.0.0.1:8765"
    python server.py
  ) else (
    echo Python 3 no detectado. Abri index.html para usar las funciones offline.
    pause
  )
)
