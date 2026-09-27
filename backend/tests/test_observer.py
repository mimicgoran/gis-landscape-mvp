"""
Testovi za ObserverInput model — Phase 2.

Namjerno mali obim (samo granice lat/lon i default vrijednosti opcionih
polja) jer u ovoj fazi model nema drugu logiku — validacija granica je
sve što Pydantic ovdje radi. Kompleksnija GIS matematika (bearing,
distance, sector) dobija svoje testove u Phase 3/5 (vidi
docs/architecture-feasibility-review.md, sekcija 14/13).
"""

import pytest
from pydantic import ValidationError

from app.models.observer import ObserverInput


def test_observer_input_valid_minimal():
    observer = ObserverInput(latitude=43.2914, longitude=20.8171)

    assert observer.latitude == pytest.approx(43.2914)
    assert observer.longitude == pytest.approx(20.8171)
    assert observer.horizontal_accuracy_m is None
    assert observer.phone_altitude_m is None
    assert observer.phone_altitude_accuracy_m is None


def test_observer_input_with_optional_fields():
    observer = ObserverInput(
        latitude=43.2914,
        longitude=20.8171,
        horizontal_accuracy_m=6.4,
        phone_altitude_m=1248.0,
        phone_altitude_accuracy_m=9.0,
    )

    assert observer.horizontal_accuracy_m == pytest.approx(6.4)
    assert observer.phone_altitude_m == pytest.approx(1248.0)
    assert observer.phone_altitude_accuracy_m == pytest.approx(9.0)


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (90.1, 20.0),  # latitude van granice (>90)
        (-90.1, 20.0),  # latitude van granice (<-90)
        (43.0, 180.1),  # longitude van granice (>180)
        (43.0, -180.1),  # longitude van granice (<-180)
    ],
)
def test_observer_input_rejects_out_of_range_coordinates(latitude, longitude):
    with pytest.raises(ValidationError):
        ObserverInput(latitude=latitude, longitude=longitude)


def test_observer_input_rejects_negative_accuracy():
    with pytest.raises(ValidationError):
        ObserverInput(latitude=43.0, longitude=20.0, horizontal_accuracy_m=-1.0)
