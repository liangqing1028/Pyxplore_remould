import json

import numpy as np
import pytest

from wpem_desktop.engine import run_request
from wpem_desktop.project import Project


def run_analysis(tmp_path, operation, parameters, files):
    project = Project.create(tmp_path / "project.wpem")
    run = project.create_run(operation, parameters, files)
    code = run_request(run / "request.json")
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    assert code == 0, result.get("traceback")
    return run, result


def test_conversion_and_bad_request_are_recorded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spectrum = tmp_path / "raw.dat"
    spectrum.write_text("x y\n10 4\n11 5\n12 6\n")
    run, result = run_analysis(tmp_path / "valid", "convert", {}, {"spectrum": str(spectrum)})
    np.testing.assert_array_equal(np.loadtxt(run / "converted.csv", delimiter=","), [[10, 4], [11, 5], [12, 6]])
    assert result["engine_commit"] and result["versions"]["numpy"]
    request_path = run / "request.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    request["inputs"]["spectrum"] = "../../../outside.csv"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    assert run_request(request_path) == 1
    assert json.loads((run / "result.json").read_text(encoding="utf-8"))["status"] == "failed"


def test_adjacency_and_laplacian_include_isolated_nodes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    edges = tmp_path / "edges.npy"
    np.save(edges, [[0, 1], [1, 0]])
    run, _ = run_analysis(tmp_path / "adj", "adjacency", {"size": 3}, {"edges": str(edges)})
    adjacency = np.load(run / "adjacency.npy")
    np.testing.assert_array_equal(adjacency, [[0, 1, 0], [1, 0, 0], [0, 0, 0]])
    lap_run, _ = run_analysis(tmp_path / "lap", "laplacian", {}, {"matrix": str(run / "adjacency.npy")})
    actual = np.load(lap_run / "laplacian.npy")
    np.testing.assert_allclose(actual, np.array([[1, -1, 0], [-1, 1, 0], [0, 0, 1]]) + np.eye(3) * 1e-5)


def test_dataset_split_keeps_sample_alignment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inputs = {}
    for key, offset in (("nodes", 0), ("edges", 100), ("target", 200)):
        path = tmp_path / f"{key}.npy"
        np.save(path, np.arange(20) + offset)
        inputs[key] = str(path)
    run, _ = run_analysis(tmp_path / "split", "split", {"ratio": 0.25}, inputs)
    np.testing.assert_array_equal(np.load(run / "edges_train.npy") - 100, np.load(run / "nodes_train.npy"))
    np.testing.assert_array_equal(np.load(run / "target_test.npy") - 200, np.load(run / "nodes_test.npy"))
    assert len(np.load(run / "nodes_test.npy")) == 5


def test_symmetry_arithmetic_rejects_python_execution(tmp_path):
    from wpem_desktop._vendor.pywpem.Extinction.XRDpre import apply_operation
    np.testing.assert_allclose(apply_operation("-x+1/2,y,z+1/3", ["x", "y", "z"], [0.2, 0.3, 0.4]), [0.3, 0.3, 0.4 + 1/3])
    target = tmp_path / "executed"
    with pytest.raises(ValueError):
        apply_operation(f"__import__('pathlib').Path({str(target)!r}).touch(),y,z", ["x", "y", "z"], [0, 0, 0])
    assert not target.exists()


def test_cif_without_symmetry_operations_preserves_axis_setting(tmp_path):
    from wpem_desktop._vendor.pywpem.Extinction.XRDpre import read_cif, UnitCellAtom

    cif = tmp_path / "axis-setting.cif"
    cif.write_text("""data_axes
_cell_length_a 18.1047
_cell_length_b 6.5348
_cell_length_c 10.6439
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P n 21 a'
_symmetry_Int_Tables_number 33
loop_
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Fe 0.13124 0.24729 0.35468
""")
    _, _, atoms, _, operations = read_cif(str(cif))
    actual = np.array([atom[1:] for atom in UnitCellAtom(atoms, operations)])
    expected = np.array([[0.13124, 0.24729, 0.35468], [0.36876, 0.74729, 0.85468],
                         [0.86876, 0.74729, 0.64532], [0.63124, 0.24729, 0.14532]])
    assert actual.shape == expected.shape
    np.testing.assert_allclose(actual[np.lexsort(actual.T)], expected[np.lexsort(expected.T)], atol=1e-12)
    from wpem_desktop._vendor.pywpem.Extinction.XRDpre import structure_extinction
    assert structure_extinction([["Fe", *coordinate] for coordinate in actual], [0, 0, 1], 10, 1.54056)
