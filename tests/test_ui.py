import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog

from wpem_desktop.catalog import BY_KEY, OPERATIONS, parameters
from wpem_desktop.project import Project
from wpem_desktop.ui import MainWindow
from wpem_desktop.widgets import ParameterEditor


def test_start_creates_project_and_preserves_xrd_inputs(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    spectrum = tmp_path / "原始谱图.txt"
    spectrum.write_text("5 2\n20 5\n40 3\n", encoding="utf-8")
    cifs = [tmp_path / f"晶相-{index}.cif" for index in range(3)]
    for path in cifs:
        path.write_text("data_crystal\n", encoding="utf-8")
    window.inputs["spectrum"].set_paths([spectrum])
    window.inputs["cifs"].set_paths(cifs)
    window.editors["two_theta_range"].control.setText("5-40")
    window.editors["iter_max"].set_value(17)
    window.background_editors["lowAngleRange"].set_value(6)
    inputs, editors = window.inputs, window.editors
    project_path = tmp_path / "新项目" / "样品.wpem"
    dialogs, started, errors = [], [], []

    def choose_project(parent, title, *args):
        dialogs.append(title)
        return str(project_path), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose_project)
    monkeypatch.setattr(window.runner, "start", started.append)
    monkeypatch.setattr(window, "error", errors.append)
    assert window.run_button.isEnabled()
    qtbot.mouseClick(window.run_button, Qt.LeftButton)
    assert dialogs and "新建项目" in dialogs[0]
    assert not errors
    assert window.project.path == project_path
    assert window.inputs is inputs and window.editors is editors
    assert window.editors["two_theta_range"].control.text() == "5-40"
    assert window.inputs["cifs"].value() == [str(path) for path in cifs]
    assert len(started) == 1
    run = started[0]
    request = json.loads((run / "request.json").read_text(encoding="utf-8"))
    assert request["operation"] == "xrd"
    assert request["parameters"]["two_theta_range"] == [5, 40]
    assert request["parameters"]["iter_max"] == 17
    assert request["parameters"]["background"]["lowAngleRange"] == 6
    assert (run / request["inputs"]["spectrum"]).read_bytes() == spectrum.read_bytes()
    assert [(run / path).read_bytes() for path in request["inputs"]["cifs"]] == [path.read_bytes() for path in cifs]
    window.close()


def test_cancel_project_creation_keeps_unfinished_form(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    spectrum = tmp_path / "spectrum.dat"
    spectrum.write_text("5 2\n20 5\n40 3\n")
    window.inputs["spectrum"].set_paths([spectrum])
    window.editors["two_theta_range"].control.setText("5-")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    started = []
    monkeypatch.setattr(window.runner, "start", started.append)
    assert window.run_button.isEnabled()
    qtbot.mouseClick(window.run_button, Qt.LeftButton)
    assert window.project is None and not started
    assert window.inputs["spectrum"].value() == str(spectrum)
    assert window.editors["two_theta_range"].control.text() == "5-"
    assert window.run_button.isEnabled()
    window.close()


def test_toolbar_new_project_preserves_unfinished_parameters(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    window.editors["two_theta_range"].control.setText("5-")
    window.editors["iter_max"].set_value(17)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(tmp_path / "project.wpem"), ""))
    window.new_project()
    assert window.project is not None
    assert window.editors["two_theta_range"].control.text() == "5-"
    assert window.editors["iter_max"].value() == 17
    window.close()


@pytest.mark.parametrize("operation", ["xrd", "amorphous"])
@pytest.mark.parametrize("text, expected", [
    ("5-40", [5, 40]), (" 5.5 - 40.25 ", [5.5, 40.25]),
    ("-5--1", [-5, -1]), ("5e-1-4e1", [0.5, 40]),
    ("[5, 40]", [5, 40]), ("5,40", [5, 40]),
])
def test_angle_ranges_accept_hyphens_and_existing_formats(qtbot, operation, text, expected):
    field = next(field for field in parameters(BY_KEY[operation]) if field["key"] in {"two_theta_range", "ang_range"})
    editor = ParameterEditor(field)
    qtbot.addWidget(editor)
    editor.control.setText(text)
    assert editor.value() == expected


@pytest.mark.parametrize("text", ["5-40-60", "5-", "5-40deg", "5-1e999"])
def test_angle_ranges_reject_malformed_or_infinite_values(qtbot, text):
    field = next(field for field in parameters(BY_KEY["xrd"]) if field["key"] == "two_theta_range")
    editor = ParameterEditor(field)
    qtbot.addWidget(editor)
    editor.control.setText(text)
    with pytest.raises(ValueError):
        editor.value()


def test_hyphens_do_not_change_non_angle_parameters(qtbot):
    field = next(field for field in parameters(BY_KEY["xrd"]) if field["key"] == "wavelength")
    editor = ParameterEditor(field)
    qtbot.addWidget(editor)
    editor.control.setText("5-40")
    with pytest.raises(ValueError):
        editor.value()


def test_reversed_hyphen_angle_range_is_rejected_before_running(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.editors["two_theta_range"].control.setText("40-5")
    with pytest.raises(ValueError, match="起点"):
        window.collect_parameters()
    window.close()


def test_every_operation_has_usable_form(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_project(Project.create(tmp_path / "project.wpem"))
    window.show()
    for operation in OPERATIONS:
        window.nav.setCurrentRow(window.groups.index(operation.group))
        index = window.operation_combo.findData(operation.key)
        assert index >= 0
        window.operation_combo.setCurrentIndex(index)
        assert set(window.inputs) == {field.key for field in operation.inputs}
        if operation.key == "rdf":
            window.editors["density_zero"].set_value(0.05)
        if operation.key == "xrd_manual":
            window.editors["Lattice_constants"].set_value([[5.64, 5.64, 5.64, 90, 90, 90]])
        if operation.key == "substitution":
            window.editors["SolventAtom"].set_value("Mn3+")
            window.editors["SoluteAtom"].set_value("Ru2+")
        window.collect_parameters()
        QApplication.processEvents()
        assert window.parameter_scroll.widget().width() <= window.parameter_scroll.viewport().width(), operation.key
    window.close()


def test_ui_runs_real_worker_and_restores_result(qtbot, tmp_path, monkeypatch):
    path = tmp_path / "spectrum.dat"
    path.write_text("x y\n10 1\n11 3\n12 2\n")
    project_path = tmp_path / "科研项目" / "样品.wpem"
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(project_path), ""))
    window.operation_combo.setCurrentIndex(window.operation_combo.findData("convert"))
    window.inputs["spectrum"].set_paths([path])
    with qtbot.waitSignal(window.runner.finished, timeout=60000) as signal:
        qtbot.mouseClick(window.run_button, Qt.LeftButton)
    assert signal.args[0]["status"] == "success"
    run = window.runner.directory
    assert (run / "converted.csv").is_file()
    assert window.files.count() > 0
    reopened = Project.open(project_path)
    assert reopened.data["runs"][0]["status"] == "success"
    window.close()
    reopened.data["runs"][0]["status"] = "running"
    reopened.save()
    restored = MainWindow()
    qtbot.addWidget(restored)
    restored.set_project(reopened)
    assert reopened.data["runs"][0]["status"] == "success"
    restored.close()


def test_peak_editor_preserves_numeric_binding_energies(qtbot):
    from wpem_desktop.widgets import PeakEditor
    editor = PeakEditor([["CuII", "2p3/2", 933.7]])
    qtbot.addWidget(editor)
    assert editor.value()[0][2] == 933.7


def test_failed_worker_does_not_appear_as_success(qtbot, tmp_path):
    spectrum = tmp_path / "bad.csv"
    spectrum.write_text("1,2\n1,3\n1,4")
    project = Project.create(tmp_path / "project.wpem")
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_project(project)
    window.operation_combo.setCurrentIndex(window.operation_combo.findData("convert"))
    window.inputs["spectrum"].set_paths([spectrum])
    with qtbot.waitSignal(window.runner.finished, timeout=60000) as signal:
        window.start_analysis()
    assert signal.args[0]["status"] == "failed"
    assert "失败" in window.state_label.text()
    assert window.run_button.isEnabled()
    window.close()


def test_plotly_is_available_offline_in_desktop_view(qtbot, tmp_path):
    import json
    import subprocess
    import sys
    import plotly.graph_objects as go
    path = tmp_path / "offline.html"
    go.Figure(go.Scatter(x=[1, 2, 3], y=[2, 4, 3])).write_html(path, include_plotlyjs=True)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show_html(path)
    loaded = []
    with qtbot.waitSignal(window.web_view.loadFinished, timeout=30000) as load:
        window.show()
    assert load.args[0]
    window.web_view.page().runJavaScript("typeof Plotly", lambda value: loaded.append(value))
    qtbot.waitUntil(lambda: bool(loaded), timeout=10000)
    assert loaded[0] == "object"
    window.close()
    screenshot = tmp_path / "smoke.png"
    subprocess.run([sys.executable, "-m", "wpem_desktop", "--smoke-html", str(path),
                    "--smoke-test", str(screenshot)], timeout=60, check=True)
    assert screenshot.is_file()
    assert json.loads(screenshot.with_suffix(".json").read_text(encoding="utf-8")) == {"webgl_rendered": False}
