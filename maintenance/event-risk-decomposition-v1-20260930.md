# Event risk decomposition v1

## Core principle
Do not ask Jev to forecast the stock price. Use Jev to identify and structure the event. Use Python to estimate:
1. probability the event occurs;
2. conditional return distribution if it occurs;
3. downside and upside expected-value components.

## Dilution
Validated screening target: at least one public offering / private placement / PIPE / warrant-conversion disclosure in the next 60 calendar days.

### Conditional 5D impact
- n=115 liquid/seasoned events.
- mean normalized impact: -0.3133
- negative-part EV coefficient: -0.6278
- positive-part EV coefficient: +0.3145
- median coefficient: -0.3987
- p10 coefficient: -1.5670

For current daily volatility sigma in percentage points:
- scale5 = sigma * sqrt(5)
- downside EV = P(event) * -0.6278 * scale5
- upside offset EV = P(event) * +0.3145 * scale5
- net event EV = P(event) * -0.3133 * scale5
- conditional median = -0.3987 * scale5
- conditional p10 = -1.5670 * scale5

### Conditional 20D impact
- n=81
- mean normalized impact: -0.2140
- negative-part EV coefficient: -0.4253
- positive-part EV coefficient: +0.2113
- median coefficient: -0.2405
- p10 coefficient: -1.1852

## Probability layer
Dilution hazard v2 holdout:
- base event rate: 4.18%
- history+shelf Brier: 0.03857, AUC 0.654, AP 12.43%
- history+shelf+424B5 AUC 0.663, AP 13.66%
- history+shelf+vol AUC 0.682, top-decile rate 13.15% = 3.15x base

Because variant choice was observed on this holdout, keep this as research-candidate status until another matured validation window.

## Output contract
For each ticker display separately:
- Event probability / risk rank
- Conditional median impact
- Conditional adverse p10 impact
- Downside EV
- Upside EV
- Net Event Skew
- Evidence quality / sample size
- Semantics status: structured vs ambiguous

Do not collapse all of this into an opaque 0-100 score.
