# Pick model

How the sim forms playoff alliances: each captain picks from the teams still available, drawn from a model of how real
captains have picked. One set of coefficients applies to every season.

## Model

`PickModel` (`sim/pick_model.py`) gives each available team a score from its traits, weighted by the model's
coefficients. A team's chance of being picked is `exp(score)` as a share of the same over every available team.

`PickField` computes the traits:

| Trait | Description |
| --- | --- |
| `predictor_z` | The candidate's predicted point contribution, as a z-score within the event |
| `rank_pct` | The candidate's qualification rank as a percentile, first place 1 and last 0 |
| `captain_x_rank` | The captain's rank percentile times the candidate's |
| `partner` | The candidate played on the captain's alliance in qualification |
| `allied_before` | The candidate was on the captain's playoff alliance at an earlier event this season |
| `same_city` | The candidate gives the same city as the captain in its registration |
| `team_age` | Seasons since the candidate's rookie year, capped at `TEAM_AGE_CAP` |

Each trait has one weight, `w`, and a team's score is their sum:

```
score = w_predictor_z × predictor_z
      + w_rank_pct × rank_pct
      + w_captain_x_rank × captain's rank_pct × rank_pct
      + w_partner × partner
      + w_allied_before × allied_before
      + w_same_city × same_city
      + w_team_age × team_age

P(pick) = exp(score) / sum of exp(score) over every team still available
```

The weights are `MEASURED_PICK_MODELS` in `sim/constants.py`, keyed by predictor version, in `PICK_FEATURES` order.

`w_captain_x_rank` impacts the relavence of a team's rank being used to pick. Being negative, it implies captains
with lower rankings (often last minute promotions) are more likely to rely strictly on rank compared to other factors.

## Selection

`select_alliances` (`sim/selection.py`) forms the alliances in seed order:

- Each captain is the best-ranked team not yet on an alliance.
- It picks by a draw from the model's probabilities over every team not yet on an alliance, and the pick always
  accepts.
- `alliance_size`: two-team alliances except at FIRST Championship (three-team). The second round of
  picks runs in reverse seed order.

## Fitting

`pick_decisions` (`sim/pick_corpus.py`) reads a season's selections from `pub.v_alliance_pick`. It keeps one decision
per captain's first pick, at rated events: the captain, every team it could pick, the one it took, and their traits.

- Ranks are FIRST's published qualification rankings.
- The predictor's rating is read after the event's last qualification match, before alliance selection.
- An event is left out when it has no rankings, a team lacks a rating, and the occasional event where a
  team left before selection.

`measure_pick_model` fits every first pick of the given seasons pooled, by maximum likelihood. `allied_before`
is fit only on seasons after and including `INTO_THE_DEEP`, when the two-team alliance structure started.
Every other trait uses all seasons.

## Derivation

The factors were first explored with epa-0.10.0, DECODE 2025, with ranks rebuilt from the matches and sister teams from
a generated registry. Events were split by date: the first 70% trained, the rest were held out. Every comparison is
the held-out mean log probability of the team actually picked, and its interval is a 95% bootstrap over held-out
events.

### Factor search

A random forest was trained on every candidate as a row, with whether it was picked as the label, and its predictions
were renormalized within each pick's pool. Its features were everything plausibly known at selection: ratings and OPR,
in total, by phase and by leaf component; rank, ranking score and the first tiebreaker; each value's distance from the
best still available; the captain's rank and rating; pool size and pick slot; partner, opponent count, sister team,
same city and region, earlier alliances and earlier picks; and team age.

| Feature | Importance |
| --- | --- |
| rank percentile, distance from the best available | +0.150 |
| EPA z, distance from the best available | +0.133 |
| OPR z, distance from the best available | +0.090 |
| EPA z | +0.057 |
| first tiebreaker | +0.037 |
| OPR z | +0.035 |
| rank percentile | +0.032 |
| ranking score | +0.027 |
| captain's rank percentile | +0.023 |
| auto OPR z | +0.023 |
| teleop artifact points | +0.022 |
| pool size | +0.022 |
| partner | +0.016 |
| captain's EPA z | +0.015 |
| same city | +0.006 |
| sister | +0.005 |
| team age | +0.002 |
| allied before | +0.002 |
| opponent count | -0.001 |

Traits that are proxies for the same underlying effect cannabalize each other's importance, so suspected related
effects are investigated further.

### Winnowing

A simple pick model was built first, on just a team's strength, its rank, whether it partnered the captain and whether
it is a sister team. Then each promising factor from the forest was added to it one at a time, to see how much better
it predicted the held-out picks.

| Term added | Held-out gain |
| --- | --- |
| allied before | +0.0273 |
| same city | +0.0117 |
| captain's EPA z times EPA z | +0.0099 |
| team age | +0.0099 |
| pool size times EPA z | +0.0089 |
| auto artifact points | +0.0068 |
| EPA z squared | +0.0062 |
| captain's rank times rank | +0.0060 |
| auto OPR z | -0.0004 |
| first tiebreaker | -0.0006 |
| OPR z | -0.0009 |
| ranking score | -0.0014 |
| opponent count | -0.0038 |

Then the reverse check: starting from the full model, which at this point still included sister teams, each factor was
taken out one at a time to see how much worse the held-out picks were predicted without it. The interval shows how
sure that loss is, and the last column how often a resampled set of events still showed a loss.

| Term dropped | Held-out loss | Interval | Share of bootstrap above zero |
| --- | --- | --- | --- |
| partner | +0.0346 | +0.0197 to +0.0508 | 1.000 |
| allied before | +0.0272 | +0.0106 to +0.0455 | 0.999 |
| same city | +0.0101 | +0.0031 to +0.0176 | 0.998 |
| team age | +0.0099 | +0.0032 to +0.0164 | 0.999 |
| captain's rank times rank | +0.0075 | -0.0048 to +0.0203 | 0.886 |
| sister | +0.0049 | -0.0049 to +0.0146 | 0.828 |

### Sister teams and same city

Nearly every sister team candidate shares the captain's city, so the two traits overlap. In the forest, each took the
other's importance when the other was removed. With same city in, sister team added a held-out gain whose interval crosses
zero, and dropping sister team moved same city's coefficient up to absorb it. Same city stays because it needs only the
FIRST supplied registered city, and sister teams need a curated list.
