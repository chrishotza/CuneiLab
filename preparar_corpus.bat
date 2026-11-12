@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
  echo Python no disponible. Instala Python 3 desde python.org y activa Add to PATH.
  pause
  exit /b 1
)
echo Descarga autorizada: SumTablets train.csv, ~106 MB.
echo Se verificara SHA-256 antes de importar. Validation y test NO se descargan.
py -3 scripts\download_corpus.py --import
if %ERRORLEVEL% NEQ 0 (
  echo Hubo un problema. Revisa los detalles anteriores.
  pause
  exit /b 1
)
echo Corpus indexado. Ejecuta iniciar_cuneilab.bat para abrir CuneiLab.
pause
