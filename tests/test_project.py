import hashlib
import json

import pytest

from wpem_desktop.project import Project, write_json


def test_project_portable_runs_and_source_protection(tmp_path):
    source = tmp_path / "原始样品.csv"
    source.write_text("10,4\n11,5\n12,6\n", encoding="utf-8")
    original = source.read_bytes()
    project = Project.create(tmp_path / "项目" / "样品.wpem")
    first = project.create_run("convert", {}, {"spectrum": str(source)})
    request = json.loads((first / "request.json").read_text(encoding="utf-8"))
    staged = first / request["inputs"]["spectrum"]
    staged.write_text("changed")
    second = project.create_run("convert", {}, {"spectrum": str(source)})
    assert source.read_bytes() == original
    assert (second / "inputs/spectrum/0/原始样品.csv").read_bytes() == original
    reopened = Project.open(project.path)
    assert len(reopened.data["runs"]) == 2
    assert len(reopened.data["assets"]) == 1
    assert reopened.data["assets"][0]["sha256"] == hashlib.sha256(original).hexdigest()


def test_reusing_project_inputs_does_not_duplicate_assets(tmp_path):
    source = tmp_path / "sample.csv"
    source.write_text("1,2\n2,3\n3,4\n")
    project = Project.create(tmp_path / "p/project.wpem")
    first = project.import_file(source)
    second = project.import_file(project.resolve(first["path"]))
    assert second["id"] == first["id"]
    assert len(project.data["assets"]) == 1


def test_reject_external_paths_in_project(tmp_path):
    project = Project.create(tmp_path / "项目" / "project.wpem")
    project.data["assets"].append({"path": "../secret.txt"})
    project.save()
    with pytest.raises(ValueError, match="超出"):
        Project.open(project.path)


def test_atomic_json_preserves_previous_file_when_serialization_fails(tmp_path):
    path = tmp_path / "project.wpem"
    write_json(path, {"valid": True})
    with pytest.raises(ValueError):
        write_json(path, {"invalid": float("nan")})
    assert json.loads(path.read_text()) == {"valid": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_context_is_snapshot_of_existing_run(tmp_path):
    project = Project.create(tmp_path / "project.wpem")
    source = project.create_run("convert", {}, {})
    (source / "intensity.csv").write_text("1,2\n2,3\n3,4\n")
    second = project.create_run("components", {}, {}, context=source)
    assert (second / "context/intensity.csv").read_text() == (source / "intensity.csv").read_text()
    (source / "intensity.csv").write_text("changed")
    assert "changed" not in (second / "context/intensity.csv").read_text()
