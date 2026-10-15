import pytest

from scripts import check_bundle, package_installers


def test_failed_bundle_check_cannot_leave_previous_success(monkeypatch, tmp_path):
    monkeypatch.setattr(check_bundle, "ROOT", tmp_path)
    output = tmp_path / "outputs"
    output.mkdir()
    stale = [output / name for name in ("bundle-check.json", "bundle-smoke.png", "bundle-interactive.png", "bundle-interactive.json", "packaged-science.xml")]
    for path in stale:
        path.write_text("previous run")
    with pytest.raises(FileNotFoundError):
        check_bundle.main()
    assert not any(path.exists() for path in stale)


def test_windows_packaging_prints_chinese_with_legacy_console(monkeypatch, tmp_path):
    import io
    import sys
    import zipfile
    root = tmp_path / "中文目录"
    app = root / "dist/PyWPEMDesktop"
    app.mkdir(parents=True)
    (app / "PyWPEMDesktop.exe").write_bytes(b"test executable")
    monkeypatch.setattr(package_installers, "__file__", str(root / "scripts/package_installers.py"))
    monkeypatch.setattr(package_installers.platform, "system", lambda: "Windows")
    monkeypatch.setattr(package_installers.shutil, "which", lambda name: None)
    monkeypatch.setenv("ProgramFiles(x86)", str(root / "no-compiler"))
    output = io.BytesIO()
    console = io.TextIOWrapper(output, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", console)
    package_installers.main()
    console.flush()
    assert "便携版" in output.getvalue().decode("utf-8")
    with zipfile.ZipFile(root / "dist/PyWPEMDesktop-Windows-x64.zip") as archive:
        assert archive.read("PyWPEMDesktop/PyWPEMDesktop.exe") == b"test executable"
