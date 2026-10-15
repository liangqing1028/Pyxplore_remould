"""Validate experimental data without evaluating code or loading pickle files."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd


def read_spectrum(path, *, minimum=3):
    path = Path(path)
    if path.suffix.lower() == ".xrdml":
        root = ET.fromstring(path.read_bytes())
        strip = lambda tag: tag.rsplit("}", 1)[-1]
        signals = [e for e in root.iter() if strip(e.tag) in {"intensities", "counts"}]
        if len(signals) != 1:
            raise ValueError("XRDML 必须包含一个扫描；请先分别导出多次扫描的数据。")
        y = np.asarray([float(value) for value in (signals[0].text or "").split()])
        positions = next((e for e in root.iter()
                          if strip(e.tag) == "positions" and e.get("axis") == "2Theta"), None)
        if positions is None:
            raise ValueError("XRDML 中没有 2Theta 角度轴。")
        fields = {strip(e.tag): e.text for e in positions}
        if "listPositions" in fields:
            x = np.asarray([float(value) for value in fields["listPositions"].split()])
        else:
            try:
                x = np.linspace(float(fields["startPosition"]), float(fields["endPosition"]), len(y))
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("无法读取 XRDML 的扫描角度。") from error
        if len(x) != len(y):
            raise ValueError("XRDML 的角度与强度点数不一致。")
        values = np.column_stack((x, y))
    else:
        rows = []
        started = False
        text = path.read_text(encoding="utf-8-sig")
        for number, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith(("#", "!", ";")):
                continue
            fields = re.split(r"[,;\s]+", line)
            try:
                row = [float(fields[0]), float(fields[1])]
            except (ValueError, IndexError) as error:
                if started:
                    raise ValueError(f"第 {number} 行不是有效的两列数值，未忽略该行。") from error
                continue
            started = True
            rows.append(row)
        values = np.asarray(rows, dtype=float)
    if values.ndim != 2 or len(values) < minimum:
        raise ValueError(f"需要至少 {minimum} 个有效数据点。")
    if not np.isfinite(values).all():
        raise ValueError("数据包含 NaN 或无穷大。")
    values = values[np.argsort(values[:, 0], kind="stable")]
    if np.any(np.diff(values[:, 0]) <= 0):
        raise ValueError("横坐标有重复值，请先确认扫描数据。")
    return pd.DataFrame(values, columns=["x", "intensity"])


def load_array(path):
    path = Path(path)
    if path.suffix.lower() == ".npy":
        value = np.load(path, allow_pickle=False)
    elif path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as archive:
            if len(archive.files) != 1:
                raise ValueError("请选择仅包含一个数组的 NPZ 文件。")
            value = archive[archive.files[0]]
    else:
        value = np.loadtxt(path, delimiter="," if path.suffix.lower() == ".csv" else None)
    if not np.issubdtype(value.dtype, np.number) or not np.isfinite(value).all():
        raise ValueError("需要不含 NaN / 无穷大的数值数组。")
    return value
