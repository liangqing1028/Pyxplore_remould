import numpy as np
import pandas as pd
import pytest

from wpem_desktop.engine import background_std_for_range


def test_vector_background_std_tracks_cropped_data():
    frame = pd.DataFrame({"x": [10, 20, 30, 40, 50]})
    np.testing.assert_array_equal(background_std_for_range([1, 2, 3, 4, 5], frame, (20, 40)), [2, 3, 4])
    np.testing.assert_array_equal(background_std_for_range([2, 3, 4], frame, (20, 40)), [2, 3, 4])
    assert background_std_for_range(2.5, frame, (20, 40)) == 2.5
    with pytest.raises(ValueError):
        background_std_for_range([1, 2], frame, (20, 40))
