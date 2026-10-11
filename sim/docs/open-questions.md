# Open questions

## RP aprox curves at the championship tiers

The RP approximation curve is overconfident at RCMP and CMP events, check back in on a general model once we have more than one season to go off of.

## Robot states where a season reports them

Modelling each robot's state, such as leave and park, beat the EPA aproximation curve on parking RPs, but only works when the rule pack reports those states per team. We would have to add team-based stat tracking to the overall pipeline.

## Create non-generic formulas for specific RP types

Every RP oddsmaking is currently routed through a metric's predicted points. More specific models should be made to account for foul-granted RP, counting-based RP, team-separable performance. The universal model is not hald bad, but there is plenty left on the table.

## Rating uncertainty that shrinks through an event

The score model draws every match independently with one spread per season. Early predictions are less certain because the ratings have seen few of the event's matches, can we take advantage of that for better predictions?
