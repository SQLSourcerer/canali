# Open questions

## RP aprox curves at the championship tiers

The RP approximation curve is overconfident at RCMP and CMP events, check back in on a general model once we have more than one season to go off of.

## Robot states where a season reports them

Modelling each robot's state, such as leave and park, beat the EPA aproximation curve on parking RPs, but only works when the rule pack reports those states per team. We would have to add team-based stat tracking to the overall pipeline.

## Create non-generic formulas for specific RP types

Every RP oddsmaking is currently routed through a metric's predicted points. More specific models should be made to account for foul-granted RP, counting-based RP, team-separable performance. The universal model is not hald bad, but there is plenty left on the table.

## Rating uncertainty that shrinks through an event

The score model draws every match independently with one spread per season. Early predictions are less certain because the ratings have seen few of the event's matches, can we take advantage of that for better predictions?
## Declines

Every simulated invitation is accepted. Future work could base declines off of simulated win probability against some "standard playoff alliance" as calculated by event predictor_z.

## How many award places an event gives

The sim gives Inspire places by field size: 1st only up to 10 teams, 1st and 2nd from 11 to 20, and 1st to 3rd from 21.
No other award gives a 2nd or 3rd place. That fits Pennsylvania's recent events, but regions differ and change over
time: Pennsylvania gave two Inspire places at every 2024 event regardless of size, Australia's championship gives 2nd
places in every award, and some regions give a Think 2nd at larger qualifiers. Regions also break their own rule now
and then. A simulation that generalizes beyond Pennsylvania would need to draw the number of places with uncertainty.
