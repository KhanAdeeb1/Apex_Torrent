@echo off
rem ======================================================================================
rem  ApexTorrent one-click release build  ->  dist\ApexTorrent_Setup.exe
rem
rem  Usage:   build_installer.bat [--skip-tests]
rem  Needs:   Python 3.10-3.13 (64-bit) and internet access for pip. Inno Setup 6.3+ is auto-detected
rem           (and installed with winget if missing).
rem  Signing: set SIGNTOOL_CMD before running, e.g.
rem           set SIGNTOOL_CMD=$qC:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe$q sign /fd sha256 /tr http://timestamp.digicert.com /td sha256 /a
rem           ($q = a quote character; the script appends $f, the file to sign)
rem ======================================================================================
setlocal EnableExtensions
cd /d "%~dp0"
title ApexTorrent release build

set "SKIPTESTS="
if /I "%~1"=="--skip-tests" set "SKIPTESTS=1"

echo.
echo === [1/7] Python and virtual environment ===
set "STAMP=MISSING - upload to GitHub may be incomplete"
if exist BUILD_STAMP.txt set /p STAMP=<BUILD_STAMP.txt
echo File set: %STAMP%
rem libtorrent only ships Windows wheels for Python 3.9-3.13, so never pick 3.14+. Order: APEX_PYTHON override,
rem then the py launcher (3.12, 3.13, 3.11, 3.10), then plain python.
set "PYEXE=%APEX_PYTHON%"
if defined PYEXE goto :havepy
for %%V in (3.12 3.13 3.11 3.10) do (
    if not defined PYEXE (
        py -%%V -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PYEXE=py -%%V"
    )
)
if defined PYEXE goto :havepy
where python >nul 2>nul
if not errorlevel 1 set "PYEXE=python"
:havepy
if not defined PYEXE goto :nopython
echo Using interpreter: %PYEXE%
%PYEXE% -c "import sys,struct; print(sys.version); print(struct.calcsize('P')*8, 'bit'); sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,13) and struct.calcsize('P')==8 else 1)"
if errorlevel 1 (
    echo ERROR: need 64-bit Python 3.10 to 3.13 - libtorrent has no wheels for other versions.. Set APEX_PYTHON to a suitable python.exe.
    goto :fail
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in .venv ...
    %PYEXE% -m venv .venv
    if errorlevel 1 goto :fail
)
call ".venv\Scripts\activate.bat"
if errorlevel 1 goto :fail
python -c "import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] <= (3, 13) else 1)"
if errorlevel 1 (
    echo ERROR: the existing .venv uses an unsupported Python. Delete the .venv folder and run again.
    goto :fail
)

echo.
echo === [2/7] Installing runtime and build dependencies ===
python -m pip install --upgrade pip
if errorlevel 1 goto :fail
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :pipfail
python -c "import libtorrent, PySide6, psutil, PIL, PyInstaller"
if errorlevel 1 goto :pipfail

echo.
echo === [3/7] Generating icons and installer artwork ===
python build_assets.py
if errorlevel 1 goto :fail

echo.
echo === [4/7] Running tests ===
if defined SKIPTESTS (
    echo Skipped by --skip-tests
) else (
    python tests\test_core.py
    if errorlevel 1 goto :fail
    python tests\test_packaging.py
    if errorlevel 1 goto :fail
)

echo.
echo === [5/7] Building the application with PyInstaller ===
if exist build rmdir /s /q build
if exist "dist\ApexTorrent" rmdir /s /q "dist\ApexTorrent"
python -m PyInstaller --noconfirm --clean apextorrent.spec
if errorlevel 1 goto :fail
if not exist "dist\ApexTorrent\ApexTorrent.exe" (
    echo ERROR: dist\ApexTorrent\ApexTorrent.exe was not produced.
    goto :fail
)

echo.
echo === [6/7] Self-test of the bundled application ===
set "SELFTEST=%TEMP%\apextorrent_selftest.txt"
if exist "%SELFTEST%" del /q "%SELFTEST%"
start "" /wait "dist\ApexTorrent\ApexTorrent.exe" --selftest "%SELFTEST%"
if not exist "%SELFTEST%" (
    echo ERROR: the bundled app did not write a self-test result. It crashed on startup.
    echo        Check %USERPROFILE%\.apextorrent\apextorrent.log
    goto :fail
)
type "%SELFTEST%"
echo.
findstr /B /C:"OK" "%SELFTEST%" >nul
if errorlevel 1 (
    echo ERROR: bundled app self-test failed.
    goto :fail
)

echo.
echo === [7/7] Building the installer with Inno Setup ===
set "ISCC="
where ISCC.exe >nul 2>nul
if not errorlevel 1 for /f "delims=" %%I in ('where ISCC.exe') do set "ISCC=%%I"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC goto :installinno
:haveiscc
echo Using: %ISCC%

set "APP_VERSION="
for /f "delims=" %%V in ('python -c "from version import APP_VERSION; print(APP_VERSION)"') do set "APP_VERSION=%%V"
if not defined APP_VERSION goto :fail

set "SIGNARGS="
if defined SIGNTOOL_CMD set SIGNARGS=/DSignTool=1 "/Sapexsign=%SIGNTOOL_CMD% $f"

if exist "dist\ApexTorrent_Setup.exe" del /q "dist\ApexTorrent_Setup.exe"
"%ISCC%" /Qp /DMyAppVersion=%APP_VERSION% %SIGNARGS% installer.iss
if errorlevel 1 goto :fail
if not exist "dist\ApexTorrent_Setup.exe" (
    echo ERROR: dist\ApexTorrent_Setup.exe was not produced.
    goto :fail
)

echo.
echo ======================================================================================
echo  SUCCESS: dist\ApexTorrent_Setup.exe  (version %APP_VERSION%)
certutil -hashfile "dist\ApexTorrent_Setup.exe" SHA256 | findstr /V "hash CertUtil"
echo ======================================================================================
goto :done

:installinno
where winget >nul 2>nul
if errorlevel 1 goto :noinno
echo Inno Setup not found. Installing it with winget ...
winget install -e --id JRSoftware.InnoSetup --silent --accept-source-agreements --accept-package-agreements
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if defined ISCC goto :haveiscc
:noinno
echo ERROR: Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php and run this script again.
echo        (The application itself was built: dist\ApexTorrent\ApexTorrent.exe)
goto :fail

:nopython
echo ERROR: Python was not found. Install 64-bit Python 3.10+ from https://www.python.org/downloads/
echo        and tick "Add python.exe to PATH".
goto :fail

:pipfail
echo.
echo ERROR: installing dependencies failed. If the message mentions libtorrent, your Python version has
echo        no libtorrent wheel yet: install Python 3.12 (64-bit, not 3.14), delete the .venv folder and retry.
goto :fail

:fail
echo.
echo BUILD FAILED.
if /I not "%CI%"=="1" if /I not "%CI%"=="true" pause
exit /b 1

:done
if /I not "%CI%"=="1" if /I not "%CI%"=="true" pause
exit /b 0
