@echo off
echo ========================================
echo Gayathri Smart Speak V4 - Setup
echo ========================================
echo.

echo Step 1: Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.10 or higher from python.org
    pause
    exit /b 1
)
python --version
echo.

echo Step 2: Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)
echo.

echo Step 3: Checking configuration...
if not exist ".env" (
    echo ERROR: .env file not found!
    pause
    exit /b 1
)

findstr /C:"your_api_key_here" .env >nul
if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo IMPORTANT: Configure your API key!
    echo ========================================
    echo.
    echo Please edit the .env file and add your GROQ API key:
    echo 1. Open .env with Notepad
    echo 2. Replace "your_api_key_here" with your actual key
    echo 3. Save the file
    echo 4. Run this script again
    echo.
    echo Get your API key from: https://console.groq.com/
    echo.
    pause
    exit /b 0
)

echo.
echo ========================================
echo Setup Complete!
echo ========================================
echo.
echo To start the application, run: start.bat
echo Or manually run: python app.py
echo.
pause
