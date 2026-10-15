import random
import numpy as np

from wpem_desktop._vendor.pywpem.StructureOpt.SiteOpt import generate_sp, label_decode


def test_candidate_cap_applies_before_large_site_enumeration():
    atoms = [["Mn3+", index / 80, 0, 0] for index in range(80)]
    random.seed(42)
    actual = generate_sp(atoms, "Mn3+", "Ru2+", ["Mn3+", "Ru2+"], 6)
    assert len(actual) == 6
    assert len({tuple(row) for row in actual}) == 6
    assert atoms[0][0] == "Mn3+"
    random.seed(42)
    assert generate_sp(atoms, "Mn3+", "Ru2+", ["Mn3+", "Ru2+"], 6) == actual


def test_small_search_covers_all_nonempty_subsets():
    atoms = [["Mn3+", 0, 0, 0], ["Mn3+", 0.5, 0.5, 0.5]]
    assert len(generate_sp(atoms, "Mn3+", "Ru2+", ["Mn3+", "Ru2+"], 20)) == 3


def test_bayesian_numpy_candidate_decodes_like_initial_list():
    candidate = [0, 0.25, 0.5, 0.75, 1, 0, 0, 0]
    assert label_decode(np.asarray(candidate), ["Mn3+", "Ru2+"]) == label_decode(candidate, ["Mn3+", "Ru2+"])
