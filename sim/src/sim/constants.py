"""The sim's fitted constants."""

from __future__ import annotations

from sim.award_model import AwardModel
from sim.pick_model import PickModel
from sim.rp_probability import RpCurve
from sim.rp_source import Ratio
from sim.score import ScoreModel
from warehouse.tier import EventTier

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

MEASURED_PICK_MODELS: dict[str, PickModel] = {
    "epa-0.10.0": PickModel(
        coefficients=(1.449, 12.53, -10.38, 0.5326, 1.279, 0.7664, 0.1129),
        decisions=8287,
        seasons=(2022, 2023, 2024, 2025),
    ),
}

MEASURED_AWARD_MODELS: dict[str, tuple[AwardModel, ...]] = {
    "epa-0.10.0": (
        AwardModel(
            "Inspire",
            (0.4453, 0.1278, 1.091, 0.7429, -0.3808, 0.4789, 0.5586, 0.8074),
            stage=EventTier.REGULAR,
            decisions=944,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Inspire",
            (0.4896, 0.263, 1.477, 0.1779, -0.4712, 0.6328, 0.8163, 0.7864),
            stage=EventTier.RCMP,
            decisions=617,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Think",
            (0.3938, 1.042, 1.104, 0.479, -0.3616, 0.2744, 0.4343, 0.5616),
            decisions=1560,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Connect",
            (1.038, 1.294, 0.4438, -0.4662, 0.2888, 0.399, 0.7082),
            decisions=1517,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Reach",
            (0.4018, 0.6113, -0.586, -0.06663, 0.2134, 0.821),
            decisions=448,
            seasons=(2025,),
        ),
        AwardModel(
            "Sustain",
            (0.5073, 0.529, -0.3524, 0.1221, 0.4661, 0.5429),
            decisions=447,
            seasons=(2025,),
        ),
        AwardModel(
            "Design",
            (0.5488, 0.319, 0.7485, 0.7244, -0.3328, 0.5127, 0.6077, 0.2353),
            decisions=1537,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Innovate",
            (0.6505, 0.3395, 1.012, 0.768, -0.3562, 0.3777, 0.5983, 0.2938),
            decisions=1537,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Control",
            (0.5329, 0.3851, 0.5694, 0.546, 0.8722, -0.3511, 0.4722, 0.6759, 0.4339),
            decisions=1463,
            seasons=(2022, 2023, 2024, 2025),
        ),
    ),
}
