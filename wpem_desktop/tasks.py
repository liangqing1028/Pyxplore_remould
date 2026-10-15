"""A Qt process boundary keeps numerical work and cancellation outside the UI."""

from __future__ import annotations

import json
import codecs
import sys
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .project import timestamp, write_json


class TaskRunner(QObject):
    log = Signal(str)
    finished = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._error)
        self.directory = None
        self.cancelled = False
        self._reported = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._cancel_children = []
        self._generation = 0
        self._offset = 0
        self.timer = QTimer(self)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self._poll_log)

    @property
    def running(self):
        return self.process.state() != QProcess.NotRunning

    def start(self, directory):
        if self.running:
            raise RuntimeError("已有分析正在运行。")
        self.directory = Path(directory).resolve()
        self.cancelled = False
        self._reported = False
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._cancel_children = []
        self._generation += 1
        self._offset = 0
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("PYTHONUTF8", "1")
        environment.insert("MPLBACKEND", "Agg")
        environment.insert("TF_USE_LEGACY_KERAS", "1")
        environment.insert("TF_CPP_MIN_LOG_LEVEL", "2")
        environment.insert("OMP_NUM_THREADS", "1")
        environment.insert("OPENBLAS_NUM_THREADS", "1")
        environment.insert("MPLCONFIGDIR", str(self.directory / ".matplotlib"))
        self.process.setProcessEnvironment(environment)
        request = str(self.directory / "request.json")
        if getattr(sys, "frozen", False):
            arguments = ["--worker", request]
        else:
            arguments = ["-m", "wpem_desktop", "--worker", request]
            self.process.setWorkingDirectory(str(Path(__file__).resolve().parent.parent))
        self.timer.start()
        self.process.start(sys.executable, arguments)

    def _read(self):
        data = bytes(self.process.readAllStandardOutput())
        if data:
            with (self.directory / "run.log").open("ab") as stream:
                stream.write(data)
        self._poll_log()

    def _poll_log(self):
        if self.directory is None or not (self.directory / "run.log").is_file():
            return
        with (self.directory / "run.log").open("rb") as stream:
            stream.seek(self._offset)
            data = stream.read()
            self._offset = stream.tell()
        text = self._decoder.decode(data)
        if text:
            self.log.emit(text)

    def _error(self, error):
        if error == QProcess.FailedToStart:
            self._finish_result({"status": "failed", "error": "无法启动计算进程：" + self.process.errorString()})

    def _finish_result(self, result):
        if self._reported:
            return
        self._reported = True
        self.timer.stop()
        result.setdefault("finished_at", timestamp())
        write_json(self.directory / "result.json", result)
        self.finished.emit(result)

    def _finished(self, exit_code, exit_status):
        self._read()
        path = self.directory / "result.json"
        if self.cancelled:
            result = {"status": "cancelled", "warning": "已停止分析。已生成的文件保留，不能视为完整结果。"}
        elif path.is_file():
            try:
                result = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                result = {"status": "failed", "error": "计算进程未生成有效的结果记录，请查看运行日志。"}
        else:
            result = {"status": "failed", "error": f"计算进程意外退出（{exit_code}），请查看运行日志。"}
        self._finish_result(result)

    def cancel(self):
        if not self.running:
            return
        self.cancelled = True
        generation = self._generation
        try:
            descendants = psutil.Process(self.process.processId()).children(recursive=True)
        except psutil.Error:
            descendants = []
        self._cancel_children = descendants
        for child in reversed(descendants):
            try:
                child.terminate()
            except psutil.Error:
                pass
        self.process.terminate()

        def finish_cancel():
            for child in descendants:
                try:
                    if child.is_running():
                        child.kill()
                except psutil.Error:
                    pass
            if self._generation == generation and self.running:
                self.process.kill()

        QTimer.singleShot(800, self, finish_cancel)

    def shutdown(self):
        if self.running:
            self.cancel()
            if not self.process.waitForFinished(1000):
                self.process.kill()
                self.process.waitForFinished(1000)
            for child in self._cancel_children:
                try:
                    if child.is_running():
                        child.kill()
                except psutil.Error:
                    pass
