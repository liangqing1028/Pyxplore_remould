@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -3.11 --version >nul 2>&1
if errorlevel 1 (
  echo 请先安装 Python 3.11 并保留 Python Launcher，再双击此文件。
  pause
  exit /b 1
)
py -3.11 -m venv .venv || goto failed
set "PYWPEM_PYTHON=%CD%\.venv\Scripts\python.exe"
"%PYWPEM_PYTHON%" -m pip install ".[full,dev]" || goto failed
if not exist outputs mkdir outputs
set QT_QPA_PLATFORM=offscreen
set MPLBACKEND=Agg
set TF_USE_LEGACY_KERAS=1
set TF_CPP_MIN_LOG_LEVEL=2
"%PYWPEM_PYTHON%" -m pytest -q --junitxml=outputs/source-tests.xml || goto failed
"%PYWPEM_PYTHON%" scripts/prepare_bundle.py || goto failed
"%PYWPEM_PYTHON%" -m PyInstaller --noconfirm packaging/desktop.spec || goto failed
"%PYWPEM_PYTHON%" scripts/check_bundle.py || goto failed
"%PYWPEM_PYTHON%" scripts/package_installers.py || goto failed
echo 构建验证完成。应用和安装包位于 dist，验证报告位于 outputs。
pause
exit /b 0
:failed
echo 构建未完成，请保留窗口中的错误信息。
pause
exit /b 1
