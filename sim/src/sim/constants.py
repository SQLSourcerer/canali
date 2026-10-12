"""The sim's fitted constants."""

from __future__ import annotations

from sim.rp_probability import RpCurve
from sim.rp_source import Ratio
from sim.score import ScoreModel

# Rows the bucket that sets an RP curve's cap must hold.
RP_CAP_MIN_ROWS = 100

# Whole-season fits on qualification rows, keyed by predictor version, season and bonus RP component.
MEASURED_RP_CURVES: dict[str, dict[int, dict[str, RpCurve]]] = {
    "epa-0.10.0": {
        2025: {
            "movementRP": RpCurve(
                shift=0.9447, log_sd=1.6477, log_sd_slope=0.03927, cap=0.7402, rows=62245, correlation=0.3511
            ),
            "goalRP": RpCurve(
                shift=-0.0001,
                log_sd=3.2545,
                log_sd_slope=0.002508,
                cap=0.9374,
                rows=62240,
                recovery=Ratio(0.3496),
                correlation=0.9430,
            ),
            "patternRP": RpCurve(
                shift=-3.2819, log_sd=2.6708, log_sd_slope=-0.02095, cap=0.6053, rows=62245, correlation=0.3224
            ),
        },
    },
}

# Earlier seasons' curves that stand in for a bonus RP until its season has INIT_WINDOW rows.
RP_STAND_INS: dict[int, dict[str, tuple[tuple[int, str], ...]]] = {
    2026: {
        "swarmRP": ((2025, "movementRP"),),
        "pollinator1RP": ((2025, "goalRP"),),
        "pollinator2RP": ((2025, "goalRP"),),
    },
}

# Whole-season fits on qualification rows, keyed by predictor version and season.
MEASURED_SCORE_MODELS: dict[str, dict[int, ScoreModel]] = {
    "epa-0.10.0": {
        2022: ScoreModel(
            intercept=0.0971,
            slope=0.8941,
            dispersion=10.220,
            dof=11.96,
            skew=1.2688,
            foul_mean=6.62,
            foul_variance=115.5,
            rows=43573,
        ),
        2023: ScoreModel(
            intercept=-1.3348,
            slope=0.8793,
            dispersion=9.702,
            dof=15.15,
            skew=1.3652,
            foul_mean=5.56,
            foul_variance=156.4,
            rows=50204,
        ),
        2024: ScoreModel(
            intercept=-0.3838,
            slope=0.9522,
            dispersion=11.082,
            dof=10.14,
            skew=1.1977,
            foul_mean=3.49,
            foul_variance=101.5,
            rows=56660,
        ),
        2025: ScoreModel(
            intercept=-0.5347,
            slope=0.9657,
            dispersion=7.363,
            dof=9.886,
            skew=1.1449,
            foul_mean=15.06,
            foul_variance=198.0,
            rows=62181,
        ),
    },
}
