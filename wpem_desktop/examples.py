"""A portable copy of the upstream Mn2O3 tutorial, with its original settings."""

from pathlib import Path
from uuid import uuid4

from .project import Project


def example_directory():
    bundled = Path(__file__).parent / "assets" / "examples"
    if bundled.is_dir():
        return bundled
    return Path(__file__).parent.parent / "examples/upstream/class_2_basic_structure/data"


def create_example(parent):
    root = Path(parent) / ("Mn2O3 示例-" + uuid4().hex[:6])
    project = Project.create(root / "Mn2O3.wpem", "Mn₂O₃ · 官方教学算例")
    assets = {}
    for key, filename in (("spectrum", "intensity.csv"), ("cifs", "Mn2O3.cif")):
        source = example_directory() / filename
        if not source.is_file():
            raise FileNotFoundError("示例数据未完整打包：" + filename)
        assets[key] = [project.import_file(source)["path"]]
    project.data["drafts"] = {"xrd": {"inputs": assets, "parameters": {
        "wavelength": [1.540593, 1.544414], "two_theta_range": [15, 75],
        "subset_number": 11, "low_bound": 20, "up_bound": 70, "bta": 0.85,
        "iter_max": 5, "asy_C": 0, "InitializationEpoch": 0, "cpu": 1,
        "background": {"lowAngleRange": 17, "poly_n": 13, "bac_split": 16, "bac_num": 300},
    }}}
    project.save()
    return project
