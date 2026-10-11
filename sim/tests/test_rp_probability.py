"""Drawing bonus RPs."""

from __future__ import annotations

import numpy as np

from sim.rp_probability import draw_bonus
from sim.rp_source import rp_sources
from warehouse.rules.loader import discover


def test_the_second_pollinator_rp_never_appears_without_the_first() -> None:
    pack = next(pack for pack in discover() if pack.season == 2026)
    rng = np.random.default_rng(0)
    first = rng.uniform(0, 1, (5000, 2))
    earned = draw_bonus(
        {"pollinator1RP": first, "pollinator2RP": 0.6 * first, "swarmRP": np.full((5000, 2), 0.5)},
        rp_sources(pack),
        rng,
    )

    assert earned["pollinator2RP"].any()
    assert not (earned["pollinator2RP"] & ~earned["pollinator1RP"]).any()
