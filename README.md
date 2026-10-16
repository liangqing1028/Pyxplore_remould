# PyWPEM Desktop

面向 Windows 和 macOS 的本地科研分析工作台，基于 [Bin Cao 的 PyWPEM / PyXplore](https://github.com/Bin-Cao/PyWPEM)。

## 功能范围

- XRD：格式转换、背景处理、全谱拟合、晶格常数精修、多相分解、组分定量与衍射谱模拟。
- 晶体结构：CIF 预处理、消光、结构预求解、固溶占位搜索与 M3GNet 弛豫。
- 非晶：峰拟合及 RDF；XPS：主峰与卫星峰拟合；XAS：EXAFS 处理与变换。
- 晶体图：图构建、节点矩阵、邻接矩阵、数据集划分与拉普拉斯分析。
- 独立后台计算、取消任务、输入副本保护、参数与版本记录、项目恢复、交互图表和结果导出。

功能是否已经通过验证，以 `outputs` 中的验证记录及测试结果为准。尚未生成的安装包不视为已交付。

## 下载安装包

打开 [GitHub 构建与下载页面](https://github.com/liangqing1028/Pyxplore_remould/actions/runs/38777042894)，在 Artifacts 中选择对应电脑的文件：`PyWPEMDesktop-Windows-x64`、`PyWPEMDesktop-macOS-arm64`（Apple Silicon）或 `PyWPEMDesktop-macOS-x64`（Intel）。如提示登录，请使用你的 GitHub 账号。

Windows：下载后解压，在 `dist` 文件夹中运行 `PyWPEMDesktop-Windows-x64-Setup.exe` 安装。便携版是同目录下的 ZIP，另行解压后双击 `PyWPEMDesktop.exe`。Mac：下载后解压，在 `dist` 中打开对应架构的 DMG，再把应用拖入“应用程序”。安装包包含计算依赖和离线模型，无需另外安装 Python。

## 直接启动桌面版

本机生成的应用位于 `dist/PyWPEMDesktop.app`，适用于 Apple Silicon Mac。安装镜像位于 `dist/PyWPEMDesktop-macOS-arm64.dmg`：打开镜像，把应用拖入“应用程序”，再双击启动。桌面版已包含计算依赖和离线模型，不需要另装 Python。

启动后可点击“打开示例”，选择一个保存位置，再点击“开始分析”。示例默认运行 5 次迭代；若达到上限，界面会显示“需检查”，可增加迭代次数后重新分析。

当前构建使用本地临时签名，尚未做开发者签名和 Apple 公证。从网络下载后，macOS 可能要求在系统设置的“隐私与安全性”中确认打开。Windows x64 和 Intel Mac 需下载各自的安装包，不能使用本机的 ARM 应用包替代。

## 开发环境启动

使用 Python 3.11。macOS 的 Apple Silicon 和 Intel，以及 Windows x64，分别安装与构建。

```sh
python3 -m venv .venv
```

macOS：

```sh
.venv/bin/python -m pip install -e '.[full,dev]'
.venv/bin/python -m wpem_desktop
```

Windows PowerShell：

```powershell
.venv\Scripts\python -m pip install -e '.[full,dev]'
.venv\Scripts\python -m wpem_desktop
```

普通用户使用打包后的安装程序，不需要安装 Python。未安装 `full` 依赖的开发环境不能执行 M3GNet 弛豫与贝叶斯占位搜索。

## 使用

1. 在独立目录新建 `.wpem` 项目，或打开已有项目。
2. 选择模块和具体分析，导入谱图与所需 CIF。CSV / DAT / TXT / XY 使用前两列作为横坐标与强度。
3. 确认波长、数据单位、分析区间与参数。角度范围支持 `5-40` 或 `[5, 40]`；其他列表使用 `[10, 90]`；XPS 峰使用表格编辑。
4. 点击“开始分析”。日志显示真实计算阶段；“停止计算”保留已有文件，并把记录标为未完成。
5. 在分析记录中查看结果，双击结果文件预览，导出图表、数值文件或包含全部输入的分析 ZIP。

“打开示例”会复制上游 Mn₂O₃ 教学数据并填入教学参数，所有计算在副本中进行。

也可以先选择实验文件、CIF 和参数，再点击“开始分析”：尚未建项目时会提示创建项目，保存后沿用当前输入继续计算；取消创建时保留当前输入。直接点击“新建项目”也会保留当前表单。

### 科研结果说明

- `XRDfit` 精修晶格常数，不能据此宣称所有原子坐标都已精修。
- 自动 XRD 分析按区间内实际采样点和有效波长共同生成 HKL；双波长模式仅使用两条峰位均严格位于数据区间内的反射，边界处不完整的双峰不参与拟合。平均波长及零点校准模式按求解器的有效平均波长生成反射，原始数据和用户的拟合区间保留。
- 结构预求解只有通过原算法接受条件才会更新运行中的 CIF 副本；原始导入文件不被改写。
- 达到迭代上限和收敛是不同状态，结果界面保留原始停止标志与 Rp / Rwp。
- RDF 中角度输入为 **2θ（度）**，距离为 **Å**，原子数密度填写 **atoms/Å³**。当数据未覆盖高角度归一化区间时，必须明确提供正数 `Nf2`。
- EXAFS 工作区覆盖原项目已有处理与变换，不额外声称提供完整的散射路径结构拟合。
- 数据表只预览前 2000 行、100 列；原始结果与导出文件不截断。
- 不读取外部 pickle 文件；晶体图额外输出 JSON / NPY，方便安全复用。

## 项目文件

```text
样品.wpem                 项目索引，使用相对路径
inputs/                   带 SHA-256 记录的输入副本
runs/时间-编号/
  request.json            输入、参数与随机种子
  result.json             状态、诊断、版本与结果文件清单
  run.log                 完整日志
  inputs/                 本次运行可写副本
  figures/                可重绘曲线、PNG、SVG 与交互 HTML
  ...                     保留上游计算输出
```

移动项目时，请一起移动其整个目录。每次分析使用单独目录，避免上游固定文件名互相覆盖。

## 验证与打包

在另一台电脑验证时，先解压完整源码，安装 Python 3.11，再双击 `构建并验证.bat`（Windows）或 `构建并验证.command`（Mac）。首次运行需要联网下载计算依赖，窗口会依次显示测试、打包和成品验证进度。建议预留至少 20 GB 可用空间。

Windows 默认生成可解压运行的 ZIP；安装 Inno Setup 6 后还会生成 Setup 安装程序。Mac 生成对应处理器架构的 DMG，包含应用和“应用程序”快捷入口。

通过标准：源代码测试全部通过，`outputs/bundle-check.json` 中 `status` 为 `passed`，`outputs/packaged-science.xml` 中失败和错误数量均为 0，并且能手动打开应用、运行示例和旋转三维晶胞。没有可用显卡的构建环境可能得到 `passed_with_manual_checks`；这表示计算和普通界面检查通过，三维图尚需在有显卡的电脑上确认，不能据此声称三维图已经渲染成功。请保留 `outputs` 中的报告与截图；自动检查通过仍需在真实桌面确认显示和操作正常。

需要逐步执行时：

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/prepare_bundle.py
.venv/bin/python -m PyInstaller --noconfirm packaging/desktop.spec
.venv/bin/python scripts/check_bundle.py
.venv/bin/python scripts/package_installers.py
```

Windows 请将 `.venv/bin/python` 替换成 `.venv\Scripts\python`。`packaging/windows.iss` 用于制作 Windows 安装程序。

`.github/workflows/build.yml` 为 Windows x64、macOS Apple Silicon 和 Intel 定义了独立的测试、打包及成品验证流程。需要在实际目标平台运行成功后，才能确认该平台可交付。发布签名及 macOS 公证需要发布者的证书，未配置证书的构建不可声称已签名。

## 上游来源与修改

固定上游版本：`6b4e5542af3896040a0f445e5a72487d7023c1aa`。来源、逐文件哈希及桌面化修正记录在 `wpem_desktop/_vendor/upstream.json`。上游源码与模型保留原有目录，未重新实现 WPEM 求解器。

桌面化修正涉及结构化诊断、晶体图目录、CIF 安全解析、无窗口绘图、RDF 的角度与归一化、结构弛豫输出。会改变科研数值的修正必须有明确的验证用例。

PyWPEM 采用 MIT 许可；M3GNet 和其他依赖保留各自许可。原始许可保存在 `_vendor/LICENSE-*`，打包时收集第三方声明。

科研引用：Cao et al., *AI-Driven Structure Refinement of X-ray Diffraction*, [arXiv:2602.16372](https://arxiv.org/abs/2602.16372)。
