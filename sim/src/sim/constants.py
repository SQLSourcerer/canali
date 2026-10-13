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
            (0.4448, 0.128, 1.098, 0.7492, -0.008609, -0.4168, 0.4782, 0.5583, 0.8083),
            stage=EventTier.REGULAR,
            decisions=944,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Inspire",
            (0.4884, 0.2637, 1.489, 0.1876, -0.01424, -0.538, 0.6381, 0.8208, 0.7908),
            stage=EventTier.RCMP,
            decisions=617,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Think",
            (0.3952, 1.036, 1.088, 0.468, 0.01689, -0.2871, 0.2751, 0.4312, 0.5626),
            decisions=1560,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Connect",
            (1.038, 1.294, 0.4437, 0.0001554, -0.4655, 0.2888, 0.399, 0.7082),
            decisions=1517,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Reach",
            (0.4103, 0.5809, 0.02769, -0.4696, -0.06359, 0.2121, 0.8317),
            decisions=448,
            seasons=(2025,),
        ),
        AwardModel(
            "Sustain",
            (0.5158, 0.4913, 0.02807, -0.2361, 0.1157, 0.46, 0.5653),
            decisions=447,
            seasons=(2025,),
        ),
        AwardModel(
            "Design",
            (0.5505, 0.3085, 0.7348, 0.7096, 0.01737, -0.2506, 0.5107, 0.6053, 0.2336),
            decisions=1537,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Innovate",
            (0.6507, 0.3271, 1.0, 0.7538, 0.01678, -0.278, 0.3748, 0.5944, 0.2957),
            decisions=1537,
            seasons=(2022, 2023, 2024, 2025),
        ),
        AwardModel(
            "Control",
            (0.532, 0.3855, 0.5575, 0.5402, 0.8605, 0.01379, -0.2835, 0.4711, 0.6748, 0.4341),
            decisions=1463,
            seasons=(2022, 2023, 2024, 2025),
        ),
    ),
}
