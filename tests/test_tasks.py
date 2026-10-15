import sys
import psutil

from wpem_desktop.tasks import TaskRunner


def test_log_handles_split_utf8_bytes(qtbot, tmp_path):
    runner = TaskRunner()
    runner.directory = tmp_path
    script = ("import sys,time; b='阶段：晶相预处理'.encode('utf-8'); "
              "sys.stdout.buffer.write(b[:1]);sys.stdout.buffer.flush();time.sleep(0.1);"
              "sys.stdout.buffer.write(b[1:]);sys.stdout.buffer.flush()")
    with qtbot.waitSignal(runner.finished, timeout=10000):
        runner.process.start(sys.executable, ["-c", script])
    assert (tmp_path / "run.log").read_text(encoding="utf-8") == "阶段：晶相预处理"


def test_cancel_stops_worker_and_records_incomplete_state(qtbot, tmp_path):
    runner = TaskRunner()
    runner.directory = tmp_path
    runner.process.start(sys.executable, ["-c", "import time;print('started',flush=True);time.sleep(60)"])
    qtbot.waitUntil(lambda: (tmp_path / "run.log").exists(), timeout=10000)
    with qtbot.waitSignal(runner.finished, timeout=10000) as result:
        runner.cancel()
    assert result.args[0]["status"] == "cancelled"
    assert not runner.running


def test_cancel_cleans_up_calculation_children(qtbot, tmp_path):
    runner = TaskRunner()
    runner.directory = tmp_path
    pid_file = tmp_path / "child.pid"
    script = ("import subprocess,sys,time,pathlib; "
              "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
              f"pathlib.Path({str(pid_file)!r}).write_text(str(p.pid));"
              "time.sleep(60)")
    runner.process.start(sys.executable, ["-c", script])
    qtbot.waitUntil(pid_file.exists, timeout=10000)
    child = psutil.Process(int(pid_file.read_text()))
    with qtbot.waitSignal(runner.finished, timeout=10000):
        runner.cancel()
    qtbot.waitUntil(lambda: not child.is_running() or child.status() == psutil.STATUS_ZOMBIE, timeout=5000)


def test_restart_after_cancel_is_not_killed_by_old_cleanup(qtbot, tmp_path):
    from wpem_desktop.project import Project
    runner = TaskRunner()
    runner.directory = tmp_path
    runner.process.start(sys.executable, ["-c", "import time;print('started',flush=True);time.sleep(60)"])
    qtbot.waitUntil(lambda: (tmp_path / "run.log").exists(), timeout=10000)
    with qtbot.waitSignal(runner.finished, timeout=10000):
        runner.cancel()
    source = tmp_path / "spectrum.csv"
    source.write_text("10,4\n11,5\n12,6\n")
    project = Project.create(tmp_path / "restarted" / "project.wpem")
    run = project.create_run("convert", {}, {"spectrum": source})
    with qtbot.waitSignal(runner.finished, timeout=60000) as result:
        runner.start(run)
    assert result.args[0]["status"] == "success", result.args[0]
    assert (run / "converted.csv").is_file()
