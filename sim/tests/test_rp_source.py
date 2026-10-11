"""Recovering an RP's quantity from points."""

from __future__ import annotations

import numpy as np
import pytest

from sim.rp_source import FloorDivide, FromFunction, Identity, Ratio, Recovery

THRESHOLDS = (1, 4, 7, 13, 36, 67)


@pytest.mark.parametrize("recovery", [Identity(), FloorDivide(20), Ratio(0.25)], ids=lambda r: type(r).__name__)
def test_the_points_threshold_is_the_fewest_points_reaching_the_threshold(recovery: Recovery) -> None:
    for threshold in THRESHOLDS:
        t = recovery.points_threshold(threshold)
        assert recovery.recover(np.array([t]))[0] >= threshold
        assert recovery.recover(np.array([t - 1e-6]))[0] < threshold


def test_from_function_matches_floor_divide_on_the_same_formula() -> None:
    custom = FromFunction(lambda p: np.floor(p / 20))
    assert [custom.points_threshold(t) for t in THRESHOLDS] == [FloorDivide(20).points_threshold(t) for t in THRESHOLDS]


def test_ratio_fits_a_known_ratio() -> None:
    points = np.random.default_rng(0).uniform(0, 200, 500)
    fitted = Ratio().fit(points, 0.25 * points)
    assert fitted.ratio == pytest.approx(0.25)
    assert fitted.points_threshold(36) == pytest.approx(144)
