# Award model

How the sim hands out judged awards once alliances are selected: each award goes to a team drawn from a model of how
judges have chosen, among the teams still able to win it. One set of coefficients applies to every season.

## Model

`AwardModel` (`sim/award_model.py`) gives each eligible team a score from its traits, weighted by the award's
coefficients. A team's chance of the award is `exp(score)` as a share of the same over every eligible team.

`AwardField` computes the traits:

| Trait | Description |
| --- | --- |
| `predictor_z` | The team's predicted point contribution after its last qualification match, as a z-score within the event |
| `predictor_auto_z` | The autonomous part of the same, as a z-score within the event |
| `own_history` | The team's earlier wins of this award |
| `other_history` | The team's earlier wins of every other award |
| `machine_history` | The team's earlier wins of the other machine awards: Design, Innovate and Control |
| `team_attribute_history` | The team's earlier wins of the other team attribute awards |
| `inspire_history` | The team's earlier Inspire placings, 1st, 2nd or 3rd |
| `rookie` | The team is in its rookie season |
| `captain` | The team captains a playoff alliance |
| `first_pick` | The team was an alliance's first pick |
| `seed_score` | The team's alliance seed, 1 for the first seed and 0 for the last, 0 when unpicked |

Each award weighs its own set of traits, `AWARD_TERMS`, and a team's score is their weighted sum:

| Award | Strength | History | Rookie and selection |
| --- | --- | --- | --- |
| Inspire | `predictor_z`, `predictor_auto_z` | `inspire_history`, `other_history` | all |
| Think | `predictor_z` | `inspire_history`, `own_history`, `other_history` | all |
| Connect | | `inspire_history`, `own_history`, `other_history` | all |
| Reach, Sustain | | `team_attribute_history`, `other_history` | all |
| Design, Innovate | `predictor_z` | `machine_history`, `own_history`, `inspire_history` | all |
| Control | `predictor_z`, `predictor_auto_z` | `machine_history`, `own_history`, `inspire_history` | all |

"All" is `rookie`, `captain`, `first_pick` and `seed_score`.

Each term has one weight, `w`, and a team's score is their sum. For Inspire:

```
score = w_predictor_z × predictor_z
      + w_predictor_auto_z × predictor_auto_z
      + w_inspire_history × inspire_history
      + w_other_history × other_history
      + w_rookie × rookie
      + w_captain × captain
      + w_first_pick × first_pick
      + w_seed_score × seed_score

P(award) = exp(score) / sum of exp(score) over every team still eligible
```

The other awards follow the same form over their own terms.

The weights are `MEASURED_AWARD_MODELS` in `sim/constants.py`, keyed by predictor version, in `AWARD_TERMS` order.
Every award has one model for regular events and regional championships together, except those in
`TIER_SPLIT_AWARDS`, which have one per tier. `model_for` picks the model for an award at a tier.

Every award weighs rookies down. Selection weighs up for nearly every award: captaining or being picked, and a better
seed, raise a team's chance even after its strength is counted.

## Eligable teams

The pool for each award follows the competition manual:

- A team wins at most one judged award at an event, counting Inspire's 2nd and 3rd places.
- At a qualifier or league tournament, a team that has already won Inspire this season can't win Inspire 1st again,
  but can place 2nd or 3rd.

## Award step

`draw_awards` (`sim/awards.py`) places the awards in turn:

- Inspire first, with as many places as `inspire_places` gives for the field size, each drawn with the Inspire model
  from the teams not yet placed.
- Then each other award's winner, in `MODELLED_AWARDS` order, from teams not yet placed.
- Then Judges' Choice, uniformly from the teams left.

## Fitting

`award_decisions` (`sim/award_corpus.py`) reads a season's awards at regular events and regional championships.

- Events with divisions drop out, since their awards sit on a parent event with no qualification matches.
- The predictor's rating is read after the event's last qualification match, before alliance selection.

`measure_award_models` fits every 1st place of the given seasons pooled, by maximum likelihood. Inspire's 2nd and 3rd
places are not fitted; the sim draws them with the Inspire 1st model.

## Performance

Fitted on 2022 to 2024 and scored on 2025. Reach and Sustain started in 2025, so they were fitted on its first 70% of
events by date and scored on the rest, which are mostly regional championships. Pseudo-R² is one minus the held-out log
likelihood over that of a uniform draw, with a 95% bootstrap over events. Top-1 is how often the team the model rates
highest won.

### All regions

| Award | Tier | Winners | Pseudo-R² | Interval | Top-1 | Uniform top-1 |
| --- | --- | --- | --- | --- | --- | --- |
| Inspire | REGULAR | 306 | 0.455 | 0.397 to 0.514 | 0.54 | 0.10 |
| Inspire | RCMP | 166 | 0.389 | 0.292 to 0.472 | 0.47 | 0.08 |
| Think | REGULAR | 301 | 0.255 | 0.200 to 0.311 | 0.42 | 0.11 |
| Think | RCMP | 163 | 0.203 | 0.132 to 0.277 | 0.37 | 0.09 |
| Connect | REGULAR | 285 | 0.186 | 0.134 to 0.238 | 0.38 | 0.11 |
| Connect | RCMP | 161 | 0.118 | 0.057 to 0.178 | 0.30 | 0.08 |
| Reach | REGULAR | 55 | 0.094 | -0.004 to 0.205 | 0.27 | 0.12 |
| Reach | RCMP | 92 | 0.108 | 0.052 to 0.165 | 0.26 | 0.08 |
| Sustain | REGULAR | 52 | 0.162 | 0.049 to 0.269 | 0.44 | 0.11 |
| Sustain | RCMP | 91 | 0.097 | 0.044 to 0.154 | 0.30 | 0.08 |
| Design | REGULAR | 289 | 0.197 | 0.155 to 0.243 | 0.38 | 0.11 |
| Design | RCMP | 163 | 0.174 | 0.127 to 0.223 | 0.30 | 0.09 |
| Innovate | REGULAR | 288 | 0.198 | 0.145 to 0.247 | 0.36 | 0.11 |
| Innovate | RCMP | 162 | 0.173 | 0.109 to 0.239 | 0.35 | 0.09 |
| Control | REGULAR | 284 | 0.373 | 0.312 to 0.433 | 0.52 | 0.11 |
| Control | RCMP | 160 | 0.268 | 0.197 to 0.337 | 0.36 | 0.08 |
| All awards | | 3018 | 0.244 | 0.224 to 0.265 | 0.40 | 0.10 |

Inspire's later places, drawn with the Inspire model from the teams left:

| Place | Tier | Placings | Pseudo-R² | Interval | Top-1 |
| --- | --- | --- | --- | --- | --- |
| 2nd | REGULAR | 280 | 0.460 | 0.395 to 0.522 | 0.60 |
| 3rd | REGULAR | 157 | 0.384 | 0.313 to 0.455 | 0.45 |
| 2nd | RCMP | 156 | 0.432 | 0.346 to 0.516 | 0.54 |
| 3rd | RCMP | 112 | 0.317 | 0.227 to 0.411 | 0.42 |

### Pennsylvania

Pennsylvania's 2025 qualifiers, scored by the same held-out fits, then its championship.

| Qualifier award | Winners | Pseudo-R² | Interval | Top-1 | Uniform top-1 |
| --- | --- | --- | --- | --- | --- |
| Inspire | 12 | 0.578 | 0.318 to 0.814 | 0.50 | 0.07 |
| Think | 12 | 0.612 | 0.383 to 0.793 | 0.75 | 0.07 |
| Connect | 12 | 0.455 | 0.148 to 0.706 | 0.67 | 0.07 |
| Reach | 4 | 0.203 | -0.131 to 0.553 | 0.25 | 0.04 |
| Sustain | 4 | 0.401 | 0.099 to 0.573 | 0.75 | 0.04 |
| Design | 12 | 0.326 | 0.103 to 0.535 | 0.67 | 0.07 |
| Innovate | 12 | 0.440 | 0.186 to 0.658 | 0.58 | 0.07 |
| Control | 12 | 0.553 | 0.335 to 0.728 | 0.67 | 0.07 |
| Inspire 2nd | 12 | 0.894 | 0.828 to 0.951 | 0.83 | 0.07 |
| Inspire 3rd | 8 | 0.736 | 0.545 to 0.888 | 0.88 | 0.05 |
| Every 1st place | 80 | 0.473 | 0.309 to 0.595 | 0.62 | 0.07 |
| Championship, every 1st place | 8 | 0.304 | | 0.25 | 0.03 |

Pennsylvania's fields are larger than most.

## Derivation

The factors were explored with epa-0.10.0. Every award except Reach and Sustain was fitted on 2022 to 2024 and scored
on 2025; Reach and Sustain split 2025 by date as above. Every comparison is the held-out mean log probability of the
team that actually won, and its interval is a 95% bootstrap over held-out events.

### Starting point

The initial award study gave each award a small set of terms: OPR as a z-score within the event (and its auto part
for Inspire and Control), decayed award history split by kind, and the seasons a team had been seen in the corpus
for the team attribute awards. Those terms were the base everything below was measured against.

### Factor search

A random forest was trained per award and tier on every eligible team as a row, with whether it won as the label, and
its predictions were renormalized within each pool. Importance is the held-out loss when one feature is shuffled
within each event. Its features were everything plausibly known to the model by award selection time: OPR and EPA,
in total and by phase, before and after qualification, and as distance from the best in the field; rank, qualification
average and win rate; captain, pick, seed finalist and event winner; award history, this season and career, by award
and by kind; team age and rookie; and home region, state and city compared to event.

The three most important features for each award and tier:

| Award | Tier | First | Second | Third |
| --- | --- | --- | --- | --- |
| Inspire | REGULAR | Inspire placings +0.251 | OPR z, distance from the best +0.175 | own wins +0.076 |
| Think | REGULAR | Inspire placings +0.157 | OPR z, distance from the best +0.066 | own wins +0.057 |
| Connect | REGULAR | Inspire placings +0.174 | OPR z, distance from the best +0.052 | own wins +0.049 |
| Reach | REGULAR | other awards +0.081 | other team attribute awards +0.077 | Inspire placings +0.042 |
| Sustain | REGULAR | other awards +0.121 | EPA z before the event +0.033 | rank percentile +0.031 |
| Design | REGULAR | OPR z, distance from the best +0.110 | EPA z after the event +0.027 | OPR z +0.027 |
| Innovate | REGULAR | OPR z, distance from the best +0.122 | EPA z before the event +0.049 | EPA z after the event +0.034 |
| Control | REGULAR | OPR z, distance from the best +0.212 | auto OPR z +0.071 | EPA z after the event +0.045 |
| Inspire | RCMP | Inspire placings +0.134 | own wins +0.118 | OPR z, distance from the best +0.077 |
| Think | RCMP | Inspire placings +0.079 | playoff matches played +0.051 | own wins +0.048 |
| Connect | RCMP | own wins +0.081 | Inspire placings +0.074 | playoff matches played +0.034 |
| Reach | RCMP | Inspire placings +0.202 | OPR z, distance from the best +0.119 | other awards +0.053 |
| Sustain | RCMP | any award last season +0.079 | OPR z, distance from the best +0.047 | other awards +0.037 |
| Design | RCMP | OPR z, distance from the best +0.091 | EPA z before the event +0.057 | alliance seed +0.052 |
| Innovate | RCMP | OPR z, distance from the best +0.109 | playoff matches played +0.046 | qualification average z +0.030 |
| Control | RCMP | OPR z, distance from the best +0.119 | playoff matches played +0.048 | Inspire placings +0.027 |

Traits that are proxies for the same underlying effect cannibalize each other's importance, so EPA z at the end of
qualification and its distance from the best in the pool were checked with each in and out:

| Award | Tier | EPA z, both in | EPA z alone | Distance from the best, both in | Distance from the best alone |
| --- | --- | --- | --- | --- | --- |
| Inspire | REGULAR | +0.045 | +0.098 | +0.144 | +0.116 |
| Think | REGULAR | +0.011 | +0.030 | +0.099 | +0.080 |
| Connect | REGULAR | +0.010 | +0.032 | +0.134 | +0.133 |
| Reach | REGULAR | +0.038 | +0.036 | +0.120 | +0.048 |
| Sustain | REGULAR | -0.005 | +0.020 | +0.109 | +0.082 |
| Design | REGULAR | +0.023 | +0.074 | +0.215 | +0.165 |
| Innovate | REGULAR | +0.048 | +0.088 | +0.161 | +0.133 |
| Control | REGULAR | +0.016 | +0.136 | +0.296 | +0.298 |
| Inspire | RCMP | +0.067 | +0.155 | +0.164 | +0.140 |
| Think | RCMP | -0.017 | +0.016 | +0.054 | +0.051 |
| Connect | RCMP | +0.012 | +0.019 | +0.133 | +0.089 |
| Reach | RCMP | +0.010 | +0.032 | +0.112 | +0.060 |
| Sustain | RCMP | +0.006 | +0.048 | +0.080 | +0.138 |
| Design | RCMP | +0.041 | +0.117 | +0.180 | +0.148 |
| Innovate | RCMP | +0.010 | +0.064 | +0.113 | +0.147 |
| Control | RCMP | +0.013 | +0.184 | +0.195 | +0.192 |

With both in, distance from the best took most of EPA z's importance. Within a pool the two differ only by the best
team's EPA z, the same for every candidate, so in the conditional logit, which compares teams within a pool, they are
the same term. The forest scores each team on its own, so it favours the version already measured against the pool.
EPA z went forward to the conditional logit as the simpler option.
