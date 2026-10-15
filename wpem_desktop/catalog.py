"""Task descriptions and parameter metadata from the pinned upstream API."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Input:
    key: str
    label: str
    kind: str = "spectrum"
    multiple: bool = False


@dataclass(frozen=True)
class Operation:
    key: str
    group: str
    label: str
    api: str | None
    description: str
    inputs: tuple[Input, ...]
    common: tuple[str, ...] = ()
    hidden: tuple[str, ...] = ()
    context: bool = False


SPECTRUM = Input("spectrum", "实验数据")
CIF = Input("cif", "晶体结构 CIF", "cif")
CIFS = Input("cifs", "晶相 CIF（可多选）", "cif", True)
OPERATIONS = (
    Operation("xrd", "XRD", "全谱拟合与晶格精修", "XRDfit",
              "自动完成背景处理、CIF 预处理、全谱拟合及精修 CIF 导出。保留各晶相的晶格参数与拟合诊断。",
              (SPECTRUM, CIFS), ("wavelength", "two_theta_range", "MODEL", "iter_max", "cpu"),
              ("no_bac_intensity_file", "original_file", "bacground_file", "cif_files", "cif_output_dir"), True),
    Operation("background", "XRD", "背景拟合与扣除", "BackgroundFit",
              "预览背景曲线、选点和扣除背景后的信号。可用于 XRD、XPS 和 Raman。",
              (SPECTRUM,), ("Model", "LFctg", "bac_split", "poly_n", "bac_var_type", "segment"), ("intensity_csv",)),
    Operation("xrd_manual", "XRD", "自定义反射与晶格拟合", "XRDfit",
              "用于已有反射列表或无完整 CIF 的分析。峰文件顺序必须与各相晶格参数顺序一致；支持原项目的大分子 / 非晶模式。",
              (SPECTRUM, Input("peaks", "初始反射 CSV（按晶相顺序多选）", "file", True)),
              ("wavelength", "Lattice_constants", "two_theta_range", "MODEL", "Macromolecule", "iter_max", "cpu"),
              ("no_bac_intensity_file", "original_file", "bacground_file", "cif_files", "cif_output_dir"), True),
    Operation("convert", "XRD", "数据格式转换", None,
              "将 CSV、DAT、TXT、XY、单扫描 XRDML 转为统一的两列数值 CSV。原文件保留。", (SPECTRUM,)),
    Operation("cif", "晶体结构", "CIF 预处理与消光", "CIFpreprocess",
              "读取晶格、原子位置和密度，生成反射列表及结构预览。结构弛豫使用内置 M3GNet 模型。",
              (CIF,), ("wavelength", "two_theta_range", "show_unitcell", "cal_extinction", "relaxation"), ("filepath",)),
    Operation("simulation", "XRD", "衍射谱模拟", "XRDSimulation",
              "从 CIF 模拟 XRD；支持超胞、固溶替换、空位、晶粒尺寸、取向及零点偏移。",
              (CIF,), ("wavelength", "two_theta_range", "SuperCell", "PeriodicArr", "GrainSize"), ("filepath",), True),
    Operation("structure", "晶体结构", "结构预求解", "StructureSolve",
              "以强衍射峰改善初始结构。只更新本次运行中的 CIF 副本，并保留接受或拒绝原因。",
              (SPECTRUM, CIF), ("wavelength", "num_peaks", "max_nfev"), ("no_bac_intensity_file", "cif_file")),
    Operation("substitution", "晶体结构", "固溶占位搜索", "SubstitutionalSearch",
              "使用已分解的晶相峰参数和 CIF 搜索替换原子的位置。贝叶斯搜索需要 Bgolearn。",
              (Input("peaks", "晶相峰参数 CSV", "file"), CIF),
              ("wavelength", "SolventAtom", "SoluteAtom", "random_num", "max_iter", "search_cap"), ("xrd_pattern", "cif_file")),
    Operation("amorphous", "非晶分析", "非晶峰拟合", "Amorphous_fit",
              "拟合宽化的非晶峰，输出组分曲线与剥离背景后的信号。输入为待分解的非晶信号。",
              (SPECTRUM,), ("mix_component", "ang_range", "peak_location", "max_iter", "Wavelength"), ("amor_file",)),
    Operation("rdf", "非晶分析", "径向分布函数 RDF", "AmorphousRDFun",
              "由非晶散射强度计算 RDF；密度与散射因子参数需依据样品确认。",
              (SPECTRUM,), ("wavelength", "r_max", "density_zero", "Nf2", "highlight"), ("amor_file",)),
    Operation("xps", "XPS", "XPS 背景与分峰", "XPSfit",
              "完成背景扣除及主峰、卫星峰拟合。结合能使用 eV；结果图按 XPS 惯例显示反向能量轴。",
              (SPECTRUM,), ("atomIdentifier", "satellitePeaks", "energy_range", "iter_max"),
              ("no_bac_df", "original_df", "bacground_df"), True),
    Operation("exafs", "XAS / EXAFS", "EXAFS 信号处理", "EXAFSfit",
              "吸收边定位、背景处理、k 空间加权及 Fourier / 小波变换。使用原项目已有处理方法。",
              (SPECTRUM,), ("Ezero", "de_bac", "power", "distance", "k_point", "transform"), ("XAFSdata",)),
    Operation("components", "XRD", "组分定量与结果绘图", "Plot_Components",
              "选择已完成的 XRD 分析，生成各晶相及非晶组分的定量结果与图表。",
              (), ("lowboundary", "upboundary", "wavelength", "density_list", "name", "phase", "Macromolecule"), (), True),
    Operation("graph", "晶体图", "晶体图构建", "CryGraph",
              "批量读取 CIF 并构建节点、边和标签；同时导出可安全读取的 JSON 与数值数组。",
              (CIFS,), ("BK_boundary_condition",), ("folder_path",)),
    Operation("matrix", "晶体图", "节点转矩阵", "ToMatrix",
              "将节点 JSON 字典转为数值矩阵。可直接使用晶体图分析输出的节点文件。",
              (Input("nodes", "节点 JSON", "json"),), (), ("Node",)),
    Operation("adjacency", "晶体图", "邻接矩阵", "ToAdj",
              "由边列表生成邻接矩阵。节点编号从 0 开始；保留原项目的有向边与计数规则。",
              (Input("edges", "边列表 NPY / CSV / JSON", "array"),), ("size", "sel"), ("Edge",)),
    Operation("split", "晶体图", "数据集划分", "split_datasets",
              "以相同索引划分节点、边和目标数组。随机种子随分析记录保存。输入为数值 NPY / CSV。",
              (Input("nodes", "节点数组", "array"), Input("edges", "边数组", "array"), Input("target", "目标数组", "array")),
              ("ratio",), ("Node", "Edge", "target")),
    Operation("laplacian", "晶体图", "图拉普拉斯分析", "Laplacian",
              "计算归一化拉普拉斯矩阵及特征值、特征向量。输入为非负、对称邻接矩阵。",
              (Input("matrix", "邻接矩阵 NPY / CSV", "array"),), (), ("A",)),
)
BY_KEY = {operation.key: operation for operation in OPERATIONS}
API_PATH = Path(__file__).parent / "_vendor" / "pywpem" / "WPEM.py"

LABELS = {
    "wavelength": "射线波长 / 预设（Å）", "two_theta_range": "2θ 范围（°）", "MODEL": "分析模式",
    "iter_max": "最大迭代次数", "cpu": "计算进程数", "LFctg": "低频滤波比例", "lowAngleRange": "低角度背景边界（°）",
    "bac_num": "背景采样点数", "bac_split": "背景分段数", "window_length": "平滑窗口点数（奇数）",
    "polyorder": "平滑多项式阶数", "poly_n": "背景多项式阶数", "bac_var_type": "背景方差模型",
    "Model": "信号类型", "segment": "手动背景区间", "noise": "背景噪声参数", "mode": "边界处理方式",
    "show_unitcell": "预览晶胞", "cal_extinction": "计算消光", "relaxation": "M3GNet 结构弛豫",
    "SuperCell": "生成超胞", "PeriodicArr": "超胞扩展倍数", "GrainSize": "晶粒尺寸（nm）",
    "LatticCs": "自定义晶格参数", "latt": "自定义晶格参数", "AtomCoordinates": "自定义原子坐标",
    "ReSolidSolution": "替换元素对", "RSSratio": "替换比例", "Vacancy": "考虑空位", "Vacancy_atom": "空位元素",
    "Vacancy_ratio": "空位比例", "PeakWidth": "模拟峰宽", "CSWPEMout": "精修峰参数 CSV", "orientation": "取向强度范围",
    "thermo_vib": "热振动位移（Å）", "zero_shift": "零点偏移（°）", "bacI": "添加模拟背景", "seed": "随机种子",
    "Lattice_constants": "自定义各相晶格参数", "density_list": "各相密度（g/cm³）", "Var": "背景标准差覆盖值",
    "bta": "Lorentz 分量比例", "bta_threshold": "Lorentz 比例下界", "limit": "峰宽方差下界",
    "iter_limit": "迭代停止阈值", "w_limit": "峰权重下界", "lock_num": "连续下降停止次数",
    "asy_C": "峰形不对称系数", "s_angle": "不对称校正角度（°）", "subset_number": "Bragg 优化选峰数",
    "low_bound": "Bragg 选峰下界（°）", "up_bound": "Bragg 选峰上界（°）", "InitializationEpoch": "初始化轮数",
    "Macromolecule": "含非晶 / 大分子", "num": "定量所用强峰数", "EXACT": "使用结构因子精确定量",
    "structure_factor": "各相结构因子", "Cu_tao": "Cu Kα 强度比例限制", "Ave_Waves": "使用平均波长",
    "loadParams": "复用前次峰形参数", "ZeroShift": "标准样品零点校准", "num_peaks": "预求解强峰数",
    "max_nfev": "最大求解次数", "peak_tolerance": "峰位接受误差（°）", "min_improvement": "最低改善比例",
    "coordinate_window": "原子坐标搜索半宽", "cell_window": "晶格长度相对搜索半宽",
    "SolventAtom": "母体离子名称（如 Mn3+）", "SoluteAtom": "替换离子名称（如 Ru2+）", "random_num": "随机初始化次数",
    "max_iter": "最大迭代次数", "search_cap": "候选结构上限", "mix_component": "非晶峰数",
    "ang_range": "分析角度范围（°）", "sigma2_coef": "初始方差系数", "peak_location": "初始峰位（°）",
    "Wavelength": "射线波长（Å）", "r_max": "RDF 最大距离（Å）", "density_zero": "原子数密度（atoms/Å³）",
    "Nf2": "N⟨f²⟩ 参数", "highlight": "标注峰数", "value": "独立散射阈值", "atomIdentifier": "主峰配置",
    "satellitePeaks": "卫星峰配置", "energy_range": "结合能范围（eV）", "s_energy": "不对称峰能量区间（eV）",
    "tao": "结合能调整阈值", "ratio": "调整 / 划分比例", "Ezero": "吸收边 E₀（eV）", "de_bac": "拟合并扣除吸收背景",
    "power": "k 空间加权幂次", "distance": "实空间最大距离（Å）", "k_point": "k 空间截止值",
    "k": "样条阶数", "s": "样条平滑参数", "window_size": "变换窗口点数", "hop_size": "变换步长",
    "Extend": "扩展能量范围（eV）", "name": "样品 / 组分名称", "transform": "变换方法",
    "first_cutoff_energy": "背景低能端（eV）", "second_cutoff_energy": "背景高能端（eV）",
    "lowboundary": "绘图角度下界（°）", "upboundary": "绘图角度上界（°）", "phase": "晶相数量",
    "Pic_Title": "显示图表标题", "lifting": "组分曲线抬升值", "BK_boundary_condition": "考虑周期边界",
    "size": "节点数量", "sel": "添加自连接",
}
CHOICES = {"MODEL": ["REFINEMENT", "ANALYSIS"], "Model": ["XRD", "XPS", "Raman"],
           "bac_var_type": ["constant", "polynomial", "multivariate gaussian"],
           "mode": ["nearest", "mirror", "constant", "wrap", "interp"], "transform": ["fourier", "wavelet"]}
OVERRIDES = {"wavelength": [1.54056, 1.54439], "Lattice_constants": None, "Var": None,
             "atomIdentifier": [["CuII", "2p3/2", 933.7], ["CuII", "2p1/2", 954.0]],
             "satellitePeaks": [], "mix_component": 2, "lowboundary": 10.0, "upboundary": 90.0, "size": None}


def parameters(operation):
    if operation.api is None:
        return []
    module = ast.parse(API_PATH.read_text(encoding="utf-8"))
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == operation.api)
    defaults = [None] * (len(function.args.args) - len(function.args.defaults)) + list(function.args.defaults)
    fields = []
    for arg, node in zip(function.args.args, defaults):
        key = arg.arg
        if key in operation.hidden or key in {"work_dir", "return_diagnostics"}:
            continue
        value = ast.literal_eval(node) if node is not None else None
        if key in OVERRIDES:
            value = OVERRIDES[key]
        if key == "wavelength" and operation.key not in {"xrd", "xrd_manual", "components"}:
            value = "CuKa" if operation.key in {"cif", "simulation", "structure", "substitution"} else 1.54184
        fields.append({"key": key, "label": LABELS.get(key, key), "default": value,
                       "required": (node is None and value is None and key not in {"Lattice_constants", "Var", "size"}) or (operation.key == "rdf" and key == "density_zero") or (operation.key == "xrd_manual" and key == "Lattice_constants") or (operation.key == "substitution" and key in {"SolventAtom", "SoluteAtom"}),
                       "common": key in operation.common, "choices": CHOICES.get(key)})
    return sorted(fields, key=lambda field: not field["common"])
