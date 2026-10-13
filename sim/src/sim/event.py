"""One event played through: qualification, alliance selection, the playoff, awards and advancement.

Every rating the event uses is the team's prediction as of the beginning of the simulation.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from sim.advancement import Offers, TeamPoints, advancement_order, advancement_points, offers
from sim.award_model import AUTO_PREFIX, AwardField, AwardModel
from sim.awards import draw_awards
from sim.match import SeasonModels, draw_matches
from sim.pick_model import PickField, PickModel
from sim.playoff import Alliance, playoff
from sim.schedule import Schedule
from sim.selection import ALLIANCE_SIZE, alliance_count, alliance_size, select_alliances
from sim.standings import MatchResults, RankingRules, Standings, standings
from warehouse.rules.model import RulePack
from warehouse.tier import EventTier, tier_for

Floats = npt.NDArray[np.float64]

AWARD_STAGES = frozenset({EventTier.REGULAR, EventTier.RCMP})

NO_FOUL = "preFoulTotal"
AUTO = "autoPoints"


@dataclass(frozen=True, slots=True)
class EventField:
    """An event's teams and what is known of them before it starts.

    Attributes:
        event_type: The event's type.
        predicted: Each team's predicted points per component, keyed by team, then column name.
        allied: Each team's alliance partners at earlier events this season.
        city: Each team's city, None when unknown.
        team_age: Each team's seasons since its rookie year.
        history: Each team's decayed award placings, as ``AwardField`` takes them.
        rookie: Teams in their rookie season.
        inspire_won_before: Teams that have won Inspire at an earlier event this season.
    """

    event_type: str | None
    predicted: Mapping[int, Mapping[str, float]]
    allied: Mapping[int, frozenset[int]]
    city: Mapping[int, str | None]
    team_age: Mapping[int, float]
    history: Mapping[int, Mapping[str, float]]
    rookie: frozenset[int]
    inspire_won_before: frozenset[int] = frozenset()

    def rating(self, team: int) -> float:
        return float(sum(self.predicted[team].values()))

    def auto_rating(self, team: int) -> float:
        return float(sum(v for k, v in self.predicted[team].items() if k.startswith(AUTO_PREFIX)))


@dataclass(frozen=True, slots=True)
class Slots:
    """The slots an event offers.

    Attributes:
        count: Slots offered.
        already_advanced: Teams that have already advanced to the level the slots lead to.
        first_championship: Of ``count``, the slots to FIRST Championship at a regional championship, else None.
    """

    count: int
    already_advanced: frozenset[int] = frozenset()
    first_championship: int | None = None


@dataclass(frozen=True, slots=True)
class EventModels:
    """The models an event is played with."""

    season: SeasonModels
    pick: PickModel
    awards: Sequence[AwardModel]


@dataclass(frozen=True, slots=True)
class EventOutcome:
    """One playing of an event.

    Attributes:
        standings: Qualification standings.
        alliances: Playoff alliances in seed order, captain first.
        places: Each alliance's playoff finish, in seed order.
        awards: Each award's placed teams, 1st first; empty where awards are not simulated.
        points: Each team's advancement points.
        order: Teams in advancement order, best first.
        offers: The slots offered, or None when the event offers none.
    """

    standings: Standings
    alliances: list[Alliance]
    places: tuple[int, ...]
    awards: dict[str, tuple[int, ...]]
    points: dict[int, TeamPoints]
    order: list[int]
    offers: Offers | None


def simulate_event(
    field: EventField,
    schedule: Schedule,
    pack: RulePack,
    models: EventModels,
    rng: np.random.Generator,
    *,
    slots: Slots | None = None,
) -> EventOutcome:
    """Play the event once on ``schedule``, every team of which ``field`` must predict."""
    advancement = pack.structure.advancement_points
    if advancement is None:
        raise ValueError(f"{pack.season}: the pack has no advancement points")

    results = draw_matches(models.season, pack, _alliance_predictions(field, schedule), field.event_type, rng)
    ranked = standings(schedule, results, RankingRules.from_pack(pack), rng)
    teams = tuple(int(t) for t in ranked.teams)
    rating = np.array([field.rating(t) for t in teams])

    alliances = select_alliances(
        PickField(
            teams=teams,
            rating=rating,
            partners=_match_mates(schedule),
            allied=field.allied,
            city=field.city,
            team_age=field.team_age,
        ),
        models.pick,
        alliance_count(pack.structure, len(teams)),
        alliance_size(field.event_type),
        rng,
    )

    def play(red: Alliance, blue: Alliance, rng: np.random.Generator) -> tuple[float, float]:
        total = np.array([[sum(map(field.rating, _on_field(field, a))) for a in (red, blue)]])
        score = models.season.score.sample(total, rng) + models.season.score.foul_points(total.shape, rng)
        return float(score[0, 0]), float(score[0, 1])

    places = playoff(pack.structure, alliances, play, rng)

    stage = tier_for(field.event_type)
    awards: dict[str, tuple[int, ...]] = {}
    if stage in AWARD_STAGES:
        award_field = AwardField(
            teams=teams,
            rating=rating,
            auto_rating=np.array([field.auto_rating(t) for t in teams]),
            history=field.history,
            rookie=field.rookie,
            alliances=alliances,
        )
        awards = draw_awards(award_field, models.awards, stage, rng, inspire_won_before=field.inspire_won_before)

    points = advancement_points(teams, alliances, places, awards, advancement)
    order = advancement_order(points, _advancement_tiebreakers(schedule, results), rng)
    offered = (
        None
        if slots is None
        else offers(order, slots.already_advanced, slots.count, first_championship_slots=slots.first_championship)
    )
    return EventOutcome(ranked, alliances, places, awards, points, order, offered)


def _alliance_predictions(field: EventField, schedule: Schedule) -> dict[str, Floats]:
    """Each alliance's predicted points per column, shaped ``(match, alliance)``."""
    columns = sorted({c for t in np.unique(schedule.stations) for c in field.predicted[int(t)]})
    return {
        c: np.vectorize(lambda t, c=c: field.predicted[int(t)].get(c, 0.0), otypes=[np.float64])(schedule.stations).sum(
            axis=2
        )
        for c in columns
    }


def _match_mates(schedule: Schedule) -> dict[int, frozenset[int]]:
    """Every team each team shared a qualification match with, on either alliance."""
    mates: dict[int, set[int]] = defaultdict(set)
    for match in schedule.stations:
        present = {int(t) for t in match.ravel()}
        for t in present:
            mates[t] |= present - {t}
    return {t: frozenset(m) for t, m in mates.items()}


def _on_field(field: EventField, alliance: Alliance) -> Alliance:
    """The alliance's best-rated teams, as many as take the field."""
    return tuple(sorted(alliance, key=field.rating, reverse=True)[:ALLIANCE_SIZE])


def _advancement_tiebreakers(schedule: Schedule, results: MatchResults) -> dict[int, tuple[float, ...]]:
    """Each team's average no-foul and autonomous points, then its highest and second-highest no-foul scores, over
    its counted appearances."""
    missing = sorted({NO_FOUL, AUTO} - set(results.components))
    if missing:
        raise ValueError(f"results lack {missing}")
    no_foul: dict[int, list[float]] = defaultdict(list)
    auto: dict[int, list[float]] = defaultdict(list)
    for m, a, s in zip(*np.nonzero(~schedule.surrogate), strict=True):
        team = int(schedule.stations[m, a, s])
        no_foul[team].append(float(results.components[NO_FOUL][m, a]))
        auto[team].append(float(results.components[AUTO][m, a]))
    tiebreakers: dict[int, tuple[float, ...]] = {}
    for team, scores in no_foul.items():
        best = sorted(scores, reverse=True)
        tiebreakers[team] = (
            float(np.mean(scores)),
            float(np.mean(auto[team])),
            best[0],
            best[1] if len(best) > 1 else 0.0,
        )
    return tiebreakers
