@echo off
setlocal
cd /d "%~dp0"
title KG beta version 3.0 - install Meta MMS (free offline Burmese voice)

set "PY=python"
where py >nul 2>nul && set "PY=py -3.12"

echo Installing torch + transformers (about 200 MB or more, one time)...
%PY% -m pip install -r requirements-mms.txt || goto :fail
echo.
echo Done. In the app choose  TTS provider = Meta MMS (offline).  The voice model downloads on the first run.
pause
exit /b 0

:fail
echo.
echo FAILED - check the messages above. Python 3.12 (64-bit) and internet are needed.
pause
exit /b 1
