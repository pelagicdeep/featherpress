@echo off
rem ============================================================
rem  Featherpress drag-and-drop converter
rem  Drag one or more manuscripts (.md .txt .docx .pdf .epub) onto this file.
rem  Everything converts with defaults and the output folder opens.
rem ============================================================
setlocal
cd /d "%~dp0"

if "%~1"=="" (
  echo Drag a manuscript file onto this .bat to convert it.
  echo Accepted: .md  .txt  .docx  .pdf  .epub
  pause
  exit /b
)

set FAILED=0
:loop
if "%~1"=="" goto done
echo Converting: %~nx1
python featherpress.py "%~1" -o output --theme dark
if errorlevel 1 (
  python3 featherpress.py "%~1" -o output --theme dark
  if errorlevel 1 set FAILED=1
)
shift
goto loop

:done
if %FAILED%==1 (
  echo.
  echo Something went wrong with at least one file. The window will stay
  echo open so you can read the message above.
  pause
) else (
  start "" explorer "output"
)
endlocal
