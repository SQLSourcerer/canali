"""The sim's fitted constants."""

from __future__ import annotations

from sim.rp_probability import RpCurve

# Qualification alliance-rows a season needs before its own RP curves replace earlier seasons'.
RP_CURVE_MIN_ROWS = 4000

# Rows the bucket that sets an RP curve's cap must hold.
RP_CAP_MIN_ROWS = 100

# Whole-season fits on qualification rows, epa-0.10.0, keyed by bonus RP component.
MEASURED_RP_CURVES: dict[int, dict[str, RpCurve]] = {
    2025: {
        "movementRP": RpCurve(shift=0.9447, log_sd=1.6477, log_sd_slope=0.03927, cap=0.7402, rows=62245),
        "patternRP": RpCurve(shift=-3.2819, log_sd=2.6708, log_sd_slope=-0.02095, cap=0.6053, rows=62245),
    },
}
