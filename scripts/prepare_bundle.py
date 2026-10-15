"""Stage tutorial data and third-party license notices before freezing."""

from __future__ import annotations

import importlib.metadata
import json
import shutil
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    assets = root / "wpem_desktop/assets"
    example = assets / "examples"
    example.mkdir(parents=True, exist_ok=True)
    for filename in ("Mn2O3.cif", "intensity.csv"):
        source = root / "examples/upstream/class_2_basic_structure/data" / filename
        if not source.is_file():
            raise FileNotFoundError("Missing upstream tutorial data: " + str(source))
        shutil.copy2(source, example / filename)
    model = root / "wpem_desktop/_vendor/pywpem/Extinction/m3gnet/models/MP-2021.2.8-EFS"
    for filename in ("checkpoint", "m3gnet.json", "m3gnet.index", "m3gnet.data-00000-of-00001"):
        if not (model / filename).is_file():
            raise FileNotFoundError("Missing offline model: " + filename)
    licenses = assets / "licenses"
    licenses.mkdir(exist_ok=True)
    inventory = []
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name", "unknown")
        folder = licenses / name
        for file in distribution.files or []:
            if any(token in Path(str(file)).name.lower() for token in ("license", "copying", "notice")):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    folder.mkdir(exist_ok=True)
                    shutil.copy2(source, folder / Path(str(file)).name)
        inventory.append({"name": name, "version": distribution.version,
                          "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", "")})
    (assets / "dependencies.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"Staged official example, offline model, and {len(inventory)} dependency notices.")


if __name__ == "__main__":
    main()
