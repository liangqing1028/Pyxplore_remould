"""Small reusable controls for files, scientific parameters and plots."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QSizePolicy,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure


class FilePicker(QWidget):
    changed = Signal()

    def __init__(self, kind="spectrum", multiple=False, parent=None):
        super().__init__(parent)
        self.kind, self.multiple = kind, multiple
        self.paths = []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel("尚未选择文件")
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.PlainText)
        self.label.setObjectName("fileLabel")
        self.label.setMinimumWidth(0)
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.button = QPushButton("选择…")
        self.button.setFixedWidth(66)
        self.button.clicked.connect(self.choose)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.button)

    def choose(self):
        filters = {"spectrum": "实验数据 (*.csv *.dat *.txt *.xy *.xrdml);;所有文件 (*)",
                   "cif": "晶体结构 (*.cif)", "json": "JSON (*.json)",
                   "array": "数值数据 (*.npy *.npz *.csv *.txt *.json)", "file": "数据文件 (*.csv *.npy *.json);;所有文件 (*)"}
        if self.multiple:
            paths, _ = QFileDialog.getOpenFileNames(self, "选择数据文件", "", filters[self.kind])
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择数据文件", "", filters[self.kind])
            paths = [path] if path else []
        if paths:
            self.set_paths(paths)

    def set_paths(self, paths, labels=None):
        self.paths = [str(Path(path).resolve()) for path in paths]
        self.label.setText("\n".join(labels or [Path(path).name for path in self.paths]) or "尚未选择文件")
        self.label.setToolTip("\n".join(self.paths))
        self.changed.emit()

    def value(self):
        return list(self.paths) if self.multiple else (self.paths[0] if self.paths else None)


class PeakEditor(QWidget):
    def __init__(self, value, parent=None):
        super().__init__(parent)
        self.rows = value or []
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        button = QPushButton("编辑峰表…")
        button.clicked.connect(self.edit)
        layout.addWidget(self.label, 1)
        layout.addWidget(button)
        self.set_value(self.rows)

    def set_value(self, value):
        self.rows = value or []
        self.label.setText(f"已配置 {len(self.rows)} 个峰")

    def value(self):
        return self.rows

    def edit(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("峰配置 · 结合能单位 eV")
        dialog.resize(530, 360)
        layout = QVBoxLayout(dialog)
        table = QTableWidget(len(self.rows), 3)
        table.setHorizontalHeaderLabels(["元素状态，如 CuII", "轨道，如 2p3/2", "结合能（eV）"])
        table.horizontalHeader().setStretchLastSection(True)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for row, values in enumerate(self.rows):
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(str(value)))
        layout.addWidget(table)
        controls = QHBoxLayout()
        add, remove = QPushButton("添加峰"), QPushButton("删除所选")
        add.clicked.connect(lambda: table.insertRow(table.rowCount()))
        remove.clicked.connect(lambda: [table.removeRow(row) for row in sorted({item.row() for item in table.selectedItems()}, reverse=True)])
        controls.addWidget(add)
        controls.addWidget(remove)
        controls.addStretch()
        layout.addLayout(controls)
        error = QLabel()
        error.setStyleSheet("color: #be453d;")
        layout.addWidget(error)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)

        def accept():
            rows = []
            try:
                for row in range(table.rowCount()):
                    values = [(table.item(row, col).text().strip() if table.item(row, col) else "") for col in range(3)]
                    if not all(values):
                        raise ValueError("每个峰需要填写元素状态、轨道和结合能。")
                    energy = float(values[2])
                    if not np.isfinite(energy):
                        raise ValueError("结合能必须为有限数值。")
                    rows.append([values[0], values[1], energy])
            except ValueError as exception:
                error.setText(str(exception))
                return
            self.set_value(rows)
            dialog.accept()

        buttons.accepted.connect(accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()


class ParameterEditor(QWidget):
    def __init__(self, field, parent=None):
        super().__init__(parent)
        self.field = field
        value, key = field["default"], field["key"]
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if key in {"atomIdentifier", "satellitePeaks"}:
            self.control = PeakEditor(value)
        elif key == "CSWPEMout":
            self.control = FilePicker("file")
        elif isinstance(value, bool):
            self.control = QCheckBox("启用")
            self.control.setChecked(value)
        elif field.get("choices"):
            self.control = QComboBox()
            self.control.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            self.control.setMinimumContentsLength(12)
            self.control.addItems(field["choices"])
            self.control.setCurrentText(str(value))
        else:
            self.control = QLineEdit()
            self.control.setMinimumWidth(160)
            self.control.setPlaceholderText("必填" if field["required"] else "自动 / 使用默认值")
            self.set_value(value)
        self.setToolTip(key)
        self.control.setAccessibleName(field["label"])
        layout.addWidget(self.control)

    def set_value(self, value):
        if isinstance(self.control, PeakEditor):
            self.control.set_value(value)
        elif isinstance(self.control, QCheckBox):
            self.control.setChecked(bool(value))
        elif isinstance(self.control, QComboBox):
            self.control.setCurrentText(str(value))
        elif isinstance(self.control, FilePicker):
            self.control.set_paths([value] if value else [])
        else:
            self.control.setText("" if value is None else (value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)))

    def value(self):
        control = self.control
        if isinstance(control, (PeakEditor, FilePicker)):
            return control.value()
        if isinstance(control, QCheckBox):
            return control.isChecked()
        if isinstance(control, QComboBox):
            return control.currentText()
        text = control.text().strip()
        if not text:
            if self.field["required"]:
                raise ValueError("请填写：" + self.field["label"])
            return None
        try:
            value = json.loads(text)
        except ValueError:
            if "," in text and not text.startswith("["):
                try:
                    value = json.loads("[" + text + "]")
                except ValueError as error:
                    raise ValueError(self.field["label"] + "：列表请使用 [值1, 值2] 格式。") from error
            elif isinstance(self.field["default"], (int, float, list, tuple)):
                raise ValueError(self.field["label"] + "：请输入有效的数值或列表。")
            else:
                value = text
        if isinstance(value, (int, float)) and not np.isfinite(value):
            raise ValueError(self.field["label"] + "：请输入有限数值。")
        return value


class PlotView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.series = []
        self.figure = Figure(figsize=(9, 5), facecolor="#ffffff", layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.curve_list = QListWidget()
        self.curve_list.setMaximumHeight(95)
        self.curve_list.itemChanged.connect(self.redraw)
        self.stack = QStackedWidget()
        self.chart = QWidget()
        chart_layout = QVBoxLayout(self.chart)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(self.toolbar)
        chart_layout.addWidget(self.canvas, 1)
        chart_layout.addWidget(self.curve_list)
        self.stack.addWidget(self.chart)
        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image_scroll = QScrollArea()
        self.image_scroll.setWidgetResizable(True)
        self.image_scroll.setWidget(self.image)
        self.stack.addWidget(self.image_scroll)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stack)
        self.xlabel, self.ylabel, self.title, self.invert_x = "2θ (°)", "Intensity (a.u.)", "", False
        self.redraw()

    def set_curves(self, series, xlabel="2θ (°)", ylabel="Intensity (a.u.)", title="", invert_x=False):
        self.series = series
        self.xlabel, self.ylabel, self.title, self.invert_x = xlabel, ylabel, title, invert_x
        self.curve_list.blockSignals(True)
        self.curve_list.clear()
        for index, curve in enumerate(series):
            label = str(curve.get("label", ""))
            if not label or label.startswith("_"):
                label = f"Curve {index + 1}"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            self.curve_list.addItem(item)
        self.curve_list.blockSignals(False)
        self.stack.setCurrentWidget(self.chart)
        self.redraw()

    def redraw(self, *args):
        self.figure.clear()
        axis = self.figure.add_subplot(111)
        palette = ["#1665b5", "#dc7f3d", "#35938a", "#a174b0", "#b34e56", "#677f98"]
        for index, curve in enumerate(self.series):
            if self.curve_list.item(index).checkState() != Qt.Checked:
                continue
            axis.plot(curve["x"], curve["y"], lw=1.3, color=palette[index % len(palette)],
                      label=self.curve_list.item(index).text())
        axis.set_xlabel(self.xlabel)
        axis.set_ylabel(self.ylabel)
        axis.set_title(self.title, loc="left", fontsize=11, pad=14)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(color="#e5eaf0", linewidth=0.65)
        axis.set_axisbelow(True)
        if self.series:
            if axis.lines:
                axis.legend(frameon=False, fontsize=8, loc="best")
        else:
            axis.text(0.5, 0.5, "Import a spectrum to begin", ha="center", va="center",
                      transform=axis.transAxes, color="#8a96a5", fontsize=14)
        if self.invert_x:
            axis.invert_xaxis()
        self.canvas.draw_idle()

    def show_image(self, path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            raise ValueError("无法读取图片。")
        self.image.setPixmap(pixmap.scaled(1150, 800, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.stack.setCurrentWidget(self.image_scroll)
