import pytest

from scripts import check_bundle


def test_failed_bundle_check_cannot_leave_previous_success(monkeypatch, tmp_path):
    monkeypatch.setattr(check_bundle, "ROOT", tmp_path)
    output = tmp_path / "outputs"
    output.mkdir()
    stale = [output / name for name in ("bundle-check.json", "bundle-smoke.png", "bundle-interactive.png", "packaged-science.xml")]
    for path in stale:
        path.write_text("previous run")
    with pytest.raises(FileNotFoundError):
        check_bundle.main()
    assert not any(path.exists() for path in stale)
