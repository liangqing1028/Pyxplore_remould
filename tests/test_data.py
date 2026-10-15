import numpy as np
import pytest

from wpem_desktop.data import load_array, read_spectrum


@pytest.mark.parametrize("text", ["x,intensity\n10,3\n11,4\n12,5\n", "# instrument\n12 5\n11 4\n10 3\n", "10;3\n11;4\n12;5\n"])
def test_spectrum_formats_and_ascending_order(tmp_path, text):
    path = tmp_path / "谱图.dat"
    path.write_text(text, encoding="utf-8")
    result = read_spectrum(path)
    np.testing.assert_array_equal(result.x, [10, 11, 12])
    np.testing.assert_array_equal(result.intensity, [3, 4, 5])


@pytest.mark.parametrize("text", ["10,1\n11,2\n11,3", "10,1\n11,nan\n12,3", "10,1\n11,2\nbroken\n12,3"])
def test_bad_points_are_rejected_without_silent_deletion(tmp_path, text):
    path = tmp_path / "bad.csv"
    path.write_text(text)
    with pytest.raises(ValueError):
        read_spectrum(path)


def test_namespaced_xrdml(tmp_path):
    path = tmp_path / "scan.xrdml"
    path.write_text('<xrdMeasurements xmlns="urn:test"><scan><dataPoints><positions axis="2Theta"><startPosition>10</startPosition>'
                    '<endPosition>12</endPosition></positions><intensities>3 4 5</intensities></dataPoints></scan></xrdMeasurements>')
    np.testing.assert_array_equal(read_spectrum(path).to_numpy(), [[10, 3], [11, 4], [12, 5]])


def test_object_arrays_cannot_execute_pickle(tmp_path):
    path = tmp_path / "unsafe.npy"
    np.save(path, np.asarray([{"x": 1}], dtype=object))
    with pytest.raises(ValueError, match="allow_pickle"):
        load_array(path)


def test_xrdml_rejects_partial_numeric_parse(tmp_path):
    path = tmp_path / "bad.xrdml"
    path.write_text('<root><positions axis="2Theta"><startPosition>10</startPosition><endPosition>12</endPosition></positions>'
                    '<intensities>1 2 3 invalid</intensities></root>')
    with pytest.raises(ValueError):
        read_spectrum(path)
