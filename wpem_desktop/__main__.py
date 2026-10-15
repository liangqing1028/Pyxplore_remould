from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import sys
from pathlib import Path


def main():
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="PyWPEM Desktop")
    parser.add_argument("--worker", metavar="REQUEST", help=argparse.SUPPRESS)
    parser.add_argument("--project", metavar="FILE", help="打开项目文件")
    parser.add_argument("--smoke-test", metavar="PNG", help=argparse.SUPPRESS)
    parser.add_argument("--smoke-html", metavar="HTML", help=argparse.SUPPRESS)
    options = parser.parse_args()
    if options.worker:
        os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
        # Windowed Windows bundles have no console streams; every worker owns its log.
        original_stdout, original_stderr = sys.stdout, sys.stderr
        with (Path(options.worker).resolve().parent / "run.log").open("a", encoding="utf-8", buffering=1) as stream:
            try:
                sys.stdout = sys.stderr = stream
                from .engine import run_request
                return run_request(options.worker)
            except Exception:
                import traceback
                traceback.print_exc(file=stream)
                return 1
            finally:
                sys.stdout, sys.stderr = original_stdout, original_stderr
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    application = QApplication(sys.argv[:1])
    application.setApplicationName("PyWPEM Desktop")
    application.setOrganizationName("PyWPEM Desktop")
    window = MainWindow()
    application.aboutToQuit.connect(window.close_web_view)
    application.aboutToQuit.connect(window.runner.shutdown)
    if options.project:
        window.open_project(options.project)
    window.show()
    if options.smoke_test:
        def capture():
            window.grab().save(options.smoke_test)
            application.quit()
        def capture_html(rendered):
            if not isinstance(rendered, bool):
                application.exit(2)
                return
            Path(options.smoke_test).with_suffix(".json").write_text(
                json.dumps({"webgl_rendered": rendered}), encoding="utf-8")
            capture()
        if options.smoke_html:
            window.show_html(Path(options.smoke_html).resolve())
            script = """Array.from(document.querySelectorAll('canvas')).some(canvas => {
                const gl = canvas.getContext('webgl2') || canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
                return !!gl && !gl.isContextLost() && canvas.width > 0 && canvas.height > 0;
            })"""
            window.web_view.loadFinished.connect(lambda success: QTimer.singleShot(
                1000, lambda: window.web_view.page().runJavaScript(script, capture_html)) if success else application.exit(2))
            QTimer.singleShot(30000, lambda: application.exit(2))
        else:
            QTimer.singleShot(1200, capture)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
