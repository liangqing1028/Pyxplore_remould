import numpy as np
import pandas as pd
import pytest

from wpem_desktop._vendor.pywpem.Amorphous.QuantitativeCalculation.AmorphousRDF import RadialDistribution


def test_rdf_degree_units_and_discrete_integral(tmp_path, monkeypatch):
    import matplotlib.pyplot as plt
    monkeypatch.setattr(plt, "savefig", lambda *args, **kwargs: None)
    monkeypatch.setattr(plt, "show", lambda *args, **kwargs: None)
    theta = np.linspace(10, 150, 900)
    wave = 1.54056
    k = 4 * np.pi / wave * np.sin(np.deg2rad(theta / 2))
    intensity = 1 + np.sin(2 * k) / (2 * k)
    source = tmp_path / "known.csv"
    np.savetxt(source, np.column_stack((theta, intensity)), delimiter=",")
    RadialDistribution(wave, 5, str(tmp_path)).RDF(str(source), density_zero=0.05, Nf2=1, highlight=4)
    actual = pd.read_csv(tmp_path / "DecomposedComponents/RDF.csv")
    for index in (50, 100, 200, 300, 450):
        radius = actual.r.iloc[index]
        expected = 2 * radius / np.pi * np.trapz((intensity - 1) * k * np.sin(k * radius), k)
        assert actual.RDF.iloc[index] == pytest.approx(expected, abs=1e-10)
    maximum = actual.r.iloc[actual.RDF.argmax()]
    assert maximum == pytest.approx(2, abs=0.1)
    plt.close("all")


def test_rdf_requires_normalization_when_high_angle_data_missing(tmp_path):
    source = tmp_path / "low_angles.csv"
    np.savetxt(source, np.column_stack((np.linspace(10, 60, 100), np.ones(100))), delimiter=",")
    with pytest.raises(ValueError, match="Nf2"):
        RadialDistribution(1.54, 5, str(tmp_path)).RDF(str(source), Nf2=None)
