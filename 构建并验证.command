#!/bin/bash
set -e
cd "$(dirname "$0")"
trap 'echo "构建未完成，请保留窗口中的错误信息。"; read -r -p "按回车关闭…"' ERR
if ! command -v python3.11 >/dev/null; then
  echo "请先安装 Python 3.11，再双击此文件。"
  read -r -p "按回车关闭…"
  exit 1
fi
python3.11 -m venv .venv
.venv/bin/python -m pip install '.[full,dev]'
mkdir -p outputs
export QT_QPA_PLATFORM=offscreen
export MPLBACKEND=Agg
export TF_USE_LEGACY_KERAS=1
export TF_CPP_MIN_LOG_LEVEL=2
.venv/bin/python -m pytest -q --junitxml=outputs/source-tests.xml
.venv/bin/python scripts/prepare_bundle.py
.venv/bin/python -m PyInstaller --noconfirm packaging/desktop.spec
.venv/bin/python scripts/check_bundle.py
.venv/bin/python scripts/package_installers.py
echo "构建验证完成。应用和安装镜像位于 dist，验证报告位于 outputs。"
read -r -p "按回车关闭…"
