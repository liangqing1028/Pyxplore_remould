from PySide6.QtWidgets import QApplication

from wpem_desktop.catalog import OPERATIONS
from wpem_desktop.project import Project
from wpem_desktop.ui import MainWindow


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
        assert window.parameter_scroll.widget().width() <= window.parameter_scroll.viewport().width()
    window.close()


def test_ui_runs_real_worker_and_restores_result(qtbot, tmp_path):
    path = tmp_path / "spectrum.dat"
    path.write_text("x y\n10 1\n11 3\n12 2\n")
    project = Project.create(tmp_path / "科研项目" / "样品.wpem")
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_project(project)
    window.operation_combo.setCurrentIndex(window.operation_combo.findData("convert"))
    window.inputs["spectrum"].set_paths([path])
    with qtbot.waitSignal(window.runner.finished, timeout=60000) as signal:
        window.start_analysis()
    assert signal.args[0]["status"] == "success"
    run = window.runner.directory
    assert (run / "converted.csv").is_file()
    assert window.files.count() > 0
    reopened = Project.open(project.path)
    assert reopened.data["runs"][0]["status"] == "success"
    window.close()


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
