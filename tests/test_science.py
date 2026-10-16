"""Real scientific workflows, not mocked solver results."""

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from wpem_desktop.engine import run_request
from wpem_desktop.project import Project

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "examples/upstream"
pytestmark = pytest.mark.integration


def perform(project, operation, parameters, inputs, context=None):
    run = project.create_run(operation, parameters, inputs, context=context)
    executable = os.environ.get("PYWPEM_TEST_EXECUTABLE")
    status = subprocess.run([executable, "--worker", str(run / "request.json")], timeout=240).returncode if executable else run_request(run / "request.json")
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    assert status == 0, result.get("traceback")
    return run, result


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    return Project.create(tmp_path_factory.mktemp("science") / "科研验证.wpem")


@pytest.fixture(scope="module")
def xrd_run(project):
    return perform(project, "xrd", {
        "wavelength": [1.540593, 1.544414], "two_theta_range": [15, 75],
        "subset_number": 11, "low_bound": 20, "up_bound": 70, "bta": 0.85,
        "iter_max": 2, "asy_C": 0, "InitializationEpoch": 0, "cpu": 2,
        "background": {"lowAngleRange": 17, "poly_n": 13, "bac_split": 16, "bac_num": 300},
    }, {"spectrum": str(DATA / "class_2_basic_structure/data/intensity.csv"),
        "cifs": [str(DATA / "class_2_basic_structure/data/Mn2O3.cif")]})


def test_official_xrd_case_and_safe_refined_cif(project, xrd_run):
    run, result = xrd_run
    assert result["metrics"]["Rwp"] < 10
    assert result["metrics"]["iterations"] == 2
    assert result["status"] == "warning"
    assert list((run / "WPEMFittingResults").glob("*_refined.cif"))
    from wpem_desktop._vendor.pywpem.Extinction.CifReader import CifFile
    before = next(iter(CifFile.from_file(str(DATA / "class_2_basic_structure/data/Mn2O3.cif")).data.values())).data
    after = next(iter(CifFile.from_file(str(next((run / "WPEMFittingResults").glob("*_refined.cif")))).data.values())).data
    for field in ("_atom_site_fract_x", "_atom_site_fract_y", "_atom_site_fract_z", "_atom_site_type_symbol"):
        assert before[field] == after[field]
    expected = np.array([9.41, 9.41, 9.41])
    actual = result["summary"]["精修后晶格参数"][0][:3]
    np.testing.assert_allclose(actual, expected, atol=0.05)


def test_xrd_exported_volume_and_plot_match_numeric_results(xrd_run):
    from pymatgen.core import Lattice
    from wpem_desktop._vendor.pywpem.Extinction.CifReader import CifFile

    run, result = xrd_run
    cif = next((run / "WPEMFittingResults").glob("*_refined.cif"))
    block = next(iter(CifFile.from_file(str(cif)).data.values())).data
    cell = result["summary"]["精修后晶格参数"][0]
    assert float(block["_cell_volume"]) == pytest.approx(Lattice.from_parameters(*cell).volume, abs=1e-8)
    observed = np.loadtxt(run / "intensity.csv", delimiter=",")
    fitted = np.loadtxt(run / "DecomposedComponents/fitting_profile.csv", delimiter=",")
    for path in (run / "figures").glob("*.curves.json"):
        curves = {curve["label"]: curve for axis in json.loads(path.read_text()) for curve in axis["curves"]}
        if "WPEM fitting profile" in curves:
            x = curves["Experimental Profile (crystal)"]["x"]
            np.testing.assert_allclose(curves["Experimental Profile (crystal)"]["y"], np.interp(x, observed[:, 0], observed[:, 1]))
            np.testing.assert_allclose(curves["WPEM fitting profile"]["y"], fitted[:, 1])
            break
    else:
        pytest.fail("Missing final XRD fitting plot")


def test_xrd_doublet_at_upper_scan_boundary(project):
    waves = [1.54056, 1.54439]
    outside_peak = 40.09287982261595
    spacing = waves[1] / (2 * np.sin(np.deg2rad(outside_peak / 2)))
    cell = 4 * spacing  # Place the NaCl 400 doublet across the 40-degree boundary.
    cif = project.root / "边界晶相.cif"
    cif.write_text((DATA / "class_3_multi_phase/data/NaCl.cif").read_text().replace("5.62", str(cell)), encoding="utf-8")
    original = cif.read_bytes()
    x = np.linspace(5, 40, 701)
    y = 20 + 0.02 * x
    for squared_hkl in (3, 4, 8, 11, 12, 16):
        for wave, strength in zip(waves, (200, 100)):
            center = np.rad2deg(2 * np.arcsin(wave * np.sqrt(squared_hkl) / (2 * cell)))
            y += strength * np.exp(-((x - center) / 0.08) ** 2)
    spectrum = project.root / "边界谱图.csv"
    np.savetxt(spectrum, np.column_stack((x, y)), delimiter=",")
    run, result = perform(project, "xrd", {
        "wavelength": waves, "two_theta_range": [5, 40], "iter_max": 1,
        "low_bound": 15, "up_bound": 38, "subset_number": 3, "cpu": 1,
        "background": {"poly_n": 2, "bac_num": 100},
    }, {"spectrum": str(spectrum), "cifs": [str(cif)]})
    peaks = pd.read_csv(run / "peak0.csv")
    for wave in waves:
        centers = np.rad2deg(2 * np.arcsin(wave / (2 * peaks.Distance)))
        assert ((centers > 5) & (centers < 40)).all()
    assert not ((peaks.H == 4) & (peaks.K == 0) & (peaks.L == 0)).any()
    assert np.isfinite(result["metrics"]["Rwp"])
    assert (run / "DecomposedComponents/fitting_profile.csv").is_file()
    assert list((run / "WPEMFittingResults").glob("*_refined.cif"))
    assert cif.read_bytes() == original


def test_xrd_phase_without_complete_reflections_has_clear_error(project):
    source = project.root / "无反射区间.csv"
    x = np.linspace(5, 10, 101)
    np.savetxt(source, np.column_stack((x, 20 + np.exp(-((x - 7) / 0.2) ** 2))), delimiter=",")
    run = project.create_run("xrd", {
        "wavelength": [1.54056, 1.54439], "two_theta_range": [5, 10],
        "background": {"poly_n": 2, "bac_num": 50},
    }, {"spectrum": str(source), "cifs": [str(DATA / "class_3_multi_phase/data/NaCl.cif")]})
    executable = os.environ.get("PYWPEM_TEST_EXECUTABLE")
    status = subprocess.run([executable, "--worker", str(run / "request.json")], timeout=240).returncode if executable else run_request(run / "request.json")
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    assert status == 1
    assert result["status"] == "failed"
    assert "NaCl.cif" in result["error"] and "完整反射峰" in result["error"]


def test_three_phase_refinement_reaches_bragg_updates(project):
    from pymatgen.core import Lattice

    cells = [[5.00123442, 6.81942858, 8.93636781, 90, 90, 90],
             [6.3297, 9.4646, 11.1, 62.6109, 83.29, 72.2418],
             [18.1047, 6.5348, 10.6439, 90, 90, 90]]
    hkl = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0], [1, 0, 1],
                    [0, 1, 1], [1, -1, 0], [1, 0, -1], [0, 1, -1]])
    waves = [1.54056, 1.54439]
    x = np.linspace(5, 40, 701)
    y = 20 + 0.02 * x
    files = []
    for index, cell in enumerate(cells):
        lattice = Lattice.from_parameters(*cell)
        spacing = np.array([lattice.d_hkl(row) for row in hkl])
        centers = np.rad2deg(2 * np.arcsin(np.array(waves)[None, :] / (2 * spacing[:, None])))
        keep = ((centers > 5) & (centers < 40)).all(axis=1)
        peaks = pd.DataFrame(hkl[keep], columns=["H", "K", "L"])
        peaks["Mult"] = 1
        peaks["2theta/TOF"] = centers[keep, 0]
        path = project.root / f"三相反射-{index}.csv"
        peaks.to_csv(path, index=False)
        files.append(str(path))
        for pair in centers[keep]:
            for center, strength in zip(pair, (150, 75)):
                y += strength * np.exp(-((x - center) / 0.10) ** 2)
    spectrum = project.root / "三相精修谱.csv"
    np.savetxt(spectrum, np.column_stack((x, y)), delimiter=",")
    run, result = perform(project, "xrd_manual", {
        "wavelength": waves, "Lattice_constants": cells, "two_theta_range": [5, 40],
        "subset_number": 9, "iter_max": 3, "iter_limit": 0, "lock_num": 10,
        "cpu": 1, "asy_C": 0,
        "background": {"poly_n": 2, "bac_num": 100},
    }, {"spectrum": str(spectrum), "peaks": files})
    assert result["metrics"]["iterations"] == 3
    assert np.isfinite(result["metrics"]["Rwp"])
    for cell in result["summary"]["精修后晶格参数"]:
        assert np.isfinite(cell).all()
        assert np.linalg.eigvalsh(Lattice.from_parameters(*cell).metric_tensor).min() > 0
    assert (run / "DecomposedComponents/fitting_profile.csv").is_file()


def test_background_constant_model_is_consistent(project):
    source = project.root / "synthetic-background.csv"
    x = np.linspace(10, 80, 701)
    background = 40 + 0.05 * x
    y = background + 500 * np.exp(-((x - 30) / 0.35) ** 2) + 300 * np.exp(-((x - 55) / 0.5) ** 2)
    np.savetxt(source, np.column_stack((x, y)), delimiter=",")
    run, _ = perform(project, "background", {"poly_n": 2, "bac_num": 100}, {"spectrum": str(source)})
    actual = np.loadtxt(run / "ConvertedDocuments/bac.csv", delimiter=",")[:, 1]
    assert np.sqrt(np.mean((actual - background) ** 2)) < 4


def test_gaussian_background_accepts_pandas_spectrum(project):
    source = project.root / "gaussian-background.csv"
    x = np.linspace(10, 80, 101)
    np.savetxt(source, np.column_stack((x, 20 + 0.1 * x + 50 * np.exp(-((x - 40) / 2) ** 2))), delimiter=",")
    run, _ = perform(project, "background", {"bac_var_type": "multivariate gaussian", "bac_num": 20, "noise": 0.05},
                     {"spectrum": str(source)})
    actual = np.loadtxt(run / "ConvertedDocuments/bac.csv", delimiter=",")
    assert np.isfinite(actual).all()


def test_cif_preprocess_and_interactive_unit_cell(project):
    run, result = perform(project, "cif", {"two_theta_range": [10, 80], "show_unitcell": True},
                          {"cif": str(DATA / "class_3_multi_phase/data/NaCl.cif")})
    assert result["summary"]["密度（g/cm³）"] > 0
    assert list((run / "figures").glob("interactive-*.html"))
    assert list((run / "output_xrd").glob("*HKL.csv"))


def test_simulation_matches_independent_bragg_peak_positions(project):
    from pymatgen.core import Structure
    from pymatgen.analysis.diffraction.xrd import XRDCalculator
    source = DATA / "class_3_multi_phase/data/NaCl.cif"
    run, result = perform(project, "simulation", {"wavelength": 1.54056, "two_theta_range": [15, 80, 0.1]}, {"cif": str(source)})
    assert result["summary"]["模拟数据点数"] > 100
    observed = pd.read_csv(next((run / "output_xrd").glob("*HKL.csv")))["2theta/TOF"].to_numpy()
    reference = XRDCalculator(wavelength=1.54056).get_pattern(Structure.from_file(source), two_theta_range=(15, 80)).x
    for theta in reference:
        assert np.min(np.abs(observed - theta)) < 0.03


def test_amorphous_fit_outputs_finite_curves(project):
    source = project.root / "amorphous.csv"
    x = np.linspace(10, 80, 300)
    y = 100 * np.exp(-((x - 28) / 6) ** 2) + 60 * np.exp(-((x - 53) / 8) ** 2)
    np.savetxt(source, np.column_stack((x, y)), delimiter=",")
    run, _ = perform(project, "amorphous", {"mix_component": 2, "max_iter": 30, "peak_location": [28, 53]}, {"spectrum": str(source)})
    curve = np.loadtxt(run / "DecomposedComponents/Amorphous.csv", delimiter=",")
    assert np.isfinite(curve).all()
    assert curve.shape[0] == len(x)


def test_xps_official_data_reaches_solver(project):
    source = DATA / "class_8_XPS/data/CuO.csv"
    run, result = perform(project, "xps", {
        "atomIdentifier": [["CuII", "2p3/2", 933.7], ["CuII", "2p1/2", 954.0]],
        "satellitePeaks": [["CuII", "2p3/2", 941.6], ["CuII", "2p1/2", 962.5]],
        "iter_max": 2, "InitializationEpoch": 0, "energy_range": [925, 965],
        "background": {"segment": [[910, 931], [948, 952], [958, 959], [966, 970]],
                       "bac_num": 120, "noise": 0.05, "bac_var_type": "multivariate gaussian"},
    }, {"spectrum": str(source)})
    assert np.isfinite(result["metrics"]["Rwp"])
    assert list((run / "XPSFittingProfile").glob("*.csv"))
    profile = np.loadtxt(run / "XPScomponents/FittingProfile.csv", delimiter=",")
    assert profile[:, 0].min() >= 925 and profile[:, 0].max() <= 965
    resumed, resumed_result = perform(project, "xps", {
        "atomIdentifier": [["CuII", "2p3/2", 933.7], ["CuII", "2p1/2", 954.0]],
        "satellitePeaks": [["CuII", "2p3/2", 941.6], ["CuII", "2p1/2", 962.5]],
        "iter_max": 1, "InitializationEpoch": 0, "loadParams": True, "energy_range": [925, 965],
    }, {"spectrum": str(source)}, context=run)
    assert np.isfinite(resumed_result["metrics"]["Rwp"])


@pytest.mark.parametrize("transform", ["fourier", "wavelet"])
def test_exafs_transforms_produce_finite_data(project, transform):
    source = project.root / "synthetic-exafs.csv"
    energy = np.linspace(7000, 7800, 450)
    e0 = 7112
    k = np.sqrt(np.maximum(0, 0.262449 * (energy - e0)))
    absorption = 0.2 + 0.8 / (1 + np.exp(np.clip(-(energy - e0) / 2, -500, 500)))
    absorption += np.where(energy > e0, 0.04 * np.sin(2 * k) * np.exp(-0.03 * k), 0)
    np.savetxt(source, np.column_stack((energy, absorption)), delimiter=",")
    run, _ = perform(project, "exafs", {"Ezero": e0, "Extend": 10, "distance": 4, "window_size": 16, "transform": transform},
                     {"spectrum": str(source)})
    value = pd.read_csv(next((run / "XAFS/EXAFS").glob("FineStructure_*.csv")))
    assert len(value) > 10 and np.isfinite(value.to_numpy()).all()
    assert (run / "XAFS/EXAFS/interactive_plot.html").is_file()


def test_graph_to_matrix_and_adjacency(project):
    graph_run, result = perform(project, "graph", {}, {"cifs": [str(DATA / "class_3_multi_phase/data/NaCl.cif")]})
    assert result["summary"]["成功晶体图数量"] == 1
    nodes = next((graph_run / "CifParserToGraph").glob("*.nodes.json"))
    edges = next((graph_run / "CifParserToGraph").glob("*.edges.npy"))
    matrix_run, _ = perform(project, "matrix", {}, {"nodes": str(nodes)})
    adjacency_run, _ = perform(project, "adjacency", {}, {"edges": str(edges)})
    assert np.load(matrix_run / "node_matrix.npy").shape[1] == 3
    assert np.load(adjacency_run / "adjacency.npy").sum() > 0


def test_rdf_and_graph_numerical_workflows(project):
    theta = np.linspace(10, 150, 900)
    k = 4 * np.pi / 1.54056 * np.sin(np.deg2rad(theta / 2))
    source = project.root / "known-rdf.csv"
    np.savetxt(source, np.column_stack((theta, 1 + np.sin(2 * k) / (2 * k))), delimiter=",")
    run, _ = perform(project, "rdf", {"wavelength": 1.54056, "r_max": 5, "density_zero": 0.05, "Nf2": 1}, {"spectrum": source})
    rdf = pd.read_csv(run / "DecomposedComponents/RDF.csv")
    assert rdf.r.iloc[rdf.RDF.argmax()] == pytest.approx(2, abs=0.1)
    matrix = project.root / "known-adjacency.npy"
    np.save(matrix, [[0, 1, 0], [1, 0, 0], [0, 0, 0]])
    run, _ = perform(project, "laplacian", {}, {"matrix": matrix})
    np.testing.assert_allclose(np.load(run / "laplacian.npy"), np.array([[1, -1, 0], [-1, 1, 0], [0, 0, 1]]) + np.eye(3) * 1e-5)
    inputs = {}
    for key, offset in (("nodes", 0), ("edges", 100), ("target", 200)):
        path = project.root / f"split-{key}.npy"
        np.save(path, np.arange(20) + offset)
        inputs[key] = path
    run, _ = perform(project, "split", {"ratio": 0.25}, inputs)
    np.testing.assert_array_equal(np.load(run / "edges_train.npy") - 100, np.load(run / "nodes_train.npy"))
    assert len(np.load(run / "target_test.npy")) == 5


def test_components_reuse_previous_xrd_without_changing_it(project, xrd_run):
    previous, _ = xrd_run
    original = (previous / "intensity.csv").read_bytes()
    run, _ = perform(project, "components", {"lowboundary": 15, "upboundary": 75, "wavelength": [1.540593, 1.544414], "phase": 1}, {}, context=previous)
    assert (previous / "intensity.csv").read_bytes() == original
    assert list((run / "DecomposedComponents").glob("*.png"))


def test_structure_solver_keeps_imported_cif_unchanged(project, xrd_run):
    previous, _ = xrd_run
    cif = DATA / "class_2_basic_structure/data/Mn2O3.cif"
    original = cif.read_bytes()
    run, result = perform(project, "structure", {"max_nfev": 2, "num_peaks": 6},
                          {"cif": str(cif), "spectrum": str(previous / "ConvertedDocuments/no_bac_intensity.csv")})
    assert cif.read_bytes() == original
    assert "accepted" in result["summary"]
    assert (run / "WPEMFittingResults/structure_solver_report.json").is_file()


def test_multiphase_quantification(project):
    run, result = perform(project, "xrd", {
        "wavelength": [1.540593, 1.544414], "two_theta_range": [11, 110],
        "subset_number": 11, "low_bound": 20, "up_bound": 50, "bta": 0.9,
        "iter_max": 2, "asy_C": 0, "InitializationEpoch": 0, "cpu": 1, "num": 7, "Ave_Waves": True,
        "background": {"LFctg": 0.2, "lowAngleRange": 20, "window_length": 7, "bac_num": 500},
    }, {"spectrum": str(DATA / "class_3_multi_phase/data/intensity.csv"),
        "cifs": [str(DATA / "class_3_multi_phase/data/NaCl.cif"), str(DATA / "class_3_multi_phase/data/Li2CO3.cif")]})
    assert len(result["summary"]["精修后晶格参数"]) == 2
    assert len(list((run / "WPEMFittingResults").glob("*_refined.cif"))) == 2


def test_manual_reflections_cover_no_cif_workflow(project, xrd_run):
    previous, result = xrd_run
    run, actual = perform(project, "xrd_manual", {
        "wavelength": [1.540593, 1.544414], "Lattice_constants": [[9.41, 9.41, 9.41, 90, 90, 90]],
        "two_theta_range": [15, 75], "subset_number": 11, "low_bound": 20, "up_bound": 70,
        "iter_max": 1, "InitializationEpoch": 0, "cpu": 1,
        "background": {"lowAngleRange": 17, "poly_n": 13, "bac_split": 16, "bac_num": 300},
    }, {"spectrum": str(previous / "intensity.csv"), "peaks": [str(previous / "peak0.csv")]})
    assert np.isfinite(actual["metrics"]["Rwp"])
    assert (run / "DecomposedComponents/fitting_profile.csv").is_file()


@pytest.mark.full
def test_m3gnet_relaxation_outputs_structure_and_energy(project):
    pytest.importorskip("tensorflow")
    model = ROOT / "wpem_desktop/_vendor/pywpem/Extinction/m3gnet/models/MP-2021.2.8-EFS/m3gnet.data-00000-of-00001"
    assert model.is_file(), "Offline model must be bundled for the full build."
    run, result = perform(project, "cif", {"two_theta_range": [15, 70], "relaxation": True},
                          {"cif": str(DATA / "class_3_multi_phase/data/NaCl.cif")})
    assert (run / "output_xrd/relaxed_structure.cif").is_file()
    assert np.isfinite(result["summary"]["结构弛豫"]["energy_per_atom_eV"])


@pytest.mark.parametrize("bayesian", [False, True])
def test_substitution_search_generates_results(project, xrd_run, bayesian):
    if bayesian:
        pytest.importorskip("Bgolearn")
    previous, _ = xrd_run
    peaks = next((previous / "WPEMFittingResults").glob("CrystalSystem0_WPEMout*.csv"))
    run, result = perform(project, "substitution", {
        "SolventAtom": "Mn3+", "SoluteAtom": "Ru2+", "random_num": 1 if bayesian else 4,
        "max_iter": 3 if bayesian else 2, "search_cap": 6, "cal_extinction": False,
    }, {"peaks": str(peaks), "cif": str(DATA / "class_2_basic_structure/data/Mn2O3.cif")})
    assert list((run / "WPEMSitOpt").glob("*"))
