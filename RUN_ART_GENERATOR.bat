@echo off
echo ============================================================
echo   WILDFOLD - Art Generator Setup
echo ============================================================
echo.

:: Set your ComfyUI path
set COMFYUI_PATH=C:\Users\Mati\Downloads\AI\ComfyUI\ComfyUI
set MODELS_PATH=%COMFYUI_PATH%\models\checkpoints

:: Check if ComfyUI exists
if not exist "%COMFYUI_PATH%" (
    echo ERROR: ComfyUI not found at %COMFYUI_PATH%
    echo Edit this file and set COMFYUI_PATH to your ComfyUI location.
    pause
    exit /b 1
)

:: Check if any SDXL model exists
echo Checking for SDXL models in %MODELS_PATH%...
dir /b "%MODELS_PATH%\*.safetensors" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo No checkpoint models found!
    echo.
    echo Downloading RealVisXL V4.0 (6.5 GB - best free realistic model)...
    echo This will take 10-30 minutes depending on your internet speed.
    echo.
    
    :: Create models directory if needed
    if not exist "%MODELS_PATH%" mkdir "%MODELS_PATH%"
    
    :: Download using Python (more reliable than curl on Windows)
    python -c "import urllib.request; print('Starting download...'); urllib.request.urlretrieve('https://huggingface.co/SG161222/RealVisXL_V4.0/resolve/main/RealVisXL_V4.0.safetensors', r'%MODELS_PATH%\RealVisXL_V4.0.safetensors', lambda b,bs,ts: print(f'\r  {b*bs/1024/1024:.0f} MB / {ts/1024/1024:.0f} MB', end=''))"
    
    if %errorlevel% neq 0 (
        echo.
        echo Download failed. Please manually download an SDXL model:
        echo   1. Go to: https://huggingface.co/SG161222/RealVisXL_V4.0
        echo   2. Download RealVisXL_V4.0.safetensors
        echo   3. Put it in: %MODELS_PATH%
        echo.
        pause
        exit /b 1
    )
    echo.
    echo Download complete!
) else (
    echo Found models:
    dir /b "%MODELS_PATH%\*.safetensors"
)

:: Install Python dependencies
echo.
echo Installing Python dependencies...
pip install websocket-client Pillow requests 2>nul

:: Check if ComfyUI is running
echo.
echo Checking if ComfyUI is running...
python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/system_stats')" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo ComfyUI is NOT running. Starting it now...
    echo.
    start "ComfyUI" cmd /c "cd /d %COMFYUI_PATH% && python main.py --listen 0.0.0.0"
    echo Waiting 30 seconds for ComfyUI to start...
    timeout /t 30 /nobreak
    
    :: Check again
    python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8188/system_stats')" 2>nul
    if %errorlevel% neq 0 (
        echo.
        echo ComfyUI still not ready. Waiting another 30 seconds...
        timeout /t 30 /nobreak
    )
) else (
    echo ComfyUI is running!
)

:: Run the generator
echo.
echo ============================================================
echo   Starting art generation...
echo   This will take 3-6 hours. Go to sleep!
echo ============================================================
echo.
python generate_all_art.py

echo.
echo ============================================================
echo   DONE! Check the output folder for your art assets.
echo ============================================================
pause
