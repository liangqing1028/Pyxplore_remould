import numpy as np
import pytest
from pymatgen.core import Lattice

from wpem_desktop._vendor.pywpem.EMBraggOpt.BraggLawDerivation import BraggLawDerivation


CELL = [6.3297, 9.4646, 11.1, 62.6109, 83.29, 72.2418]
HKL = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0], [1, 0, 1],
                [0, 1, 1], [1, -1, 0], [1, 0, -1], [0, 1, -1]])


def angles(cell, hkl, waves):
    lattice = Lattice.from_parameters(*cell)
    spacing = np.array([lattice.d_hkl(row) for row in hkl])
    return np.rad2deg(2 * np.arcsin(np.asarray(waves)[None, :] / (2 * spacing[:, None]))).ravel()


def test_triclinic_spacing_matches_independent_reciprocal_metric():
    expected = [Lattice.from_parameters(*CELL).d_hkl(row) for row in HKL]
    actual = BraggLawDerivation().get_d_space_multitask([7], [HKL.T], [CELL])[0]
    np.testing.assert_allclose(actual, expected, rtol=1e-12)


@pytest.mark.parametrize("waves", [[1.54056], [1.54056, 1.54439]])
def test_triclinic_refinement_recovers_valid_cell(waves):
    target = np.array(CELL) + [0.006, -0.008, 0.009, 0.02, -0.015, 0.01]
    result = BraggLawDerivation().OptmialLatticeConstant(
        7, angles(CELL, HKL, waves), angles(target, HKL, waves), 9, 5, 40,
        *HKL.T, *CELL, waves,
    )
    np.testing.assert_allclose(result[:6], target, rtol=1e-6, atol=2e-5)
    np.testing.assert_allclose(result[6], angles(target, HKL, waves), atol=1e-6)
    assert np.linalg.eigvalsh(Lattice.from_parameters(*result[:6]).metric_tensor).min() > 0


def test_empty_bragg_selection_has_actionable_error():
    peaks = angles(CELL, HKL, [1.54056, 1.54439])
    with pytest.raises(ValueError, match="Bragg.*65.*80"):
        BraggLawDerivation().OptmialLatticeConstant(
            7, peaks, peaks, 9, 65, 80, *HKL.T, *CELL, [1.54056, 1.54439],
        )


def test_degenerate_triclinic_reflections_are_rejected():
    hkl = np.array([[1, 0, 0], [2, 0, 0], [3, 0, 0]])
    waves = [1.54056, 1.54439]
    peaks = angles(CELL, hkl, waves)
    with pytest.raises(ValueError, match="独立|约束"):
        BraggLawDerivation().OptmialLatticeConstant(
            7, peaks, peaks, 9, 5, 80, *hkl.T, *CELL, waves,
        )


def test_tied_peak_errors_use_requested_subset_without_repetition():
    waves = [1.54056, 1.54439]
    peaks = angles(CELL, HKL, waves)
    result = BraggLawDerivation().OptmialLatticeConstant(
        7, peaks, peaks, 6, 5, 40, *HKL.T, *CELL, waves,
    )
    np.testing.assert_allclose(result[:6], CELL, atol=1e-10)
    np.testing.assert_allclose(result[6], peaks, atol=1e-10)


def test_triclinic_selection_uses_independent_reflections_beyond_lowest_errors():
    hkl = np.array([[0, 1, 0], [0, 0, 1], [0, 1, 1], [0, 1, -1], [0, 2, 0],
                    [0, 0, 2], [0, 2, 1], [0, 1, 2], [0, 2, 2],
                    [1, 0, 0], [1, 1, 0], [1, 0, 1]])
    waves = [1.54056, 1.54439]
    original = angles(CELL, hkl, waves)
    observed = original.copy()
    observed[-6:] += 1e-5
    result = BraggLawDerivation().OptmialLatticeConstant(
        7, original, observed, 9, 5, 40, *hkl.T, *CELL, waves,
    )
    assert np.isfinite(result[:6]).all()
    np.testing.assert_allclose(result[6], observed, atol=1e-6)
