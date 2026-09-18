import math

from tideline.predict import Constituent, height


def test_single_constituent_peaks_at_phase():
    m2 = Constituent("M2", 2.0, 0.0, 28.9841042)
    assert math.isclose(height([m2], 0.0), 2.0)


def test_datum_offsets_the_series():
    m2 = Constituent("M2", 1.0, 0.0, 28.9841042)
    assert math.isclose(height([m2], 0.0, datum=3.0), 4.0)


def test_empty_station_is_flat_at_datum():
    assert height([], 5.0, datum=1.5) == 1.5
