"""The local scientific workbench; numerical execution lives in a child process."""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtCore import Qt, QCoreApplication, QEvent, QLockFile, QSettings, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFont, QKeySequence, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFileDialog, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextBrowser, QToolBar, QVBoxLayout,
    QWidget,
)

from . import __version__
from .catalog import BY_KEY, OPERATIONS, parameters
from .data import load_array, read_spectrum
from .engine import validate_parameters
from .project import Project
from .tasks import TaskRunner
from .widgets import FilePicker, ParameterEditor, PlotView


STATUS = {"queued": "待运行", "running": "运行中", "success": "已完成", "warning": "需检查",
          "failed": "失败", "cancelled": "已停止"}
STYLE = """
QMainWindow, QWidget#workspace { background: #f4f6f9; color: #233249; }
QWidget { font-size: 13px; }
QFrame#sidebar { background: #eaf0f7; border-right: 1px solid #d7e0eb; }
QLabel#brand { font-size: 21px; font-weight: 700; color: #163e6b; }
QLabel#eyebrow { color: #73829a; font-size: 11px; font-weight: 600; }
QLabel#heading { font-size: 23px; font-weight: 600; color: #203c5d; }
QLabel#description { color: #64748b; line-height: 1.5; }
QLabel#fileLabel { color: #42607e; font-size: 12px; }
QFrame#parameters { background: white; border-left: 1px solid #dfe5ed; }
QWidget#parameterContent { background: white; }
QPushButton { border: 1px solid #d5deea; background: white; border-radius: 5px; padding: 7px 12px; color: #334d6a; }
QPushButton:hover { background: #edf4fd; border-color: #9eb9dc; }
QPushButton:disabled { color: #9aa8b9; background: #f0f3f7; }
QPushButton#primary { color: white; background: #2563a5; border: 1px solid #2563a5; font-weight: 600; padding: 10px; }
QPushButton#primary:hover { background: #1b528c; }
QPushButton#primary:disabled { background: #96b0cc; border-color: #96b0cc; }
QLineEdit, QComboBox { background: white; border: 1px solid #d7e0eb; border-radius: 4px; padding: 6px; min-height: 21px; }
QLineEdit:focus, QComboBox:focus { border-color: #528bc8; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 8px 9px; border-radius: 5px; }
QListWidget::item:selected { background: #d6e5f7; color: #174f89; }
QGroupBox { font-weight: 600; border: 1px solid #e1e7ef; border-radius: 6px; margin-top: 15px; padding: 14px 9px 9px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #5f7187; }
QTabWidget::pane { background: white; border: 1px solid #e0e6ee; border-radius: 5px; }
QTabBar::tab { padding: 10px 18px; background: transparent; color: #738197; }
QTabBar::tab:selected { color: #205e9b; border-bottom: 2px solid #2563a5; }
QTextBrowser, QPlainTextEdit, QTableWidget { background: white; border: none; }
QToolBar { background: #fff; border-bottom: 1px solid #dfe5ed; padding: 6px 10px; spacing: 10px; }
QStatusBar { background: #edf2f7; color: #687d92; }
QProgressBar { border: none; background: #dce5f0; border-radius: 3px; max-height: 5px; }
QProgressBar::chunk { background: #4282bd; }
QScrollArea { border: none; background: transparent; }
QSplitter::handle { background: #e0e6ee; width: 1px; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = None
        self._project_lock = None
        self.current_directory = None
        self.inputs = {}
        self.editors = {}
        self.settings = QSettings()
        self.runner = TaskRunner(self)
        self.runner.log.connect(self.append_log)
        self.runner.finished.connect(self.analysis_finished)
        self.setWindowTitle("PyWPEM Desktop · 科研分析工作台")
        self.resize(1460, 920)
        self.setMinimumSize(1120, 760)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        self._toolbar()
        self._layout()
        self.nav.setCurrentRow(0)
        self.statusBar().showMessage("本地计算 · 数据保存在项目目录 · 新建或打开项目以开始")

    def _toolbar(self):
        toolbar = QToolBar("项目")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        for label, shortcut, slot in (("新建项目", QKeySequence.New, self.new_project),
                                      ("打开项目", QKeySequence.Open, self.choose_project),
                                      ("保存项目", QKeySequence.Save, self.save_project)):
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            toolbar.addAction(action)
        toolbar.addSeparator()
        example = QAction("打开示例", self)
        example.triggered.connect(self.open_example)
        toolbar.addAction(example)
        recent_menu = self.menuBar().addMenu("最近项目")
        for value in self.settings.value("recent_projects", []) or []:
            action = recent_menu.addAction(Path(value).stem)
            action.setToolTip(value)
            action.triggered.connect(lambda checked=False, path=value: self.open_project(path))
        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction("使用说明", self.show_help)
        help_menu.addAction("关于与引用", self.show_about)

    def _layout(self):
        root = QWidget()
        root.setObjectName("workspace")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(16, 24, 14, 14)
        brand = QLabel("◉  PyWPEM")
        brand.setObjectName("brand")
        left.addWidget(brand)
        caption = QLabel("DESKTOP  /  科研分析")
        caption.setObjectName("eyebrow")
        left.addWidget(caption)
        left.addSpacing(20)
        self.project_label = QLabel("尚未打开项目")
        self.project_label.setWordWrap(True)
        self.project_label.setTextFormat(Qt.PlainText)
        left.addWidget(self.project_label)
        left.addSpacing(18)
        self.nav = QListWidget()
        self.groups = list(dict.fromkeys(op.group for op in OPERATIONS))
        self.nav.addItems(self.groups)
        self.nav.setFixedHeight(236)
        self.nav.currentRowChanged.connect(self.change_group)
        left.addWidget(self.nav)
        left.addSpacing(12)
        left.addWidget(QLabel("项目文件"))
        self.assets = QListWidget()
        self.assets.setMinimumHeight(80)
        self.assets.itemDoubleClicked.connect(self.preview_asset)
        left.addWidget(self.assets, 1)
        import_button = QPushButton("＋ 导入文件")
        import_button.clicked.connect(self.import_files)
        left.addWidget(import_button)
        left.addSpacing(14)
        left.addWidget(QLabel("分析记录"))
        self.history = QListWidget()
        self.history.setMinimumHeight(95)
        self.history.itemClicked.connect(self.select_history)
        left.addWidget(self.history, 1)
        footer = QLabel("LOCAL SCIENCE WORKBENCH\nPyWPEM engine · Bin Cao")
        footer.setObjectName("eyebrow")
        left.addWidget(footer)
        layout.addWidget(sidebar)
        center = QWidget()
        main = QVBoxLayout(center)
        main.setContentsMargins(22, 23, 22, 14)
        main.setSpacing(12)
        top = QHBoxLayout()
        self.heading = QLabel("XRD")
        self.heading.setObjectName("heading")
        top.addWidget(self.heading)
        top.addStretch()
        self.state_label = QLabel("● 就绪")
        self.state_label.setStyleSheet("color: #438477; font-weight: 600;")
        top.addWidget(self.state_label)
        main.addLayout(top)
        self.operation_combo = QComboBox()
        self.operation_combo.currentIndexChanged.connect(self.change_operation)
        main.addWidget(self.operation_combo)
        self.description = QLabel()
        self.description.setObjectName("description")
        self.description.setWordWrap(True)
        main.addWidget(self.description)
        self.tabs = QTabWidget()
        self.plot = PlotView()
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.summary = QTextBrowser()
        self.summary.setOpenExternalLinks(False)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(10000)
        self.log.setFont(QFont("Menlo", 11))
        self.files = QListWidget()
        self.files.itemDoubleClicked.connect(self.open_artifact)
        self.tabs.addTab(self.plot, "谱图")
        self.tabs.addTab(self.table, "数据")
        self.tabs.addTab(self.summary, "分析摘要")
        self.tabs.addTab(self.log, "运行日志")
        self.tabs.addTab(self.files, "结果文件")
        main.addWidget(self.tabs, 1)
        actions = QHBoxLayout()
        curve_export = QPushButton("导出当前图…")
        curve_export.clicked.connect(self.export_plot)
        file_export = QPushButton("导出所选文件…")
        file_export.clicked.connect(self.export_artifact)
        bundle_export = QPushButton("导出完整分析…")
        bundle_export.clicked.connect(self.export_bundle)
        folder = QPushButton("打开结果目录")
        folder.clicked.connect(self.open_directory)
        reuse = QPushButton("复用参数")
        reuse.clicked.connect(self.reuse_parameters)
        for button in (curve_export, file_export, bundle_export, folder, reuse):
            actions.addWidget(button)
        actions.addStretch()
        main.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setTextVisible(False)
        main.addWidget(self.progress)
        splitter = QSplitter()
        splitter.addWidget(center)
        self.parameter_panel = QFrame()
        self.parameter_panel.setObjectName("parameters")
        self.parameter_panel.setMinimumWidth(310)
        self.parameter_panel.setMaximumWidth(430)
        right = QVBoxLayout(self.parameter_panel)
        right.setContentsMargins(16, 24, 16, 14)
        right.addWidget(QLabel("分析设置"))
        self.parameter_scroll = QScrollArea()
        self.parameter_scroll.setWidgetResizable(True)
        self.parameter_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right.addWidget(self.parameter_scroll, 1)
        self.run_button = QPushButton("开始分析")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.start_analysis)
        self.run_button.setEnabled(False)
        self.cancel_button = QPushButton("停止计算")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.runner.cancel)
        right.addWidget(self.run_button)
        right.addWidget(self.cancel_button)
        note = QLabel("每次运行独立保存输入、参数和结果。\n原始数据保持完整。")
        note.setObjectName("description")
        right.addWidget(note)
        splitter.addWidget(self.parameter_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setSizes([920, 340])
        layout.addWidget(splitter, 1)
        self.summary.setHtml("<h2>从一份谱图开始</h2><p>新建项目，选择实验数据与晶体结构，然后配置分析。</p>"
                             "<p>支持 XRD、非晶分析、XPS、EXAFS 与晶体图。所有计算在本机执行。</p>")

    @property
    def operation(self):
        return BY_KEY[self.operation_combo.currentData()]

    def change_group(self, row):
        if row < 0:
            return
        self.operation_combo.blockSignals(True)
        self.operation_combo.clear()
        self.heading.setText(self.groups[row])
        for operation in OPERATIONS:
            if operation.group == self.groups[row]:
                self.operation_combo.addItem(operation.label, operation.key)
        self.operation_combo.blockSignals(False)
        self.change_operation()

    def change_operation(self, *args):
        if self.operation_combo.currentIndex() < 0:
            return
        operation = self.operation
        self.description.setText(operation.description)
        content = QWidget()
        content.setObjectName("parameterContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 6, 0, 0)
        self.inputs, self.editors = {}, {}
        if operation.inputs:
            group = QGroupBox("输入数据")
            form = QVBoxLayout(group)
            for specification in operation.inputs:
                label = QLabel(specification.label)
                form.addWidget(label)
                picker = FilePicker(specification.kind, specification.multiple)
                picker.button.setAccessibleName("选择" + specification.label)
                picker.changed.connect(lambda key=specification.key: self.preview_input(key))
                self.inputs[specification.key] = picker
                form.addWidget(picker)
            layout.addWidget(group)
        self.context_combo = None
        if operation.context:
            group = QGroupBox("前次分析结果（可选）")
            form = QVBoxLayout(group)
            self.context_combo = QComboBox()
            self.context_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.context_combo.setMinimumContentsLength(12)
            self.refresh_context()
            form.addWidget(self.context_combo)
            note = QLabel("用于组分绘图、峰参数复用或继续分析。")
            note.setWordWrap(True)
            note.setObjectName("description")
            form.addWidget(note)
            layout.addWidget(group)
        fields = parameters(operation)
        for title, common in (("常用参数", True), ("高级参数", False)):
            selected = [field for field in fields if field["common"] == common]
            if not selected:
                continue
            group = QGroupBox(title)
            body = QWidget()
            outer = QVBoxLayout(group)
            outer.addWidget(body)
            if not common:
                group.setTitle("展开高级参数")
                group.setCheckable(True)
                group.setChecked(False)
                body.setVisible(False)
                group.toggled.connect(body.setVisible)
                group.setToolTip("折叠仅影响显示，参数仍按当前值使用。")
            form = QFormLayout(body)
            form.setRowWrapPolicy(QFormLayout.WrapAllRows)
            form.setVerticalSpacing(11)
            for field in selected:
                editor = ParameterEditor(field)
                self.editors[field["key"]] = editor
                label = QLabel(field["label"])
                label.setToolTip(field["key"])
                form.addRow(label, editor)
            layout.addWidget(group)
        self.background_editors = {}
        if operation.key in {"xrd", "xrd_manual", "xps"}:
            group = QGroupBox("展开背景处理参数")
            group.setCheckable(True)
            group.setChecked(False)
            body = QWidget()
            outer = QVBoxLayout(group)
            outer.addWidget(body)
            body.setVisible(False)
            group.toggled.connect(body.setVisible)
            form = QFormLayout(body)
            form.setRowWrapPolicy(QFormLayout.WrapAllRows)
            for field in parameters(BY_KEY["background"]):
                if field["key"] == "Model":
                    continue
                editor = ParameterEditor(field)
                self.background_editors[field["key"]] = editor
                form.addRow(field["label"], editor)
            layout.addWidget(group)
        layout.addStretch()
        self.parameter_scroll.setWidget(content)
        if self.project:
            draft = self.project.data.get("drafts", {}).get(operation.key)
            if draft:
                self.restore_values(draft)

    def refresh_context(self):
        if self.context_combo is None:
            return
        self.context_combo.clear()
        self.context_combo.addItem("不复用前次结果", None)
        if self.project:
            for run in reversed(self.project.data["runs"]):
                if run["status"] in {"success", "warning"}:
                    operation = BY_KEY.get(run["operation"])
                    self.context_combo.addItem(f"{operation.label if operation else run['operation']} · {run['id']}", run["path"])

    def collect_parameters(self):
        result = {}
        for key, editor in self.editors.items():
            value = editor.value()
            if value is not None:
                result[key] = value
        if self.background_editors:
            result["background"] = {key: editor.value() for key, editor in self.background_editors.items()
                                    if editor.value() is not None}
        validate_parameters(self.operation, result)
        return result

    def restore_values(self, draft):
        for key, value in draft.get("parameters", {}).items():
            if key == "background":
                for background_key, background_value in value.items():
                    if background_key in self.background_editors:
                        self.background_editors[background_key].set_value(background_value)
            elif key in self.editors:
                self.editors[key].set_value(value)
        if self.project:
            for key, paths in draft.get("inputs", {}).items():
                if key in self.inputs:
                    names = {asset["path"]: asset["name"] for asset in self.project.data["assets"]}
                    self.inputs[key].set_paths([self.project.resolve(path) for path in paths],
                                               [names.get(path, Path(path).name) for path in paths])

    def error(self, message):
        QMessageBox.warning(self, "暂时无法完成", str(message))

    def ensure_idle(self):
        if self.runner.running:
            self.error("请等待当前分析完成，或先停止计算。")
            return False
        return True

    def new_project(self):
        if not self.ensure_idle():
            return
        path, _ = QFileDialog.getSaveFileName(self, "新建项目：请选择独立目录保存", str(Path.home() / "Documents" / "新分析" / "新分析.wpem"),
                                             "PyWPEM 项目 (*.wpem)")
        if path:
            try:
                self.set_project(Project.create(path))
            except Exception as error:
                self.error(error)

    def choose_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开项目", "", "PyWPEM 项目 (*.wpem *.wpem.json)")
        if path:
            self.open_project(path)

    def open_project(self, path):
        if not self.ensure_idle():
            return
        try:
            self.set_project(Project.open(path))
        except Exception as error:
            self.error(error)

    def set_project(self, project):
        if self.project and project.path == self.project.path:
            return
        lock = QLockFile(str(project.path) + ".lock")
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            raise RuntimeError("该项目正在另一个窗口中使用，请先关闭那个窗口。")
        if self.project:
            self.save_project(silent=True)
        if self._project_lock:
            self._project_lock.unlock()
        self._project_lock = lock
        self.project = project
        self.run_button.setEnabled(True)
        self.current_directory = None
        self.files.clear()
        self.log.clear()
        for run in project.data["runs"]:
            if run["status"] in {"running", "queued"}:
                result_path = project.resolve(run["path"]) / "result.json"
                if result_path.is_file():
                    run["status"] = json.loads(result_path.read_text())["status"]
                else:
                    run["status"] = "cancelled"
        project.save()
        self.project_label.setText(project.data["name"])
        self.setWindowTitle(f"{project.data['name']} · PyWPEM Desktop")
        recent = self.settings.value("recent_projects", []) or []
        recent = [str(project.path)] + [path for path in recent if path != str(project.path)]
        self.settings.setValue("recent_projects", recent[:8])
        self.refresh_lists()
        self.change_operation()
        last = self.project.data.get("last_operation")
        if last in BY_KEY:
            self.nav.setCurrentRow(self.groups.index(BY_KEY[last].group))
            self.operation_combo.setCurrentIndex(self.operation_combo.findData(last))
        if self.project.data["runs"]:
            self.show_run(self.project.resolve(self.project.data["runs"][-1]["path"]))
        self.statusBar().showMessage(str(project.path))

    def save_project(self, silent=False):
        if not self.project:
            self.new_project()
            return
        try:
            parameters_value = self.collect_parameters()
            assets = {}
            for key, picker in self.inputs.items():
                assets[key] = [self.project.import_file(path)["path"] for path in picker.paths]
            self.project.data.setdefault("drafts", {})[self.operation.key] = {"parameters": parameters_value, "inputs": assets}
            self.project.data["last_operation"] = self.operation.key
            self.project.save()
            self.refresh_lists()
            self.statusBar().showMessage("项目与当前参数已保存。", 5000)
            return True
        except Exception as error:
            if not silent:
                self.error(error)
            return False

    def refresh_lists(self):
        self.assets.clear()
        self.history.clear()
        if not self.project:
            return
        for asset in self.project.data["assets"]:
            item = QListWidgetItem(asset["name"])
            item.setData(Qt.UserRole, asset["path"])
            item.setToolTip(asset["sha256"])
            self.assets.addItem(item)
        for run in reversed(self.project.data["runs"]):
            operation = BY_KEY.get(run["operation"])
            item = QListWidgetItem(f"{STATUS.get(run['status'], run['status'])} · {operation.label if operation else run['operation']}\n{run['id']}")
            item.setData(Qt.UserRole, run["path"])
            self.history.addItem(item)
        self.refresh_context()

    def import_files(self):
        if not self.project:
            self.new_project()
        if not self.project:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "导入实验数据和晶体结构", "", "科研数据 (*.csv *.dat *.txt *.xy *.xrdml *.cif *.npy *.npz *.json);;所有文件 (*)")
        self.add_files(paths)

    def add_files(self, paths):
        try:
            for path in paths:
                self.project.import_file(path)
            self.refresh_lists()
            for key, picker in self.inputs.items():
                matches = [path for path in paths if (Path(path).suffix.lower() == ".cif") == (picker.kind == "cif")]
                if matches:
                    picker.set_paths(matches if picker.multiple else matches[:1])
        except Exception as error:
            self.error(error)

    def preview_input(self, key):
        if key not in self.inputs or not self.inputs[key].paths:
            return
        path = Path(self.inputs[key].paths[0])
        if self.inputs[key].kind == "spectrum":
            try:
                frame = read_spectrum(path)
                self.plot.set_curves([{"label": "Observed", "x": frame.x, "y": frame.intensity}],
                                     xlabel="Binding energy (eV)" if self.operation.key == "xps" else ("Energy (eV)" if self.operation.key == "exafs" else "2θ (°)"),
                                     invert_x=self.operation.key == "xps")
                self.show_table(frame)
                self.tabs.setCurrentIndex(0)
                self.statusBar().showMessage(f"已预览 {len(frame):,} 个数据点 · {path.name}")
            except Exception as error:
                self.statusBar().showMessage("预览失败：" + str(error))

    def preview_asset(self, item):
        if self.project:
            self.preview_file(self.project.resolve(item.data(Qt.UserRole)))

    def show_table(self, frame):
        frame = frame.iloc[:2000, :100]
        self.table.clear()
        self.table.setRowCount(len(frame))
        self.table.setColumnCount(len(frame.columns))
        self.table.setHorizontalHeaderLabels([str(value) for value in frame.columns])
        self.table.setUpdatesEnabled(False)
        for row, values in enumerate(frame.itertuples(index=False, name=None)):
            for col, value in enumerate(values):
                self.table.setItem(row, col, QTableWidgetItem(f"{value:.8g}" if isinstance(value, float) else str(value)))
        self.table.setUpdatesEnabled(True)
        self.table.resizeColumnsToContents()
        self.table.setToolTip("预览最多 2000 行、100 列；结果文件保留全部数据。")

    def start_analysis(self):
        if not self.ensure_idle():
            return
        if not self.project:
            self.new_project()
            if not self.project:
                return
        try:
            params = self.collect_parameters()
            inputs = {}
            for key, picker in self.inputs.items():
                value = picker.value()
                if not value:
                    raise ValueError("请选择所有必需的输入文件。")
                inputs[key] = value
            for key, editor in self.editors.items():
                if isinstance(editor.control, FilePicker) and editor.control.value():
                    inputs["parameter_" + key] = params.pop(key)
            context = None
            if self.context_combo is not None and self.context_combo.currentData():
                context = self.project.resolve(self.context_combo.currentData())
            if self.operation.key == "components" and not context:
                raise ValueError("组分绘图需要选择一个已完成的 XRD 分析。")
            if params.get("loadParams") and context is None:
                raise ValueError("复用峰参数需要选择前次分析结果。")
            directory = self.project.create_run(self.operation.key, params, inputs,
                                                 seed=int(params.get("seed", 42)), context=context)
            self.current_directory = directory
            self.project.update_run(directory, "running")
            self.log.clear()
            self.summary.clear()
            self.files.clear()
            self.set_running(True)
            self.refresh_lists()
            self.runner.start(directory)
        except Exception as error:
            self.error(error)

    def set_running(self, running):
        self.run_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.nav.setEnabled(not running)
        self.operation_combo.setEnabled(not running)
        self.parameter_scroll.setEnabled(not running)
        self.progress.setRange(0, 0 if running else 1)
        self.state_label.setText("● 计算中" if running else "● 就绪")
        self.state_label.setStyleSheet("color: #2d6cb1; font-weight: 600;" if running else "color: #438477; font-weight: 600;")

    def append_log(self, text):
        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.log.setTextCursor(cursor)
        for line in text.replace("\r", "\n").splitlines():
            if line.startswith("阶段："):
                self.statusBar().showMessage(line)

    def analysis_finished(self, result):
        self.set_running(False)
        self.project.update_run(self.runner.directory, result["status"])
        self.current_directory = self.runner.directory
        self.refresh_lists()
        self.show_run(self.current_directory)
        state = STATUS.get(result["status"], result["status"])
        self.statusBar().showMessage(f"{state} · {result.get('elapsed_seconds', 0):.1f} 秒")
        QApplication.alert(self, 1500)

    def select_history(self, item):
        if self.project:
            self.show_run(self.project.resolve(item.data(Qt.UserRole)))

    def show_run(self, directory):
        self.current_directory = Path(directory)
        result_path = self.current_directory / "result.json"
        if not result_path.is_file():
            return
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            caption = "● " + STATUS.get(result["status"], result["status"])
            if isinstance(result.get("metrics", {}).get("Rwp"), (int, float)):
                caption += f"  ·  Rwp {result['metrics']['Rwp']:.2f}%"
            self.state_label.setText(caption)
            self.state_label.setStyleSheet("color: #b3792b; font-weight: 600;" if result["status"] == "warning"
                                           else "color: #a74943; font-weight: 600;" if result["status"] in {"failed", "cancelled"}
                                           else "color: #438477; font-weight: 600;")
            pieces = [f"<h2>{html.escape(STATUS.get(result['status'], result['status']))}</h2>"]
            for key in ("warning", "error"):
                if result.get(key):
                    pieces.append(f"<p style='color:#a65e2b'>{html.escape(str(result[key]))}</p>")
            if result.get("metrics"):
                pieces.append("<h3>拟合诊断</h3><pre>" + html.escape(json.dumps(result["metrics"], ensure_ascii=False, indent=2)) + "</pre>")
            pieces.append("<h3>分析结果</h3><pre>" + html.escape(json.dumps(result.get("summary", {}), ensure_ascii=False, indent=2)) + "</pre>")
            pieces.append(f"<p>耗时 {result.get('elapsed_seconds', 0):.2f} 秒 · 内核版本 {html.escape(result.get('engine_commit', '')[:12])}</p>")
            self.summary.setHtml("".join(pieces))
            log = self.current_directory / "run.log"
            if log.is_file():
                self.log.setPlainText(log.read_text(encoding="utf-8", errors="replace")[-500000:])
            self.files.clear()
            artifacts = result.get("artifacts") or [str(path.relative_to(self.current_directory)) for path in self.current_directory.rglob("*")
                                                    if path.is_file() and "inputs" not in path.relative_to(self.current_directory).parts
                                                    and "context" not in path.relative_to(self.current_directory).parts]
            for relative in artifacts:
                path = (self.current_directory / relative).resolve()
                if not path.is_relative_to(self.current_directory) or not path.is_file():
                    continue
                item = QListWidgetItem(relative)
                item.setData(Qt.UserRole, str(path))
                self.files.addItem(item)
            curves = sorted((self.current_directory / "figures").glob("*.curves.json"))
            if curves:
                fitting = [path for path in curves if "WPEM fitting profile" in path.read_text(encoding="utf-8")]
                self.preview_file(fitting[-1] if fitting else curves[-1])
            elif result["status"] in {"failed", "cancelled", "warning"}:
                self.tabs.setCurrentIndex(2)
        except Exception as error:
            self.error(error)

    def open_artifact(self, item):
        self.preview_file(Path(item.data(Qt.UserRole)))

    def preview_file(self, path):
        try:
            if path.name.endswith(".curves.json"):
                axes = json.loads(path.read_text(encoding="utf-8"))
                axis = axes[0]
                self.plot.set_curves(axis["curves"], axis["xlabel"], axis["ylabel"], axis["title"], axis["invert_x"])
                self.tabs.setCurrentIndex(0)
            elif path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                self.plot.show_image(path)
                self.tabs.setCurrentIndex(0)
            elif path.suffix.lower() == ".html":
                self.show_html(path)
            elif path.suffix.lower() in {".csv", ".txt", ".dat", ".xy", ".xrdml"}:
                if path.suffix.lower() == ".csv":
                    header = pd.read_csv(path, nrows=0)
                    if {"x_simu", "y_simu"}.issubset(header.columns):
                        frame = pd.read_csv(path)
                        self.plot.set_curves([{"label": "Simulation", "x": frame.x_simu, "y": frame.y_simu}])
                        self.show_table(frame)
                        self.tabs.setCurrentIndex(0)
                        return
                    if len(header.columns) > 2:
                        self.show_table(pd.read_csv(path))
                        self.tabs.setCurrentIndex(1)
                        return
                try:
                    frame = read_spectrum(path)
                    self.plot.set_curves([{"label": path.stem, "x": frame.x, "y": frame.intensity}])
                    self.show_table(frame)
                    self.tabs.setCurrentIndex(0)
                except (ValueError, UnicodeError):
                    frame = pd.read_csv(path)
                    self.show_table(frame)
                    self.tabs.setCurrentIndex(1)
            elif path.suffix.lower() in {".npy", ".npz"}:
                value = load_array(path)
                if value.ndim > 2:
                    raise ValueError(f"数组形状为 {value.shape}，请导出后在对应分析软件中使用。")
                self.show_table(pd.DataFrame(np.atleast_2d(value)))
                self.tabs.setCurrentIndex(1)
            elif path.suffix.lower() in {".cif", ".json", ".svg", ".path"}:
                text = path.read_text(encoding="utf-8")
                self.summary.setPlainText(text[:500000])
                self.tabs.setCurrentIndex(2)
            else:
                self.statusBar().showMessage("该文件可通过“导出所选文件”保存。外部 pickle 文件不会被加载。")
        except Exception as error:
            self.error(error)

    def show_html(self, path):
        from PySide6.QtWebEngineCore import QWebEngineSettings
        from PySide6.QtWebEngineWidgets import QWebEngineView
        if not hasattr(self, "web_view"):
            self.web_view = QWebEngineView()
            self.web_view.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
            self.web_view.settings().setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
            self.tabs.addTab(self.web_view, "交互图")
        self.web_view.setUrl(QUrl.fromLocalFile(str(path)))
        self.tabs.setCurrentWidget(self.web_view)

    def close_web_view(self):
        if hasattr(self, "web_view"):
            self.web_view.stop()
            self.tabs.removeTab(self.tabs.indexOf(self.web_view))
            self.web_view.deleteLater()
            del self.web_view
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def export_plot(self):
        path, selected = QFileDialog.getSaveFileName(self, "导出当前谱图", "spectrum.svg", "SVG 矢量图 (*.svg);;PNG 图像 (*.png);;PDF (*.pdf)")
        if path:
            try:
                if self.plot.stack.currentWidget() != self.plot.chart:
                    raise ValueError("当前为原始图片或交互图，请在结果文件中选择并导出原始文件。")
                self.plot.figure.savefig(path, dpi=600, bbox_inches="tight")
                self.statusBar().showMessage("图表已导出。", 5000)
            except Exception as error:
                self.error(error)

    def export_artifact(self):
        item = self.files.currentItem()
        if item is None:
            self.tabs.setCurrentWidget(self.files)
            self.statusBar().showMessage("请先在结果文件中选择要导出的文件。")
            return
        source = Path(item.data(Qt.UserRole))
        path, _ = QFileDialog.getSaveFileName(self, "导出结果文件", source.name)
        if path:
            try:
                shutil.copy2(source, path)
            except Exception as error:
                self.error(error)

    def export_bundle(self):
        if self.current_directory is None:
            self.error("请先完成或选择一次分析。")
            return
        if self.runner.running:
            self.error("请在当前分析结束后导出完整记录。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出完整分析记录", self.current_directory.name + ".zip", "ZIP (*.zip)")
        if path:
            try:
                target = Path(path)
                if target.resolve().is_relative_to(self.current_directory):
                    raise ValueError("导出位置应在本次分析目录之外。")
                shutil.make_archive(str(target.with_suffix("")), "zip", self.current_directory)
                self.statusBar().showMessage("已导出输入、参数、结果及日志。", 5000)
            except Exception as error:
                self.error(error)

    def open_directory(self):
        directory = self.current_directory or (self.project.root if self.project else None)
        if directory:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def reuse_parameters(self):
        if not self.ensure_idle() or self.current_directory is None:
            return
        try:
            request = json.loads((self.current_directory / "request.json").read_text(encoding="utf-8"))
            operation = BY_KEY[request["operation"]]
            self.nav.setCurrentRow(self.groups.index(operation.group))
            self.operation_combo.setCurrentIndex(self.operation_combo.findData(operation.key))
            for key, value in request["parameters"].items():
                if key in self.editors:
                    self.editors[key].set_value(value)
                elif key == "background":
                    for field, item in value.items():
                        if field in self.background_editors:
                            self.background_editors[field].set_value(item)
            for key, value in request["inputs"].items():
                values = value if isinstance(value, list) else [value]
                paths = [str(self.current_directory / path) for path in values]
                if key in self.inputs:
                    records = request.get("input_records", {}).get(key, [])
                    records = records if isinstance(records, list) else [records]
                    labels = [record["name"] for record in records] if records else None
                    self.inputs[key].set_paths(paths, labels)
                elif key.startswith("parameter_") and key[10:] in self.editors:
                    self.editors[key[10:]].set_value(paths[0])
            if self.context_combo is not None:
                index = self.context_combo.findData(self.current_directory.relative_to(self.project.root).as_posix())
                if index >= 0:
                    self.context_combo.setCurrentIndex(index)
            self.statusBar().showMessage("已载入该次分析的输入和参数；开始分析会创建新记录。")
        except Exception as error:
            self.error(error)

    def open_example(self):
        if not self.ensure_idle():
            return
        from .examples import create_example
        directory = QFileDialog.getExistingDirectory(self, "选择示例项目保存目录")
        if directory:
            try:
                self.set_project(create_example(Path(directory)))
                self.restore_values(self.project.data["drafts"]["xrd"])
            except Exception as error:
                self.error(error)

    def show_help(self):
        self.summary.setHtml("<h2>使用顺序</h2><ol><li>新建项目或打开已有项目。</li>"
                             "<li>选择分析模块，导入实验谱图和需要的 CIF。</li>"
                             "<li>确认射线波长、数据单位和分析区间；需要时展开高级参数。</li>"
                             "<li>开始分析，可在运行日志中查看真实计算阶段，也可停止。</li>"
                             "<li>双击结果文件预览曲线、图片或数据，导出结果或完整记录。</li></ol>"
                             "<p>列表参数使用 [10, 90]，各相晶格参数使用 [[a,b,c,α,β,γ], ...]。"
                             "XPS 峰通过峰表编辑。留空使用自动计算或原始默认值。</p>"
                             "<p>数据预览最多 2000 行、100 列；完整结果不会截断。</p>"
                             "<p>请检查收敛状态、残差与物理合理性。结构预求解只改写运行目录内的副本。</p>")
        self.tabs.setCurrentWidget(self.summary)

    def show_about(self):
        QMessageBox.about(self, "关于 PyWPEM Desktop",
                          f"PyWPEM Desktop {__version__}\n\n计算内核：PyWPEM / PyXplore\n作者：Bin Cao 等\n"
                          "科研引用：AI-Driven Structure Refinement of X-ray Diffraction\narXiv:2602.16372\n\n"
                          "内核遵循原 MIT 许可；第三方组件保留各自许可。\nhttps://github.com/Bin-Cao/PyWPEM")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        if len(paths) == 1 and paths[0].endswith((".wpem", ".wpem.json")):
            self.open_project(paths[0])
        else:
            if not self.project:
                self.new_project()
            if self.project:
                self.add_files(paths)

    def closeEvent(self, event):
        if self.runner.running:
            answer = QMessageBox.question(self, "计算仍在运行", "停止当前分析并退出？已生成文件会保留。")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self.runner.shutdown()
        if self.project:
            self.save_project(silent=True)
            try:
                self.project.save()
            except OSError as error:
                self.error(error)
                event.ignore()
                return
        if self._project_lock:
            self._project_lock.unlock()
        self.close_web_view()
        event.accept()
