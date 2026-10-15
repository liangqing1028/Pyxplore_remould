"""Run the pinned scientific APIs inside one isolated analysis directory."""

from __future__ import annotations

import importlib.metadata
import copy
import json
import os
import random
import shutil
import time
import traceback
from pathlib import Path

import numpy as np

from . import __version__
from .catalog import BY_KEY, parameters
from .data import load_array, read_spectrum
from .project import timestamp, write_json


def json_value(value):
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def validate_parameters(operation, params):
    fields = {field["key"] for field in parameters(operation)}
    unexpected = set(params) - fields - {"background", "preprocess"}
    if unexpected:
        raise ValueError("未知参数：" + ", ".join(sorted(unexpected)))
    for key in ("iter_max", "max_iter", "max_nfev", "cpu", "num", "subset_number", "window_size", "mix_component", "bac_split", "search_cap"):
        if key in params and (isinstance(params[key], bool) or not isinstance(params[key], int) or params[key] < 1):
            raise ValueError(f"{key} 必须是正整数。")
    for key in ("two_theta_range", "ang_range", "energy_range", "s_energy"):
        interval = params.get(key)
        if interval is not None:
            count = (2, 3) if key == "two_theta_range" and operation.key == "simulation" else (2,)
            if not isinstance(interval, (tuple, list)) or len(interval) not in count or interval[0] >= interval[1]:
                raise ValueError(f"{key} 需要有序的起点、终点" + ("及可选正步长。" if len(count) == 2 else "。"))
            if len(interval) == 3 and interval[2] <= 0:
                raise ValueError("扫描步长必须大于 0。")
    if "ratio" in params and operation.key == "split" and not 0 < params["ratio"] < 1:
        raise ValueError("测试集比例必须在 0 与 1 之间。")
    for key in ("RSSratio", "bta", "bta_threshold", "LFctg"):
        if key in params and not 0 <= params[key] <= 1:
            raise ValueError(f"{key} 必须在 0 与 1 之间。")
    if "window_length" in params and (params["window_length"] < 1 or params["window_length"] % 2 != 1):
        raise ValueError("平滑窗口必须是正奇数。")
    if params.get("polyorder", 3) >= params.get("window_length", 17):
        raise ValueError("平滑多项式阶数必须小于窗口点数。")
    if operation.key == "xps":
        for key in ("atomIdentifier", "satellitePeaks"):
            rows = params.get(key)
            if not isinstance(rows, list) or (key == "atomIdentifier" and not rows):
                raise ValueError("请配置至少一个主峰；卫星峰可以为空。")
            if any(not isinstance(row, list) or len(row) != 3 or not isinstance(row[2], (float, int)) for row in rows):
                raise ValueError("峰配置每行需要：元素状态、轨道、结合能（eV）。")
    if operation.key == "rdf" and (params.get("density_zero") is None or params["density_zero"] <= 0):
        raise ValueError("请填写正数原子数密度，单位为 atoms/Å³。")


def setup_plot_capture(directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import plotly.graph_objects as go

    folder = directory / "figures"
    folder.mkdir(exist_ok=True)
    counter = [0]

    def capture_matplotlib(*args, **kwargs):
        for figure_number in plt.get_fignums():
            figure = plt.figure(figure_number)
            if not figure.axes:
                continue
            counter[0] += 1
            base = folder / f"figure-{counter[0]:03d}"
            figure.savefig(base.with_suffix(".png"), dpi=180, bbox_inches="tight")
            figure.savefig(base.with_suffix(".svg"), bbox_inches="tight")
            axes = []
            for axis in figure.axes:
                curves = []
                for line in axis.lines:
                    try:
                        x, y = np.asarray(line.get_xdata(), dtype=float), np.asarray(line.get_ydata(), dtype=float)
                    except (TypeError, ValueError):
                        continue
                    if x.ndim == y.ndim == 1 and len(x) == len(y):
                        curves.append({"label": line.get_label(), "x": x.tolist(), "y": y.tolist(),
                                       "color": line.get_color(), "style": line.get_linestyle()})
                if curves:
                    axes.append({"xlabel": axis.get_xlabel(), "ylabel": axis.get_ylabel(),
                                 "title": axis.get_title(), "curves": curves,
                                 "invert_x": axis.xaxis_inverted()})
            if axes:
                write_json(base.with_suffix(".curves.json"), json_value(axes))

    def capture_plotly(figure, *args, **kwargs):
        counter[0] += 1
        figure.write_html(str(folder / f"interactive-{counter[0]:03d}.html"), include_plotlyjs=True)

    plt.show = capture_matplotlib
    go.Figure.show = capture_plotly
    return plt


def normalize_input(path, directory, name="spectrum"):
    frame = read_spectrum(path)
    target = directory / f"{name}.csv"
    frame.to_csv(target, header=False, index=False)
    return frame, str(target)


def fit_background(wpem, frame, directory, kwargs=None, model="XRD"):
    kwargs = dict(kwargs or {})
    kwargs["Model"] = model
    validate_parameters(BY_KEY["background"], kwargs)
    if len(frame) < kwargs.get("window_length", 17):
        raise ValueError("数据点数少于平滑窗口，请减小窗口或导入完整谱图。")
    print("阶段：背景拟合与扣除", flush=True)
    variance = wpem.BackgroundFit(frame, work_dir=str(directory), **kwargs)
    return variance


def stage_context(directory):
    context = directory / "context"
    if not context.exists():
        return
    for source in context.iterdir():
        if source.name in {"inputs", "context", "request.json", "result.json", "run.log", "figures"}:
            continue
        target = directory / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)


def background_std_for_range(value, frame, interval):
    array = np.asarray(value, dtype=float)
    if not np.isfinite(array).all() or np.any(array < 0):
        raise ValueError("背景标准差必须是有限非负数。")
    if array.ndim == 0:
        return float(array)
    if array.ndim != 1:
        raise ValueError("背景标准差应为单个数值或一维数组。")
    mask = np.ones(len(frame), dtype=bool) if interval is None else (frame.x >= interval[0]) & (frame.x <= interval[1])
    if len(array) == len(frame):
        return array[mask]
    if len(array) == np.count_nonzero(mask):
        return array
    raise ValueError("背景标准差数组长度与分析区间的数据点数不一致。")


def execute(operation, inputs, params, directory):
    from ._vendor.pywpem import WPEM as wpem

    params = dict(params)
    background = params.pop("background", {})
    preprocess = params.pop("preprocess", {})
    for name in ("two_theta_range", "ang_range", "energy_range"):
        if isinstance(params.get(name), list):
            params[name] = tuple(params[name])
    for key in tuple(inputs):
        if key.startswith("parameter_"):
            params[key.removeprefix("parameter_")] = inputs[key]
    stage_context(directory)
    key = operation.key
    summary = {}
    metrics = {}
    if key == "convert":
        frame, path = normalize_input(inputs["spectrum"], directory, "converted")
        summary = {"数据点数": len(frame), "横坐标范围": [float(frame.x.min()), float(frame.x.max())], "输出": Path(path).name}
    elif key == "background":
        frame, _ = normalize_input(inputs["spectrum"], directory)
        variance = fit_background(wpem, frame, directory, params, params.get("Model", "XRD"))
        np.save(directory / "background_std.npy", variance)
        summary = {"背景标准差": json_value(variance), "数据点数": len(frame)}
    elif key in {"xrd", "xrd_manual"}:
        frame, original = normalize_input(inputs["spectrum"], directory, "intensity")
        variance = fit_background(wpem, frame, directory, background)
        wavelength = params.get("wavelength", [1.54056, 1.54439])
        waves = wavelength if isinstance(wavelength, list) else [wavelength]
        if not waves or any(not isinstance(wave, (int, float)) or wave <= 0 for wave in waves):
            raise ValueError("XRD 精修波长应为正数列表，例如 [1.54056, 1.54439]。")
        lattice, densities = [], []
        theta_range = params.get("two_theta_range") or (float(frame.x.min()), float(frame.x.max()))
        if key == "xrd":
            for index, cif in enumerate(inputs["cifs"]):
                print(f"阶段：晶相 {index + 1} / {len(inputs['cifs'])} 预处理", flush=True)
                constants, _, density = wpem.CIFpreprocess(cif, wavelength=waves[0],
                                                          two_theta_range=theta_range, work_dir=str(directory), **preprocess)
                reflection = directory / "output_xrd" / f"{Path(cif).stem}HKL.csv"
                shutil.copy2(reflection, directory / f"peak{index}.csv")
                lattice.append(constants)
                densities.append(density)
        else:
            lattice = params.get("Lattice_constants")
            if not isinstance(lattice, list) or len(lattice) != len(inputs["peaks"]):
                raise ValueError("每个晶相需要一组晶格参数和一个初始峰文件，数量必须一致。")
            for index, reflection in enumerate(inputs["peaks"]):
                shutil.copy2(reflection, directory / f"peak{index}.csv")
            densities = [1.0] * len(lattice)
        params["wavelength"] = waves
        params["Lattice_constants"] = params.get("Lattice_constants") or lattice
        params["density_list"] = params.get("density_list") or densities
        params["Var"] = variance if params.get("Var") is None else params["Var"]
        params["Var"] = background_std_for_range(params["Var"], frame, params.get("two_theta_range"))
        if len(params["Lattice_constants"]) != len(lattice) or len(params["density_list"]) != len(lattice):
            raise ValueError("晶格参数、密度和 CIF 的晶相数量必须一致。")
        print("阶段：全谱拟合与晶格精修", flush=True)
        initial_lattice = copy.deepcopy(params["Lattice_constants"])
        value = wpem.XRDfit(**params, original_file=original,
                            no_bac_intensity_file=str(directory / "ConvertedDocuments/no_bac_intensity.csv"),
                            bacground_file=str(directory / "ConvertedDocuments/bac.csv"),
                            work_dir=str(directory), cif_files=inputs.get("cifs"), return_diagnostics=True)
        summary = {"晶相数": len(lattice), "精修前晶格参数": initial_lattice, "精修后晶格参数": value["lattice_constants"],
                   "说明": "XRDfit 精修晶格常数；原子坐标由独立的结构求解 / 占位搜索处理。"}
        metrics = value["diagnostics"]
    elif key in {"cif", "simulation"}:
        value = getattr(wpem, operation.api)(inputs["cif"], work_dir=str(directory), **params)
        if key == "cif":
            summary = {"晶格参数": value[0], "原子坐标": value[1], "密度（g/cm³）": value[2]}
            if params.get("relaxation"):
                summary["结构弛豫"] = json.loads((directory / "output_xrd/relaxation.json").read_text())
        else:
            summary = {"结构因子": json_value(value[0]), "模拟数据点数": len(value[1])}
            np.savetxt(directory / "Simulation_WPEM/spectrum.csv", np.column_stack((value[1], value[2])), delimiter=",")
    elif key == "structure":
        _, spectrum = normalize_input(inputs["spectrum"], directory)
        report = wpem.StructureSolve(spectrum, inputs["cif"], work_dir=str(directory), **params)
        summary = report
    elif key == "substitution":
        value = wpem.SubstitutionalSearch(inputs["peaks"], inputs["cif"], work_dir=str(directory), **params)
        summary = {"搜索结果": json_value(value)}
    elif key in {"amorphous", "rdf"}:
        _, spectrum = normalize_input(inputs["spectrum"], directory)
        value = getattr(wpem, operation.api)(amor_file=spectrum, work_dir=str(directory), **params)
        summary = {"处理结果": json_value(value)}
    elif key == "xps":
        frame, original = normalize_input(inputs["spectrum"], directory, "intensity")
        variance = fit_background(wpem, frame, directory, background, "XPS")
        params["Var"] = variance if params.get("Var") is None else params["Var"]
        params["Var"] = background_std_for_range(params["Var"], frame, params.get("energy_range"))
        no_bac = str(directory / "ConvertedDocuments/no_bac_intensity.csv")
        bac = str(directory / "ConvertedDocuments/bac.csv")
        value = wpem.XPSfit(original_df=original, no_bac_df=no_bac, bacground_df=bac,
                           work_dir=str(directory), return_diagnostics=True, **params)
        metrics = value["diagnostics"]
        summary = {"主峰数": len(params["atomIdentifier"]), "卫星峰数": len(params.get("satellitePeaks", []))}
    elif key == "exafs":
        _, spectrum = normalize_input(inputs["spectrum"], directory)
        if params.get("name") and any(char in str(params["name"]) for char in ("/", "\\", "\0")):
            raise ValueError("样品名称不能包含路径分隔符。")
        value = wpem.EXAFSfit(spectrum, work_dir=str(directory), **params)
        summary = {"处理结果": json_value(value)}
    elif key == "components":
        if not (directory / "DecomposedComponents").is_dir():
            raise ValueError("请选择已有的 XRD 分析作为前次结果。")
        value = wpem.Plot_Components(work_dir=str(directory), **params)
        summary = {"定量结果": json_value(value)}
    elif key == "graph":
        from ._vendor.pywpem.GraphStructure.graph import CrystalGraph
        folder = directory / "cifs"
        folder.mkdir(exist_ok=True)
        for path in inputs["cifs"]:
            shutil.copy2(path, folder / Path(path).name)
        graph = CrystalGraph(str(folder), str(directory))
        records = graph.generate_graph(**params)
        if not records:
            raise ValueError("没有成功生成的晶体图，请检查 CIF 中的对称信息及原子坐标。")
        for index, record in enumerate(records):
            prefix = directory / "CifParserToGraph" / f"graph-{index:03d}"
            write_json(prefix.with_suffix(".nodes.json"), json_value(record["nodes"]))
            np.save(prefix.with_suffix(".edges.npy"), np.asarray(record["edges"], dtype=int))
        write_json(directory / "CifParserToGraph/graphs.json", json_value(records))
        summary = {"成功晶体图数量": len(records), "输入 CIF 数量": len(inputs["cifs"])}
    elif key == "matrix":
        node = json.loads(Path(inputs["nodes"]).read_text(encoding="utf-8"))
        if not isinstance(node, dict):
            raise ValueError("节点 JSON 应为节点编号到数值特征的字典。")
        value = wpem.ToMatrix(node)
        if not np.issubdtype(value.dtype, np.number) or not np.isfinite(value).all():
            raise ValueError("节点特征必须是有限数值。")
        np.save(directory / "node_matrix.npy", value)
        np.savetxt(directory / "node_matrix.csv", value, delimiter=",")
        summary = {"矩阵形状": list(value.shape)}
    elif key == "adjacency":
        path = Path(inputs["edges"])
        edge = np.asarray(json.loads(path.read_text()) if path.suffix.lower() == ".json" else load_array(path))
        edge = np.atleast_2d(edge)
        if edge.shape[1] != 2 or not np.isfinite(edge).all() or np.any(edge < 0) or not np.equal(edge, np.floor(edge)).all():
            raise ValueError("边列表应为两列非负整数。")
        size = params.pop("size", None) or int(edge.max()) + 1
        if not isinstance(size, int) or size <= int(edge.max()):
            raise ValueError("节点数量必须大于最大节点编号。")
        value = wpem.ToAdj(edge.astype(int), size, **params)
        np.save(directory / "adjacency.npy", value)
        np.savetxt(directory / "adjacency.csv", value, delimiter=",")
        summary = {"节点数量": size, "边数量": len(edge)}
    elif key == "split":
        arrays = [load_array(inputs[name]) for name in ("nodes", "edges", "target")]
        if len({len(array) for array in arrays}) != 1 or len(arrays[0]) < 2:
            raise ValueError("节点、边和目标数组第一维必须相同，并至少有两个样本。")
        ratio = params.get("ratio", 0.2)
        if not 1 <= int(len(arrays[0]) * (1 - ratio)) < len(arrays[0]):
            raise ValueError("当前比例会产生空训练集或空测试集，请调整。")
        values = wpem.split_datasets(*arrays, **params)
        for name, value in zip(("nodes_train", "nodes_test", "edges_train", "edges_test", "target_train", "target_test"), values):
            np.save(directory / f"{name}.npy", value)
        summary = {"训练样本数": len(values[0]), "测试样本数": len(values[1])}
    elif key == "laplacian":
        adjacency = load_array(inputs["matrix"])
        if adjacency.ndim != 2 or adjacency.shape[0] != adjacency.shape[1] or np.any(adjacency < 0) or not np.allclose(adjacency, adjacency.T):
            raise ValueError("请输入非负、对称的方阵。")
        for name, value in zip(("laplacian", "eigenvalues", "eigenvectors"), wpem.Laplacian(adjacency)):
            np.save(directory / f"{name}.npy", value)
            np.savetxt(directory / f"{name}.csv", value, delimiter=",")
        summary = {"节点数量": len(adjacency), "对角正则化常数": 1e-5}
    else:
        raise ValueError("不支持的分析任务。")
    return summary, metrics


def run_request(request_path):
    request_path = Path(request_path).resolve()
    directory = request_path.parent
    started = time.monotonic()
    result = {"format": 1, "status": "failed", "started_at": timestamp(), "desktop_version": __version__}
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"),
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"无效数值：{value}")))
        operation = BY_KEY[request["operation"]]
        result["operation"] = operation.key
        result["engine_commit"] = json.loads((Path(__file__).parent / "_vendor/upstream.json").read_text())["commit"]
        params = request["parameters"]
        validate_parameters(operation, params)
        inputs = {}
        for key, value in request["inputs"].items():
            paths = value if isinstance(value, list) else [value]
            resolved = []
            for path in paths:
                target = (directory / path).resolve(strict=True)
                if not target.is_relative_to(directory) or not target.is_file():
                    raise ValueError("输入文件必须位于本次分析目录内。")
                resolved.append(str(target))
            inputs[key] = resolved if isinstance(value, list) else resolved[0]
        for expected in operation.inputs:
            if expected.key not in inputs or not inputs[expected.key]:
                raise ValueError(f"缺少输入：{expected.label}")
        seed = int(request.get("seed", 42))
        np.random.seed(seed)
        random.seed(seed)
        os.chdir(directory)
        plt = setup_plot_capture(directory)
        print(f"任务：{operation.label}\n随机种子：{seed}", flush=True)
        summary, metrics = execute(operation, inputs, params, directory)
        numeric_outputs = {
            "background": ["ConvertedDocuments/bac.csv", "ConvertedDocuments/no_bac_intensity.csv"],
            "xrd": ["DecomposedComponents/fitting_profile.csv"],
            "xrd_manual": ["DecomposedComponents/fitting_profile.csv"],
            "xps": ["XPScomponents/FittingProfile.csv"],
            "amorphous": ["DecomposedComponents/Amorphous.csv"],
            "rdf": ["DecomposedComponents/RDF.csv"],
            "exafs": ["XAFS/EXAFS/FineStructure_*.csv"],
            "simulation": ["Simulation_WPEM/spectrum.csv"],
        }
        for pattern in numeric_outputs.get(operation.key, []):
            files = list(directory.glob(pattern))
            if not files:
                raise ValueError("计算没有生成预期的数值结果：" + pattern)
            for file in files:
                read_spectrum(file)
        for name in ("Rp", "Rwp"):
            if name in metrics and (not np.isfinite(metrics[name]) or metrics[name] < 0):
                raise ValueError(f"{name} 不是有效的拟合指标，结果不能视为成功。")
        plt.close("all")
        result.update(status="success", summary=json_value(summary), metrics=json_value(metrics))
        if metrics.get("flag") in (3, 4):
            result["status"] = "warning"
            result["warning"] = "已完成计算，但未达到收敛条件；请检查残差、迭代上限及参数。"
        if operation.key == "structure" and not summary.get("accepted"):
            result["status"] = "warning"
            result["warning"] = "结构候选未通过接受条件，输入 CIF 副本保持原状。"
    except Exception as error:
        result["error"] = str(error)
        result["traceback"] = traceback.format_exc()
        print(result["traceback"], flush=True)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    result["finished_at"] = timestamp()
    result["versions"] = {}
    for package in ("numpy", "scipy", "pandas", "pymatgen", "tensorflow", "PySide6", "Bgolearn"):
        try:
            result["versions"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    result["artifacts"] = [str(path.relative_to(directory)) for path in sorted(directory.rglob("*"))
                           if path.is_file() and path.name not in {"run.log", "result.json", "request.json"}
                           and "inputs" not in path.relative_to(directory).parts and "context" not in path.relative_to(directory).parts]
    write_json(directory / "result.json", result)
    print(f"任务状态：{result['status']}；耗时 {result['elapsed_seconds']} 秒", flush=True)
    return 0 if result["status"] in {"success", "warning"} else 1
