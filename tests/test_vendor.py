import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent / "wpem_desktop/_vendor"


def test_upstream_sources_have_recorded_origin_and_syntax():
    manifest = json.loads((ROOT / "upstream.json").read_text())
    modified = {entry.split(":", 1)[0] for entry in manifest["local_patches"]}
    assert len(manifest["commit"]) == 40
    for name, expected in manifest["files"].items():
        relative = name.removeprefix("src/")
        path = ROOT / "pywpem" / relative
        if path.suffix != ".py":
            continue
        data = path.read_bytes()
        ast.parse(data)
        if relative not in modified:
            actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            assert actual == expected, name
    assert (ROOT / "LICENSE-PyWPEM").is_file()
    assert (ROOT / "LICENSE-M3GNet").is_file()


@pytest.mark.full
def test_offline_model_matches_recorded_upstream_hash():
    manifest = json.loads((ROOT / "upstream.json").read_text())
    path = "src/Extinction/m3gnet/models/MP-2021.2.8-EFS/m3gnet.data-00000-of-00001"
    target = ROOT / "pywpem" / path[4:]
    assert target.is_file(), "Full desktop build requires the offline M3GNet checkpoint."
    data = target.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert actual == manifest["files"][path]
