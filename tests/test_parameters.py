import numpy as np
import pandas as pd
import pytest

from wpem_desktop.engine import background_std_for_range, xrd_preprocess_range, xrd_bragg_range


def test_vector_background_std_tracks_cropped_data():
    frame = pd.DataFrame({"x": [10, 20, 30, 40, 50]})
    np.testing.assert_array_equal(background_std_for_range([1, 2, 3, 4, 5], frame, (20, 40)), [2, 3, 4])
    np.testing.assert_array_equal(background_std_for_range([2, 3, 4], frame, (20, 40)), [2, 3, 4])
    assert background_std_for_range(2.5, frame, (20, 40)) == 2.5
    with pytest.raises(ValueError):
        background_std_for_range([1, 2], frame, (20, 40))


@pytest.mark.parametrize("waves", [[1.54056, 1.54439], [1.54439, 1.54056], [1.54056]])
@pytest.mark.parametrize("interval", [None, (5, 40), (6, 39.99)])
def test_xrd_reflections_stay_inside_actual_samples_for_every_wavelength(waves, interval):
    frame = pd.DataFrame({"x": np.linspace(5.01, 39.98, 701)})
    reference, (lower, upper) = xrd_preprocess_range(frame, interval, waves)
    samples = frame.x if interval is None else frame.loc[frame.x.between(*interval), "x"]
    assert reference == min(waves)
    for angle in (lower, upper):
        for wave in waves:
            actual = np.rad2deg(2 * np.arcsin(wave / reference * np.sin(np.deg2rad(angle / 2))))
            assert samples.min() - 1e-12 <= actual <= samples.max() + 1e-12
    incident_peak = 39.989202716
    if len(waves) == 2:
        assert upper < incident_peak


@pytest.mark.parametrize("interval, waves", [((50, 60), [1.54]), ((5, 5.01), [1.54]), ((39.9, 40), [1.54, 1.55])])
def test_xrd_rejects_empty_or_too_narrow_fitting_ranges(interval, waves):
    frame = pd.DataFrame({"x": np.linspace(5, 40, 701)})
    with pytest.raises(ValueError, match="数据点|区间过窄"):
        xrd_preprocess_range(frame, interval, waves)


def test_bragg_defaults_follow_sampled_interval_and_preserve_explicit_limits():
    frame = pd.DataFrame({"x": [5.01, 10, 20, 30, 39.98, 50]})
    assert xrd_bragg_range(frame, (5, 40)) == (5.01, 39.98)
    assert xrd_bragg_range(frame, (5, 40), 10, 35) == (10, 35)
    assert xrd_bragg_range(frame, (5, 40), 10, None) == (10, 39.98)
    with pytest.raises(ValueError, match="Bragg.*65.*80"):
        xrd_bragg_range(frame, (5, 40), 65, 80)


def test_xrd_form_defaults_use_automatic_bragg_interval():
    from wpem_desktop.catalog import BY_KEY, parameters
    for key in ("xrd", "xrd_manual"):
        fields = {field["key"]: field["default"] for field in parameters(BY_KEY[key])}
        assert fields["low_bound"] is None and fields["up_bound"] is None
