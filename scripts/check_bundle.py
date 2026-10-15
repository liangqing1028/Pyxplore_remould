"""Exercise a frozen worker and render its GUI without a Python installation path."""

from __future__ import annotations

import csv
import json
import os
import platform
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from wpem_desktop.project import Project


def main():
    if sys.platform == "darwin":
        executable = ROOT / "dist/PyWPEMDesktop.app/Contents/MacOS/PyWPEMDesktop"
    elif sys.platform == "win32":
        executable = ROOT / "dist/PyWPEMDesktop/PyWPEMDesktop.exe"
    else:
        executable = ROOT / "dist/PyWPEMDesktop/PyWPEMDesktop"
    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)
    for name in ("bundle-check.json", "bundle-smoke.png", "bundle-interactive.png", "bundle-interactive.json", "packaged-science.xml"):
        (output / name).unlink(missing_ok=True)
    project_path = output / "packaged-check" / "打包验证.wpem"
    project = Project.open(project_path) if project_path.exists() else Project.create(project_path)
    source = output / "packaged-check" / "原始数据.dat"
    source.write_text("x y\n10 4\n11 5\n12 6\n", encoding="utf-8")
    run = project.create_run("convert", {}, {"spectrum": source})
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["QT_QPA_PLATFORM"] = "windows" if sys.platform == "win32" else "cocoa" if sys.platform == "darwin" else "offscreen"
    environment["TF_USE_LEGACY_KERAS"] = "1"
    subprocess.run([str(executable), "--worker", str(run / "request.json")],
                   env=environment, cwd=output, timeout=180, check=True)
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "success", result
    with (run / "converted.csv").open() as stream:
        rows = [[float(value) for value in row] for row in csv.reader(stream)]
    assert rows == [[10, 4], [11, 5], [12, 6]], rows
    screenshot = output / "bundle-smoke.png"
    subprocess.run([str(executable), "--project", str(project.path), "--smoke-test", str(screenshot)],
                   env=environment, cwd=output, timeout=90, check=True)
    assert screenshot.is_file() and screenshot.stat().st_size > 10000
    cif_run = project.create_run("cif", {"show_unitcell": True, "two_theta_range": [15, 70], "relaxation": True},
                                 {"cif": ROOT / "examples/upstream/class_3_multi_phase/data/NaCl.cif"})
    subprocess.run([str(executable), "--worker", str(cif_run / "request.json")],
                   env=environment, cwd=output, timeout=240, check=True)
    cif_result = json.loads((cif_run / "result.json").read_text(encoding="utf-8"))
    assert cif_result["status"] == "success", cif_result
    assert math.isfinite(cif_result["summary"]["结构弛豫"]["energy_per_atom_eV"])
    interactive = next((cif_run / "figures").glob("interactive-*.html"))
    subprocess.run([str(executable), "--smoke-html", str(interactive), "--smoke-test", str(output / "bundle-interactive.png")],
                   env=environment, cwd=output, timeout=90, check=True)
    assert (output / "bundle-interactive.png").is_file()
    interactive_check = json.loads((output / "bundle-interactive.json").read_text(encoding="utf-8"))
    assert isinstance(interactive_check["webgl_rendered"], bool)
    manual_checks = [] if interactive_check["webgl_rendered"] else ["当前构建环境无可用 WebGL，需在有显卡的电脑上确认三维晶胞显示和旋转。"]
    xrd_run = project.create_run("xrd", {
        "wavelength": [1.540593, 1.544414], "two_theta_range": [15, 75], "iter_max": 1,
        "InitializationEpoch": 0, "cpu": 2, "low_bound": 20, "up_bound": 70, "subset_number": 11,
        "background": {"lowAngleRange": 17, "poly_n": 13, "bac_split": 16, "bac_num": 300},
    }, {"spectrum": ROOT / "examples/upstream/class_2_basic_structure/data/intensity.csv",
        "cifs": [ROOT / "examples/upstream/class_2_basic_structure/data/Mn2O3.cif"]})
    subprocess.run([str(executable), "--worker", str(xrd_run / "request.json")],
                   env=environment, cwd=output, timeout=240, check=True)
    xrd_result = json.loads((xrd_run / "result.json").read_text(encoding="utf-8"))
    assert xrd_result["status"] in {"success", "warning"}, xrd_result
    assert math.isfinite(xrd_result["metrics"]["Rwp"])
    environment["PYWPEM_TEST_EXECUTABLE"] = str(executable)
    science_report = output / "packaged-science.xml"
    with (output / "packaged-science.log").open("w", encoding="utf-8") as stream:
        subprocess.run([sys.executable, "-m", "pytest", "tests/test_science.py", "-q",
                        "--junitxml=" + str(science_report)], env=environment, cwd=ROOT,
                       stdout=stream, stderr=subprocess.STDOUT, timeout=1200, check=True)
    report = {"status": "passed_with_manual_checks" if manual_checks else "passed", "platform": platform.platform(), "architecture": platform.machine(),
              "executable": str(executable), "worker_result": result, "cif_result": cif_result,
              "xrd_result": xrd_result, "screenshot": str(screenshot), "interactive_rendered": interactive_check["webgl_rendered"],
              "required_manual_checks": manual_checks,
              "scientific_regression": str(science_report)}
    (output / "bundle-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Packaged workers, model inference, multi-process XRD, Chinese paths, and GUI checks completed.")
    for check in manual_checks:
        print(check)


if __name__ == "__main__":
    main()
