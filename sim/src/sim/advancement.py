"""Advancement points, the order they rank teams in, and the slots each event offers."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.special import erfinv

from sim.award_model import INSPIRE
from sim.playoff import Alliance
from warehouse.rules.model import AdvancementPoints


@dataclass(frozen=True, slots=True)
class TeamPoints:
    """A team's advancement points at one event, by category."""

    qualification: int = 0
    selection: int = 0
    playoff: int = 0
    awards: int = 0

    @property
    def total(self) -> int:
        return self.qualification + self.selection + self.playoff + self.awards


@dataclass(frozen=True, slots=True)
class Offers:
    """Teams offered a slot on merit, in advancement order.

    Attributes:
        advancing: Offered the next level: the regional championship from a qualifier, FIRST Championship from a
            regional championship.
        premier: Offered a Premier event, from a regional championship only.
    """

    advancing: tuple[int, ...]
    premier: tuple[int, ...] = ()


def qualification_points(rank: int, n_teams: int, points: AdvancementPoints) -> int:
    """Points for a qualification rank, spread from the rule pack's maximum to its minimum by an inverse error
    function of rank."""
    alpha = points.qualification_alpha
    half_range = (points.qualification_max - points.qualification_min) / 2
    middle = (points.qualification_max + points.qualification_min) / 2
    spread = erfinv((n_teams - 2 * rank + 2) / (alpha * n_teams)) / erfinv(1 / alpha)
    return math.ceil(spread * half_range + middle)


def advancement_points(
    ranking: Sequence[int],
    alliances: Sequence[Alliance],
    places: Sequence[int],
    awards: Mapping[str, Sequence[int]],
    points: AdvancementPoints,
) -> dict[int, TeamPoints]:
    """Each team's points at one event.

    Args:
        ranking: Teams in qualification rank order, first place first.
        alliances: Playoff alliances in seed order, captain first, then picks in the order they were made.
        places: Each alliance's playoff finish, in seed order.
        awards: Each award's placed teams, 1st first.
        points: The season's point tables.
    """
    n = len(alliances)
    selection: dict[int, int] = {}
    for seed, alliance in enumerate(alliances, start=1):
        for slot, team in enumerate(alliance):
            # Captains and first picks share the alliance number; later rounds run in reverse seed order.
            draft = seed if slot < 2 else (slot - 1) * n + (n - seed + 1)
            selection[team] = points.selection_base - draft
    playoff = {
        team: points.playoff[place - 1] if place <= len(points.playoff) else 0
        for alliance, place in zip(alliances, places, strict=True)
        for team in alliance
    }
    judged: dict[int, int] = {}
    for award, placed in awards.items():
        table = points.inspire if award == INSPIRE else points.other_awards
        for place, team in enumerate(placed[: len(table)]):
            judged[team] = judged.get(team, 0) + table[place]
    return {
        team: TeamPoints(
            qualification=qualification_points(rank, len(ranking), points),
            selection=selection.get(team, 0),
            playoff=playoff.get(team, 0),
            awards=judged.get(team, 0),
        )
        for rank, team in enumerate(ranking, start=1)
    }


def advancement_order(
    points: Mapping[int, TeamPoints], tiebreakers: Mapping[int, Sequence[float]], rng: np.random.Generator
) -> list[int]:
    """Teams best first: total points, then award, playoff, selection and qualification points, then ``tiebreakers``,
    higher first, then at random.

    ``tiebreakers`` are each team's average qualification points without fouls, average autonomous points, and
    highest and second-highest qualification scores without fouls.
    """
    draw = dict(zip(points, rng.permutation(len(points)), strict=True))

    def key(team: int) -> tuple[float, ...]:
        p = points[team]
        return (
            -p.total,
            -p.awards,
            -p.playoff,
            -p.selection,
            -p.qualification,
            *(-v for v in tiebreakers.get(team, ())),
            draw[team],
        )

    return sorted(points, key=key)


def offers(
    order: Sequence[int], already_advanced: frozenset[int], slots: int, *, first_championship_slots: int | None = None
) -> Offers:
    """The slots an event offers, in ``order``, passing over teams that have already advanced to the same level.

    At a regional championship, ``first_championship_slots`` of the slots go to FIRST Championship and the rest to
    Premier events; elsewhere it is None and every slot goes to the next level.
    """
    offered = tuple(t for t in order if t not in already_advanced)[:slots]
    if first_championship_slots is None:
        return Offers(offered)
    return Offers(offered[:first_championship_slots], offered[first_championship_slots:])
