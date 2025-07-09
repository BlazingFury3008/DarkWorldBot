@echo off
setlocal

:: Set the name of the virtual environment folder
set VENV_DIR=venv

:: Step 1: Remove existing virtual environment
if exist "%VENV_DIR%\" (
    echo Removing existing virtual environment...
    rmdir /s /q "%VENV_DIR%"
)

:: Step 2: Create new virtual environment
echo Creating new virtual environment...
python -m venv "%VENV_DIR%"

:: Step 3: Activate virtual environment
call "%VENV_DIR%\Scripts\activate.bat"
python -m pip install --upgrade pip

:: Step 4: Install from requirements.txt if it exists
if exist "requirements.txt" (
    echo Installing dependencies from requirements.txt...
    pip install -r requirements.txt
) else (
    echo No requirements.txt found. Skipping dependency installation.
)

echo Setup complete.
endlocal
pause
